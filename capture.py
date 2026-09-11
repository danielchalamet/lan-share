"""Native macOS ScreenCaptureKit capture, no app bundle or compiler required."""
import asyncio
import time
import threading
import objc
import numpy as np
import ScreenCaptureKit as SC
import Quartz as Q
import CoreMedia as CM
from Foundation import NSObject
from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
from audio_capture import pcm_from_sample
from playout import MediaTimeline


def initialize_macos():
    """SCContentFilter(window) requires an initialized WindowServer connection."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Инициализация macOS должна выполняться в главном потоке")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)
    return app


async def completion(invoke):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    def done(*args):
        def deliver():
            if future.done():
                return
            error = args[-1]
            if error:
                future.set_exception(RuntimeError(str(error)))
            else:
                future.set_result(args[0] if len(args) > 1 else None)
        loop.call_soon_threadsafe(deliver)
    invoke(done)
    return await asyncio.wait_for(future, 20)


class Output(NSObject, protocols=[objc.protocolNamed('SCStreamOutput'), objc.protocolNamed('SCStreamDelegate')]):
    def stream_didStopWithError_(self, stream, error):
        self.owner.error = str(error)
        self.owner.label = None
        with self.owner.lock:
            self.owner.latest = None

    def stream_didOutputSampleBuffer_ofType_(self, stream, sample, kind):
        if kind == SC.SCStreamOutputTypeAudio:
            try:
                pcm = pcm_from_sample(sample)
                with self.owner.lock:
                    self.owner.timeline.add_audio(pcm, self.owner.timestamp(sample))
            except Exception as error:
                self.owner.error = f'Аудио: {error}'
            return
        if kind != SC.SCStreamOutputTypeScreen:
            return
        attachments = CM.CMSampleBufferGetSampleAttachmentsArray(sample, False)
        if attachments and attachments[0].get(SC.SCStreamFrameInfoStatus, SC.SCFrameStatusComplete) != SC.SCFrameStatusComplete:
            return
        pixel = CM.CMSampleBufferGetImageBuffer(sample)
        if pixel is None:
            return
        if Q.CVPixelBufferLockBaseAddress(pixel, Q.kCVPixelBufferLock_ReadOnly) != 0:
            return
        try:
            width = Q.CVPixelBufferGetWidth(pixel)
            height = Q.CVPixelBufferGetHeight(pixel)
            stride = Q.CVPixelBufferGetBytesPerRow(pixel)
            pointer = Q.CVPixelBufferGetBaseAddress(pixel)
            data = np.frombuffer(pointer.as_buffer(height * stride), dtype=np.uint8)
            frame = data.reshape(height, stride)[:, :width * 4].reshape(height, width, 4).copy()
            with self.owner.lock:
                stamp = self.owner.timestamp(sample)
                self.owner.latest = (frame, stamp)
                self.owner.timeline.add_video(frame, stamp)
        except Exception as error:
            self.owner.error = str(error)
        finally:
            Q.CVPixelBufferUnlockBaseAddress(pixel, Q.kCVPixelBufferLock_ReadOnly)


class Capture:
    def __init__(self):
        self.stream = None
        self.output = None
        self.latest = None
        self.lock = threading.Lock()
        self.error = None
        self.label = None
        self.timeline = MediaTimeline()
        self.host_offset = time.monotonic() - CM.CMTimeGetSeconds(CM.CMClockGetTime(CM.CMClockGetHostTimeClock()))

    def timestamp(self, sample):
        return CM.CMTimeGetSeconds(CM.CMSampleBufferGetPresentationTimeStamp(sample)) + self.host_offset

    async def content(self):
        initialize_macos()
        if not Q.CGPreflightScreenCaptureAccess():
            Q.CGRequestScreenCaptureAccess()
            raise RuntimeError('Разрешите запись экрана для Terminal (или приложения, из которого запущен сервер) в Системных настройках → Конфиденциальность и безопасность → Запись экрана. Затем перезапустите сервер.')
        return await completion(lambda cb: SC.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True, True, cb))

    async def sources(self):
        content = await self.content()
        return ([{'id': f'display:{d.displayID()}', 'kind': 'display', 'index': i+1, 'width': d.width(), 'height': d.height(), 'name': f'Экран {i+1} · {d.width()}×{d.height()}'} for i, d in enumerate(content.displays())] +
                [{'id': f'window:{w.windowID()}', 'kind': 'window', 'app': str(w.owningApplication().applicationName()) if w.owningApplication() else None, 'title': str(w.title()) if w.title() else None, 'name': f'{w.owningApplication().applicationName() if w.owningApplication() else "Окно"} — {w.title() or "Без названия"}'}
                 for w in content.windows() if w.frame().size.width > 80 and w.frame().size.height > 80])

    async def start(self, source, width=1280, fps=24):
        kind, ident = source.split(':')
        content = await self.content()
        if kind == 'display':
            target = next((d for d in content.displays() if d.displayID() == int(ident)), None)
            if target is None:
                raise ValueError('Экран больше недоступен')
            filt = SC.SCContentFilter.alloc().initWithDisplay_excludingWindows_(target, [])
            w, h = target.width(), target.height()
        elif kind == 'window':
            target = next((w for w in content.windows() if w.windowID() == int(ident)), None)
            if target is None:
                raise ValueError('Окно больше недоступно. Обновите список.')
            filt = SC.SCContentFilter.alloc().initWithDesktopIndependentWindow_(target)
            w, h = target.frame().size.width, target.frame().size.height
        else:
            raise ValueError('Неизвестный источник')
        await self.stop()
        config = SC.SCStreamConfiguration.alloc().init()
        scale = min(1, width / w)
        config.setWidth_(max(2, int(w * scale) // 2 * 2))
        config.setHeight_(max(2, int(h * scale) // 2 * 2))
        config.setPixelFormat_(Q.kCVPixelFormatType_32BGRA)
        config.setMinimumFrameInterval_(CM.CMTimeMake(1, fps))
        config.setQueueDepth_(3)
        config.setShowsCursor_(True)
        config.setCapturesAudio_(True)
        config.setSampleRate_(48000)
        config.setChannelCount_(2)
        config.setExcludesCurrentProcessAudio_(True)
        self.output = Output.alloc().init()
        self.output.owner = self
        self.stream = SC.SCStream.alloc().initWithFilter_configuration_delegate_(filt, config, self.output)
        try:
            for kind in (SC.SCStreamOutputTypeScreen, SC.SCStreamOutputTypeAudio):
                ok, error = self.stream.addStreamOutput_type_sampleHandlerQueue_error_(self.output, kind, None, None)
                if not ok:
                    raise RuntimeError(str(error))
            await completion(self.stream.startCaptureWithCompletionHandler_)
            for _ in range(100):
                if self.latest is not None:
                    self.label = source
                    return
                await asyncio.sleep(.1)
            raise RuntimeError(self.error or 'Нет кадров. Проверьте разрешение записи экрана; окно должно быть открыто.')
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        if self.stream:
            stream, self.stream = self.stream, None
            try:
                await completion(stream.stopCaptureWithCompletionHandler_)
            finally:
                self.latest = None
                self.label = None
                self.output = None
                with self.lock:
                    self.timeline.clear()
        self.error = None
