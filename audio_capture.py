"""Copy native PCM safely; retain bounded audio history for independent viewers."""
import numpy as np
import CoreAudio as CA
import CoreMedia as CM


def pcm_from_sample(sample):
    desc = CM.CMAudioFormatDescriptionGetStreamBasicDescription(CM.CMSampleBufferGetFormatDescription(sample))
    if desc.mFormatID != CA.kAudioFormatLinearPCM or desc.mSampleRate != 48000 or desc.mChannelsPerFrame != 2:
        raise RuntimeError('Ожидался PCM 48 кГц, стерео от ScreenCaptureKit')
    planar = bool(desc.mFormatFlags & CA.kAudioFormatFlagIsNonInterleaved)
    floating = bool(desc.mFormatFlags & CA.kAudioFormatFlagIsFloat)
    if floating and desc.mBitsPerChannel == 32:
        dtype = np.dtype('>f4' if desc.mFormatFlags & CA.kAudioFormatFlagIsBigEndian else '<f4')
    elif desc.mBitsPerChannel == 16 and desc.mFormatFlags & CA.kAudioFormatFlagIsSignedInteger:
        dtype = np.dtype('>i2' if desc.mFormatFlags & CA.kAudioFormatFlagIsBigEndian else '<i2')
    else:
        raise RuntimeError('Неподдерживаемый PCM-формат ScreenCaptureKit')
    count = CM.CMSampleBufferGetNumSamples(sample)
    buffers = CA.AudioBufferList(2 if planar else 1)
    for buffer in buffers:
        buffer.mNumberChannels = 1 if planar else 2
        buffer.create_buffer(count * dtype.itemsize * buffer.mNumberChannels)
    status = CM.CMSampleBufferCopyPCMDataIntoAudioBufferList(sample, 0, count, buffers)
    if status:
        raise RuntimeError(f'Ошибка копирования аудио PCM: {status}')
    if planar:
        pcm = np.stack([np.frombuffer(b.mData, dtype=dtype, count=count) for b in buffers], axis=1)
    else:
        pcm = np.frombuffer(buffers[0].mData, dtype=dtype, count=count * 2).reshape(-1, 2)
    if floating:
        pcm = (np.clip(np.nan_to_num(pcm), -1, 1) * 32767).astype(np.int16)
    return np.ascontiguousarray(pcm, dtype=np.int16)

