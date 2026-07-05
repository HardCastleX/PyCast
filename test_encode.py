import soundcard as sc
import numpy as np
import lameenc

try:
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(44100)
    encoder.set_channels(2)
    encoder.set_quality(2)

    speaker = sc.default_speaker()
    mics = sc.all_microphones(include_loopback=True)
    loopback = None
    for m in mics:
        if str(speaker.id) == str(m.id):
            loopback = m
            break
            
    with loopback.recorder(samplerate=44100, channels=2) as mic:
        data = mic.record(numframes=1024)
        pcm_data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        # lameenc expects interleaved stereo as bytes
        mp3_data = encoder.encode(pcm_data.tobytes())
        print("MP3 data size:", len(mp3_data))
        print("Success!")
except Exception as e:
    print("Error:", e)
