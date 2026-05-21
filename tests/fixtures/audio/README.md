# Audio fixtures

These small WAVs are committed so the test suite never has to hit the network
to verify audio decoding + the full transcribe path.

| File              | Format                  | Notes                                                  |
|-------------------|-------------------------|--------------------------------------------------------|
| `silent_1s.wav`   | 16 kHz mono PCM, 1 s    | Pure silence — VAD should suppress to ≤ 1 segment.     |
| `tone_440hz_2s.wav` | 16 kHz mono PCM, 2 s | 440 Hz sine, 30% amplitude — exercises ffmpeg decode.  |

Regenerate with:

```python
import wave, struct, math
with wave.open('silent_1s.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b'\x00\x00' * 16000)
with wave.open('tone_440hz_2s.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    samples = bytearray()
    for i in range(32000):
        v = int(32767 * 0.3 * math.sin(2*math.pi*440*i/16000))
        samples.extend(struct.pack('<h', v))
    w.writeframes(bytes(samples))
```
