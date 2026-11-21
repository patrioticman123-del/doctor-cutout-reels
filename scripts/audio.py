"""Speech, measured timing, original procedural score, and deterministic mixing."""
from array import array
import asyncio
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import wave

RATE = 24000
DEFAULT_PACING = {"speech_speed":1.08,"lead_in":0.03,"trim_silence":True}


def pacing_settings(episode):
    settings=episode.get("pacing",{})
    if not isinstance(settings,dict) or any(key not in DEFAULT_PACING for key in settings):
        raise ValueError("pacing accepts speech_speed, lead_in and trim_silence")
    result={**DEFAULT_PACING,**settings}
    for key,low,high in (("speech_speed",.8,1.3),("lead_in",0,.2)):
        value=result[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f"pacing.{key} must be {low}–{high}")
    if not isinstance(result["trim_silence"],bool):
        raise ValueError("pacing.trim_silence must be true or false")
    return result


def default_hold(scene):
    if scene.get("intent")=="closing":
        return .5
    if scene.get("beat")=="punch":
        return .25
    return .12 if scene.get("intent")=="question" else .1


def trim_edges(samples):
    """Remove only leading/trailing quiet, retaining breath/consonant margins."""
    peak=max((abs(v) for v in samples),default=0)
    threshold=max(45,peak*.004)
    block=RATE//100
    voiced=[i for i in range(0,len(samples),block)
            if max((abs(v) for v in samples[i:i+block]),default=0)>=threshold]
    if not voiced:
        raise ValueError("Speech audio is silent after processing")
    keep=round(RATE*.025)
    start=max(0,voiced[0]-keep)
    end=min(len(samples),voiced[-1]+block+keep)
    return samples[start:end]


def command(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:] or result.stdout[-3000:])
    return result


def read_wav(path):
    with wave.open(str(path), "rb") as f:
        if (f.getnchannels(), f.getsampwidth(), f.getframerate()) != (1, 2, RATE):
            raise ValueError(f"Expected mono PCM16 {RATE}Hz: {path}")
        samples = array("h", f.readframes(f.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or max(abs(v) for v in samples) < 20:
        raise ValueError(f"Empty or silent speech audio: {path}")
    return samples


def write_wav(path, values):
    samples = array("h", (int(max(-32767, min(32767, v))) for v in values))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        f.writeframes(samples.tobytes())


def speech(scene, episode, backend, source_dir, audio_dir, ffmpeg):
    speaker = scene["speaker"]
    voice = episode["voices"][speaker].get(backend, "")
    pacing=pacing_settings(episode)
    provider_rate=None if backend=="files" else ((1 if speaker=="alo" else 0) if backend=="sapi" else ("+8%" if speaker=="alo" else "+0%"))
    fingerprint = {"text": scene["text"], "voice": voice, "backend": backend,
                   "provider_rate":provider_rate,"speech_speed":pacing["speech_speed"],
                   "trim_silence":pacing["trim_silence"],"v":3}
    source = None
    if backend == "files":
        if not scene.get("audio"):
            raise ValueError("--voice files requires an audio path for EVERY scene")
        source = (source_dir / scene["audio"]).resolve()
        fingerprint["source_hash"] = hashlib.sha256(source.read_bytes()).hexdigest()
    key = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False).encode()).hexdigest()[:20]
    wav = audio_dir / f"{key}.wav"
    if wav.exists():
        return read_wav(wav)
    if backend == "sapi":
        if sys.platform != "win32":
            raise ValueError("SAPI requires Windows. Use --voice edge or --voice files.")
        request = audio_dir / f"{key}.json"
        request.write_text(json.dumps({"text": scene["text"], "voice": voice,
                                      "out": str(wav.with_suffix('.raw.wav').resolve()),
                                      "rate": provider_rate}, ensure_ascii=False),
                           encoding="utf-8")
        command([shutil.which("pwsh") or "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", Path(__file__).with_name("speak.ps1"), request.resolve()])
        source = wav.with_suffix(".raw.wav")
    elif backend == "edge":
        import edge_tts
        source = wav.with_suffix(".mp3")
        async def synthesize():
            await edge_tts.Communicate(scene["text"], voice,
                                       rate=provider_rate).save(str(source))
        try:
            asyncio.run(synthesize())
        except Exception as exc:
            raise RuntimeError(f"Edge TTS failed for {speaker}: {exc}. Retry or select --voice sapi/files.") from exc
    elif backend != "files":
        raise ValueError(f"Unknown speech backend: {backend}")
    tempo=[] if pacing["speech_speed"]==1 else ["-af",f"atempo={pacing['speech_speed']}"]
    command([ffmpeg, "-y", "-v", "error", "-i", source, *tempo,
             "-ac", "1", "-ar", str(RATE),
             "-c:a", "pcm_s16le", wav])
    samples=read_wav(wav)
    if pacing["trim_silence"]:
        samples=trim_edges(samples)
        write_wav(wav,samples)
    return samples


def normalize(samples):
    peak = max(abs(v) for v in samples)
    gain = min(3.0, 23000 / max(peak, 1))
    return array("h", (int(v * gain) for v in samples))


def envelope(samples, fps=24):
    step = max(1, RATE // fps)
    return [min(1.0, math.sqrt(sum(v * v for v in samples[i:i+step]) / max(1, len(samples[i:i+step]))) / 4500)
            for i in range(0, len(samples), step)]


def score(duration, timeline):
    """An original plucked pentatonic riff, bass and soft noise percussion."""
    n = math.ceil(duration * RATE)
    music = array("f", [0.0]) * n
    rng = random.Random(347)
    beat = 60 / 116
    notes = [60, 67, 69, 64, 67, 62, 64, 55]
    for k in range(math.ceil(duration / (beat / 2))):
        start = round(k * beat / 2 * RATE)
        frequency = 440 * 2 ** ((notes[k % len(notes)] - 69) / 12)
        for j in range(min(int(RATE * .22), n - start)):
            t = j / RATE
            music[start+j] += 2300 * math.exp(-t * 19) * (math.sin(2*math.pi*frequency*t) + .25*math.sin(4*math.pi*frequency*t))
        if k % 2 == 0:
            for j in range(min(int(RATE * .13), n-start)):
                t = j / RATE
                music[start+j] += 1400 * math.exp(-t * 34) * math.sin(2*math.pi*(85*t-110*t*t))
        if k % 2:
            for j in range(min(int(RATE * .035), n-start)):
                music[start+j] += rng.uniform(-650, 650) * math.exp(-j / RATE * 100)
    for scene in timeline:
        lo, hi = int(scene["start"]*RATE), min(n, int(scene["end"]*RATE))
        speech_start, speech_end = scene["voice_start"], scene["voice_end"]
        for i in range(lo, hi):
            t = i / RATE
            # Smooth 80ms duck before speech, 180ms recovery after it.
            active = max(0.0, min(1.0, (t-(speech_start-.08))/.08,
                                  (speech_end+.18-t)/.18))
            gain = 1 - .7 * active
            if scene["beat"] == "punch" and t >= speech_end:
                gain *= .06
            music[i] *= gain * min(1, t / .2, max(0, (duration-t)/.5))
    return music


def assemble(episode, backend, source_dir, out, ffmpeg, fps):
    pacing=pacing_settings(episode)
    folder = out / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    timeline, segments, cursor = [], [], 0.0
    for index, scene in enumerate(episode["scenes"]):
        print(f"Speech {index+1}/{len(episode['scenes'])}: {scene['speaker']}", flush=True)
        samples = normalize(speech(scene, episode, backend, source_dir, folder, ffmpeg))
        length = len(samples) / RATE
        lead=pacing["lead_in"]
        hold=scene.get("hold",default_hold(scene))
        end = math.ceil((cursor + lead + length + hold) * fps) / fps
        item = dict(scene, hold=hold,start=cursor, end=end, voice_start=cursor+lead,
                    voice_end=cursor+lead+length, envelope=envelope(samples, fps), index=index)
        timeline.append(item)
        segments.append((round(item["voice_start"]*RATE), samples))
        cursor = end
    voice = array("f", [0]) * math.ceil(cursor * RATE)
    for offset, samples in segments:
        for j, v in enumerate(samples):
            voice[offset+j] += v
    music = score(cursor, timeline)
    write_wav(out / "voice.wav", voice)
    write_wav(out / "music.wav", music)
    write_wav(out / "mix.wav", (max(-30000, min(30000, v+m)) for v, m in zip(voice, music)))
    return timeline, cursor
