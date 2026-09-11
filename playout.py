"""Bounded source-time buffers and a common playout clock for audio/video."""
import asyncio
import time
from collections import deque
import numpy as np


class MediaTimeline:
    # At most ~90 MB of 1280×720 BGRA; enough for the largest 500 ms buffer.
    def __init__(self):
        self.video = deque(maxlen=24)
        self.audio = deque(maxlen=200)

    def add_video(self, pixels, timestamp):
        self.video.append((timestamp, pixels))

    def add_audio(self, pcm, timestamp):
        self.audio.append((round(timestamp * 48000), pcm))

    def video_at(self, timestamp):
        for stamp, pixels in reversed(self.video):
            if stamp <= timestamp:
                return pixels
        return None

    def audio_at(self, timestamp, count=960):
        start = round(timestamp * 48000)
        end = start + count
        result = np.zeros((count, 2), dtype=np.int16)
        for stamp, pcm in self.audio:
            lo, hi = max(start, stamp), min(end, stamp + len(pcm))
            if hi > lo:
                result[lo-start:hi-start] = pcm[lo-stamp:hi-stamp]
        return result

    def clear(self):
        self.video.clear()
        self.audio.clear()


class PlayoutClock:
    def __init__(self, delay=.3, now=None):
        self.epoch = time.monotonic() if now is None else now
        self.delay = delay

    def tick(self, previous, rate, now):
        # Keep a fixed cadence instead of adding encode time to each frame period.
        return max(previous + 1, int(max(0, now - self.epoch) * rate))

    async def wait(self, previous, rate):
        tick = self.tick(previous, rate, time.monotonic())
        await asyncio.sleep(max(0, self.epoch + tick / rate - time.monotonic()))
        return tick

    def source_time(self, tick, rate):
        return self.epoch + tick / rate - self.delay
