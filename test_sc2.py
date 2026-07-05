import soundcard as sc

try:
    speaker = sc.default_speaker()
    mics = sc.all_microphones(include_loopback=True)
    loopback = None
    for m in mics:
        if str(speaker.id) == str(m.id):
            loopback = m
            break
    
    if not loopback:
        print("Loopback not found by ID. Trying by name...")
        for m in mics:
            if speaker.name in m.name:
                loopback = m
                break
                
    if not loopback:
        print("Loopback not found. Using default mic.")
        loopback = sc.default_microphone()

    print("Selected loopback:", loopback)
    print("Recording...")
    with loopback.recorder(samplerate=44100, channels=2) as mic:
        data = mic.record(numframes=1024)
        print("Data shape:", data.shape)
        print("Success!")
except Exception as e:
    print("Error:", e)
