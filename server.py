#!/usr/bin/env python3
import argparse
import asyncio
import fractions
import ipaddress
import pathlib
import secrets
from aiohttp import web
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack, RTCRtpSender
from av import VideoFrame, AudioFrame
from capture import Capture, initialize_macos
from translations import LANGUAGES, translate
from playout import PlayoutClock
from media_library import MediaLibrary
from connection import persistent_key, phone_addresses, print_phone_qr

ROOT = pathlib.Path(__file__).resolve().parent
TOKEN = web.AppKey('token', str)
TIMERS = web.AppKey('timers', set)


class ScreenTrack(VideoStreamTrack):
    def __init__(self, capture, clock):
        super().__init__()
        self.capture, self.clock = capture, clock
        self.tick = -1

    async def recv(self):
        from aiortc.mediastreams import MediaStreamError
        while self.capture.label:
            self.tick = await self.clock.wait(self.tick, 24)
            with self.capture.lock:
                pixels = self.capture.timeline.video_at(self.clock.source_time(self.tick, 24))
            if pixels is None:
                continue
            frame = VideoFrame.from_ndarray(pixels, format='bgra')
            frame.pts = self.tick * 3750
            frame.time_base = fractions.Fraction(1, 90000)
            return frame
        raise MediaStreamError


class SystemAudioTrack(AudioStreamTrack):
    def __init__(self, capture, clock):
        super().__init__()
        self.capture, self.clock = capture, clock
        self.tick = -1

    async def recv(self):
        from aiortc.mediastreams import MediaStreamError
        if not self.capture.label:
            raise MediaStreamError
        self.tick = await self.clock.wait(self.tick, 50)
        with self.capture.lock:
            samples = self.capture.timeline.audio_at(self.clock.source_time(self.tick, 50))
        frame = AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='stereo')
        frame.sample_rate = 48000
        frame.pts = self.tick * 960
        frame.time_base = fractions.Fraction(1, 48000)
        return frame


def create_app(media_dir=None, capture=None, token=None):
    capture = capture or Capture()
    token = token or secrets.token_urlsafe(24)
    peers = set()
    lock = asyncio.Lock()
    library = MediaLibrary(media_dir)

    @web.middleware
    async def auth(request, handler):
        if request.path not in ('/', '/client.js', '/style.css', '/i18n.js', '/locales.json'):
            supplied = request.headers.get('Authorization', '').removeprefix('Bearer ') or request.query.get('key', '')
            if not secrets.compare_digest(supplied, token):
                raise web.HTTPUnauthorized(text='Откройте полную ссылку из Terminal.')
        try:
            response = await handler(request)
        except (ValueError, RuntimeError, asyncio.TimeoutError) as error:
            response = web.json_response({'error': str(error) or 'Истекло время ожидания macOS'}, status=400)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    app = web.Application(middlewares=[auth], client_max_size=128*1024)
    app[TOKEN] = token

    def local(request):
        if not request.remote or not ipaddress.ip_address(request.remote).is_loopback:
            raise web.HTTPForbidden(text='Источник выбирается только на Mac: откройте localhost.')

    async def close_peers():
        await asyncio.gather(*(pc.close() for pc in list(peers)), return_exceptions=True)
        peers.clear()

    async def static(request):
        name = request.match_info.get('name', 'index.html')
        return web.FileResponse(ROOT / 'static' / name)

    async def status(request):
        return web.json_response({'source': capture.label, 'error': capture.error,
            'local': bool(request.remote and ipaddress.ip_address(request.remote).is_loopback),
            'viewers': len(peers)})

    async def sources(request):
        local(request)
        return web.json_response(await capture.sources())

    async def start(request):
        local(request)
        body = await request.json()
        async with lock:
            await close_peers()
            await capture.start(body.get('source', ''), width=1280, fps=24)
        return web.json_response({'ok': True})

    async def stop(request):
        local(request)
        async with lock:
            await close_peers()
            await capture.stop()
        return web.json_response({'ok': True})

    async def offer(request):
        body = await request.json()
        async with lock:
            if not capture.label:
                raise ValueError('Сначала выберите и включите источник на Mac.')
            if len(peers) >= 3:
                raise ValueError('Уже подключено 3 зрителя. Закройте лишние подключения.')
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            peers.add(pc)
            @pc.on('connectionstatechange')
            async def changed():
                if pc.connectionState in ('failed', 'closed'):
                    peers.discard(pc)
                    if pc.connectionState != 'closed':
                        await pc.close()
            try:
                await pc.setRemoteDescription(RTCSessionDescription(sdp=body['sdp'], type='offer'))
                delay_ms = body.get("buffer_ms", 300)
                if delay_ms not in (150, 300, 500):
                    raise ValueError("Буфер: 150, 300 или 500 мс")
                clock = PlayoutClock(delay_ms / 1000)
                sender = pc.addTrack(ScreenTrack(capture, clock))
                if any(t.kind == "audio" for t in pc.getTransceivers()):
                    pc.addTrack(SystemAudioTrack(capture, clock))
                for transceiver in pc.getTransceivers():
                    if transceiver.sender == sender:
                        transceiver.setCodecPreferences([c for c in RTCRtpSender.getCapabilities('video').codecs if c.mimeType == 'video/H264'])
                await pc.setLocalDescription(await pc.createAnswer())
                async def expire():
                    await asyncio.sleep(30)
                    if pc.connectionState != 'connected':
                        await pc.close()
                        peers.discard(pc)
                task = asyncio.create_task(expire())
                app[TIMERS].add(task)
                task.add_done_callback(app[TIMERS].discard)
                return web.json_response({'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type})
            except BaseException:
                peers.discard(pc)
                await pc.close()
                raise

    async def listing(request):
        return web.json_response(library.listing())

    async def browse(request):
        local(request)
        body = await request.json()
        return web.json_response(await asyncio.to_thread(library.browse, body.get('path')))

    async def add_files(request):
        local(request)
        body = await request.json()
        paths = body.get('paths')
        if not isinstance(paths, list) or not paths or len(paths) > 500 or not all(isinstance(p, str) for p in paths):
            raise ValueError('Выберите от 1 до 500 файлов')
        library.add(paths)
        return web.json_response(library.listing())

    async def remove_file(request):
        local(request)
        body = await request.json()
        library.files.pop(body.get('id'), None)
        return web.json_response(library.listing())

    async def file(request):
        path = library.resolve(request.match_info['name'])
        if path is None:
            raise web.HTTPNotFound()
        response = web.FileResponse(path)
        if path.suffix.lower() in {'.mp4', '.m4v'}:
            response.content_type = 'video/mp4'
        return response

    async def cleanup(app):
        for task in app[TIMERS]:
            task.cancel()
        await close_peers()
        await capture.stop()

    app[TIMERS] = set()
    app.on_cleanup.append(cleanup)
    app.router.add_get('/', static)
    app.router.add_get('/{name:client.js|style.css|i18n.js|locales.json}', static)
    app.router.add_get('/api/status', status)
    app.router.add_get('/api/sources', sources)
    app.router.add_post('/api/start', start)
    app.router.add_post('/api/stop', stop)
    app.router.add_post('/api/offer', offer)
    app.router.add_get('/api/files', listing)
    app.router.add_post('/api/media/browse', browse)
    app.router.add_post('/api/media/add', add_files)
    app.router.add_post('/api/media/remove', remove_file)
    app.router.add_get('/media/{name}', file)
    return app


def main():
    parser = argparse.ArgumentParser(description='Local Mac screen/window sharing to Safari')
    parser.add_argument('--media', type=pathlib.Path, help='Only video files directly in this folder are shared')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--lang', choices=LANGUAGES, default='ru', help='Terminal language (web language is selected in the browser)')
    args = parser.parse_args()
    tr = lambda message: translate(message, args.lang)
    if args.media and not args.media.is_dir():
        parser.error('--media must be an existing directory')
    initialize_macos()
    app = create_app(args.media, token=persistent_key(ROOT / '.access-key'))
    print(f'\n{tr("Управление на Mac")}: http://localhost:{args.port}/#{app[TOKEN]}', flush=True)
    addresses = phone_addresses(args.port, app[TOKEN])
    for label, url in addresses:
        print(f'{tr(label)}: {url}', flush=True)
    if addresses:
        print_phone_qr(addresses[0][1], tr)
    print(tr('Сохраните ссылку в Safari: ключ сохраняется после перезапуска. Если .local не открывается, используйте запасную ссылку по IP.'), flush=True)
    print(tr('Ctrl+C — остановить. Окно/экран выбирается только на Mac. Трансляция со звуком приложения/системы.'), flush=True)
    web.run_app(app, host='0.0.0.0', port=args.port, access_log=None)

if __name__ == '__main__':
    main()
