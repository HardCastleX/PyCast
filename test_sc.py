import soundcard as sc

try:
    speaker = sc.default_speaker()
    print("Speaker:", speaker)
    print("Recording from speaker...")
    with speaker.recorder(samplerate=44100, channels=2) as mic:
        data = mic.record(numframes=1024)
        print("Data shape:", data.shape)
        print("Success!")
except Exception as e:
    print("Error:", e)
