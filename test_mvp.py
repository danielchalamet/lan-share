"""Integration checks: real H.264 WebRTC loopback, HTTP Range, authorization."""
import asyncio
import pathlib
import tempfile
import threading
import unittest
import time
import numpy as np
from aiohttp.test_utils import TestClient, TestServer
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription
from server import create_app, SystemAudioTrack
from audio_capture import pcm_from_sample
from playout import MediaTimeline, PlayoutClock

async def cancel_task(task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

class FakeCapture:
    def __init__(self):
        self.label='display:1'
        self.error=None
        self.timeline=MediaTimeline()
        import CoreMedia as CM
        self.host_offset=time.monotonic()-CM.CMTimeGetSeconds(CM.CMClockGetTime(CM.CMClockGetHostTimeClock()))
        self.lock=threading.Lock()
        self.latest=(np.full((360,640,4),128,dtype=np.uint8),time.monotonic())
        self.timeline.add_video(self.latest[0],time.monotonic()-.6)
    def timestamp(self,sample):
        from capture import Capture
        return Capture.timestamp(self,sample)
    async def stop(self):
        self.label=None
        self.latest=None

def native_audio_sample(planar=True, timestamp=0):
    import CoreAudio as A
    import CoreMedia as C
    flags = A.kAudioFormatFlagIsFloat | A.kAudioFormatFlagIsPacked
    if planar:
        flags |= A.kAudioFormatFlagIsNonInterleaved
    size = 4 if planar else 8
    desc = A.AudioStreamBasicDescription(48000, A.kAudioFormatLinearPCM, flags, size, 1, size, 2, 32, 0)
    status, fmt = C.CMAudioFormatDescriptionCreate(None, desc, 0, None, 0, None, None, None)
    assert status == 0
    timing = C.CMSampleTimingInfo(C.CMTimeMake(1,48000), C.CMTimeMake(round(timestamp*48000),48000), C.kCMTimeInvalid)
    status, sample = C.CMSampleBufferCreate(None,None,False,None,None,fmt,960,1,[timing],0,[],None)
    assert status == 0
    samples = np.stack([.25*np.sin(2*np.pi*440*np.arange(960)/48000), .5*np.sin(2*np.pi*660*np.arange(960)/48000)],axis=1).astype(np.float32)
    buffers = A.AudioBufferList(2 if planar else 1)
    for i,b in enumerate(buffers):
        b.mNumberChannels = 1 if planar else 2
        b.create_buffer(960*4*b.mNumberChannels)
        np.frombuffer(b.mData,dtype=np.float32)[:] = samples[:,i] if planar else samples.reshape(-1)
    assert C.CMSampleBufferSetDataBufferFromAudioBufferList(sample,None,None,0,buffers) == 0
    return sample, (samples * 32767).astype(np.int16)

class TimelineTests(unittest.TestCase):
    def test_jittered_arrivals_use_capture_time_for_both_tracks(self):
        timeline=MediaTimeline()
        old=np.zeros((2,2,4),dtype=np.uint8)
        new=np.ones((2,2,4),dtype=np.uint8)
        # Video arrives first, matching audio arrives later, before playout.
        timeline.add_video(old,10.0)
        timeline.add_video(new,10.2)
        pcm=np.full((960,2),1234,dtype=np.int16)
        timeline.add_audio(pcm,10.2)
        clock=PlayoutClock(.3,now=10.5)
        target=clock.source_time(0,50)
        self.assertAlmostEqual(target,10.2)
        np.testing.assert_array_equal(timeline.video_at(target),new)
        np.testing.assert_array_equal(timeline.audio_at(target),pcm)
        np.testing.assert_array_equal(timeline.audio_at(10.22),np.zeros((960,2)))
        np.testing.assert_array_equal(timeline.video_at(10.1),old)

    def test_partial_audio_gap_keeps_sample_positions(self):
        timeline=MediaTimeline()
        timeline.add_audio(np.full((480,2),99,dtype=np.int16),5.01)
        frame=timeline.audio_at(5)
        self.assertTrue(np.all(frame[:480]==0))
        self.assertTrue(np.all(frame[480:]==99))

    def test_stall_catches_up_without_clock_drift_and_memory_is_bounded(self):
        clock=PlayoutClock(.3,now=0)
        for now in (.01,.1,.9,10,600):
            video=clock.tick(-1,24,now)
            audio=clock.tick(-1,50,now)
            self.assertLessEqual(abs(clock.source_time(video,24)-clock.source_time(audio,50)),1/24)
        timeline=MediaTimeline()
        for i in range(1000):
            timeline.add_video(np.zeros((1,1,4),dtype=np.uint8),i/24)
            timeline.add_audio(np.zeros((960,2),dtype=np.int16),i/50)
        self.assertEqual(len(timeline.video),24)
        self.assertEqual(len(timeline.audio),200)

class ConnectionTests(unittest.TestCase):
    def test_key_survives_restart_and_qr_renders(self):
        from connection import persistent_key, print_phone_qr
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / '.access-key'
            first = persistent_key(path)
            self.assertEqual(first, persistent_key(path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            output = StringIO()
            with redirect_stdout(output):
                print_phone_qr('http://test-mac.local:8080/#' + first)
            self.assertGreater(len(output.getvalue().splitlines()), 15)
            path.write_text('broken')
            with self.assertRaises(RuntimeError):
                persistent_key(path)

class NativeBridge(unittest.TestCase):
    def test_native_audio_planar_and_interleaved(self):
        for planar in (True,False):
            sample, expected = native_audio_sample(planar)
            np.testing.assert_array_equal(pcm_from_sample(sample), expected)

    def test_sample_buffer_to_pixels(self):
        import Quartz as Q
        import CoreMedia as CM
        from capture import Capture, Output
        status, pixel = Q.CVPixelBufferCreate(None, 64, 32, Q.kCVPixelFormatType_32BGRA, None, None)
        self.assertEqual(status, 0)
        Q.CVPixelBufferLockBaseAddress(pixel, 0)
        try:
            size = Q.CVPixelBufferGetBytesPerRow(pixel) * 32
            buffer = np.frombuffer(Q.CVPixelBufferGetBaseAddress(pixel).as_buffer(size), dtype=np.uint8)
            buffer[:] = 127
        finally:
            Q.CVPixelBufferUnlockBaseAddress(pixel, 0)
        status, fmt = CM.CMVideoFormatDescriptionCreateForImageBuffer(None, pixel, None)
        self.assertEqual(status, 0)
        timing = CM.CMSampleTimingInfo(CM.CMTimeMake(1, 24), CM.kCMTimeZero, CM.kCMTimeInvalid)
        status, sample = CM.CMSampleBufferCreateReadyWithImageBuffer(None, pixel, fmt, timing, None)
        self.assertEqual(status, 0)
        output = Output.alloc().init()
        output.owner = Capture()
        output.stream_didOutputSampleBuffer_ofType_(None, sample, 0)
        self.assertIsNone(output.owner.error)
        self.assertEqual(output.owner.latest[0].shape, (32, 64, 4))
        self.assertTrue(np.all(output.owner.latest[0] == 127))

class Integration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.directory.name)
        (self.path/'episode.mp4').write_bytes(bytes(range(256))*16)
        (self.path/'private.txt').write_text('private')
        (self.path/'escape.mp4').symlink_to('/etc/hosts')
        self.capture=FakeCapture()
        self.client=TestClient(TestServer(create_app(self.path,self.capture,'test-secret')))
        await self.client.start_server()
        self.headers={'Authorization':'Bearer test-secret'}
    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()
    async def test_files_and_auth(self):
        response=await self.client.get('/api/status')
        self.assertEqual(response.status,401)
        response=await self.client.get('/api/files',headers=self.headers)
        files=await response.json()
        self.assertEqual([f['name'] for f in files],['episode.mp4'])
        media_url='/media/'+files[0]['id']+'?key=test-secret'
        response=await self.client.get(media_url,headers={'Range':'bytes=100-199'})
        self.assertEqual(response.status,206)
        self.assertEqual(response.headers['Content-Range'],'bytes 100-199/4096')
        self.assertEqual(await response.read(),bytes(range(100,200)))
        response=await self.client.head(media_url)
        self.assertEqual(response.status,200)
        self.assertEqual(response.headers['Content-Length'],'4096')
        response=await self.client.get('/media/escape.mp4?key=test-secret')
        self.assertEqual(response.status,404)
        response=await self.client.get('/media/private.txt?key=test-secret')
        self.assertEqual(response.status,404)
    async def test_remote_viewer_cannot_browse_or_change_files(self):
        from aiohttp.test_utils import make_mocked_request
        from aiohttp import web
        from unittest.mock import Mock
        transport=Mock()
        transport.get_extra_info.return_value=('192.168.0.50',45678)
        app=self.client.server.app
        for path in ('/api/media/browse','/api/media/add','/api/media/remove'):
            request=make_mocked_request('POST',path,headers=self.headers,transport=transport,app=app)
            match=await app.router.resolve(request)
            with self.assertRaises(web.HTTPForbidden):
                await match.handler(request)

    async def test_add_remove_media_while_running(self):
        new_file=self.path/'music.m4a'
        new_file.write_bytes(b'123456')
        response=await self.client.post('/api/media/browse',headers=self.headers,json={'path':str(self.path)})
        self.assertEqual(response.status,200)
        self.assertIn('music.m4a',[e['name'] for e in (await response.json())['entries']])
        response=await self.client.post('/api/media/add',headers=self.headers,json={'paths':[str(new_file)]})
        self.assertEqual(response.status,200)
        entry=next(f for f in await response.json() if f['name']=='music.m4a')
        self.assertNotIn('path',entry)
        url='/media/'+entry['id']+'?key=test-secret'
        response=await self.client.get(url)
        self.assertEqual(await response.read(),b'123456')
        response=await self.client.post('/api/media/remove',headers=self.headers,json={'id':entry['id']})
        self.assertEqual(response.status,200)
        self.assertEqual((await self.client.get(url)).status,404)
        self.assertTrue(new_file.exists())
        response=await self.client.post('/api/media/add',headers=self.headers,json={'paths':[str(self.path/'escape.mp4')]})
        self.assertEqual(response.status,400)

    async def test_h264_webrtc_frame(self):
        pc=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        frame_future=asyncio.get_running_loop().create_future()
        audio_future=asyncio.get_running_loop().create_future()
        @pc.on('track')
        def track_received(track):
            async def receive():
                try:
                    frame = await track.recv()
                    if track.kind == 'audio':
                        for _ in range(20):
                            if np.max(np.abs(frame.to_ndarray().astype(np.float32))) > 100:
                                break
                            frame = await track.recv()
                        audio_future.set_result(frame)
                    else:
                        frame_future.set_result(frame)
                except Exception as e:
                    if not frame_future.done(): frame_future.set_exception(e)
            asyncio.create_task(receive())
        try:
            pc.addTransceiver('video',direction='recvonly')
            pc.addTransceiver('audio',direction='recvonly')
            await pc.setLocalDescription(await pc.createOffer())
            response=await self.client.post('/api/offer',headers=self.headers,json={'sdp':pc.localDescription.sdp})
            self.assertEqual(response.status,200,await response.text())
            answer=await response.json()
            self.assertIn('H264',answer['sdp'])
            self.assertIn('opus/48000/2',answer['sdp'])
            await pc.setRemoteDescription(RTCSessionDescription(**answer))
            from capture import Output
            import ScreenCaptureKit as SC
            output = Output.alloc().init()
            output.owner = self.capture
            async def feed():
                for _ in range(100):
                    sample, _ = native_audio_sample(timestamp=time.monotonic()-self.capture.host_offset)
                    output.stream_didOutputSampleBuffer_ofType_(None,sample,SC.SCStreamOutputTypeAudio)
                    await asyncio.sleep(.02)
            feed_task = asyncio.create_task(feed())
            self.addAsyncCleanup(cancel_task, feed_task)
            frame=await asyncio.wait_for(frame_future,15)
            audio=await asyncio.wait_for(audio_future,15)
            self.assertEqual(audio.sample_rate,48000)
            self.assertGreater(np.max(np.abs(audio.to_ndarray().astype(np.float32))),100)
            self.assertIsNone(self.capture.error)
            self.assertEqual((frame.width,frame.height),(640,360))
        finally:
            await pc.close()

if __name__=='__main__':
    unittest.main(verbosity=2)
