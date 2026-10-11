#!/usr/bin/env python3
"""Compose an original, tasteful product-ad score for demo90: pulse
percussion (kick + subtle hats), a restrained warm synth melody, and
cinematic riser/impact/whoosh/snap cues timed to the act boundaries in
segments.json. Synthesized entirely with numpy/scipy (no samples, no
copyrighted material). Ducks under the measured narration window.
"""
import json
from pathlib import Path

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "output" / "demo90"
AUDIO_DIR = DEMO_DIR / "audio"
SFX_DIR = AUDIO_DIR / "sfx"

SAMPLE_RATE = 48000
TOTAL_DURATION_S = 90.0
N = int(TOTAL_DURATION_S * SAMPLE_RATE)

DUCK_DB = -16.0
DUCK_FADE_S = 0.2
MIX_PEAK_DBFS = -14.0  # restrained, sits well under -3 dBFS voice peak

BEAT_S = 0.6  # 100 BPM


def db_to_amp(db):
    return 10.0 ** (db / 20.0)


def t_axis():
    return np.arange(N) / SAMPLE_RATE


def s2i(sec):
    return int(round(sec * SAMPLE_RATE))


def lowpass(x, cutoff_hz, order=2):
    sos = signal.butter(order, cutoff_hz, btype="low", fs=SAMPLE_RATE, output="sos")
    return signal.sosfilt(sos, x)


def highpass(x, cutoff_hz, order=2):
    sos = signal.butter(order, cutoff_hz, btype="high", fs=SAMPLE_RATE, output="sos")
    return signal.sosfilt(sos, x)


def bandpass(x, low_hz, high_hz, order=2):
    lo = max(low_hz, 20.0)
    hi = min(high_hz, SAMPLE_RATE / 2 - 100)
    if hi <= lo:
        hi = lo + 50.0
    sos = signal.butter(order, [lo, hi], btype="band", fs=SAMPLE_RATE, output="sos")
    return signal.sosfilt(sos, x)


def envelope_window(center_s, attack_s, decay_s, curve="exp"):
    t = t_axis()
    env = np.zeros(N)
    c = center_s
    mask_pre = (t >= c) & (t < c + attack_s)
    env[mask_pre] = (t[mask_pre] - c) / max(attack_s, 1e-6)
    mask_post = (t >= c + attack_s) & (t < c + attack_s + decay_s)
    frac = (t[mask_post] - (c + attack_s)) / max(decay_s, 1e-6)
    env[mask_post] = (1.0 - frac) ** 2 if curve == "exp" else (1.0 - frac)
    return np.clip(env, 0, 1)


def add_at(buf, center_s, chunk, pre_s=0.0):
    """Add a short local buffer `chunk` into the full-length `buf` at center_s - pre_s."""
    start = s2i(max(center_s - pre_s, 0))
    end = min(start + len(chunk), N)
    if end <= start:
        return
    buf[start:end] += chunk[: end - start]


# --------------------------------------------------------------------------
# Percussion
# --------------------------------------------------------------------------

def make_kick(amp=1.0, dur_s=0.22):
    n = s2i(dur_s)
    t = np.arange(n) / SAMPLE_RATE
    pitch = 95.0 * np.exp(-t / 0.035) + 48.0
    phase = 2 * np.pi * np.cumsum(pitch) / SAMPLE_RATE
    tone = np.sin(phase)
    click = highpass(np.random.default_rng(int(amp * 1e6) % 9999 + n).standard_normal(n), 2000.0)
    env = np.exp(-t / 0.09)
    click_env = np.exp(-t / 0.006)
    out = tone * env + click * click_env * 0.15
    return out * amp


def make_hat(amp=1.0, dur_s=0.045, open_hat=False):
    n = s2i(dur_s if not open_hat else dur_s * 2.2)
    rng = np.random.default_rng(int(amp * 1e7) % 9973 + n)
    noise = rng.standard_normal(n)
    noise = bandpass(noise, 6000.0, 15000.0, order=2)
    t = np.arange(n) / SAMPLE_RATE
    env = np.exp(-t / (0.012 if not open_hat else 0.05))
    return noise * env * amp


def make_snap(amp=1.0, dur_s=0.09):
    """Sharp transient for editorial-cut accents."""
    n = s2i(dur_s)
    rng = np.random.default_rng(int(amp * 1e8) % 7919 + n)
    noise = bandpass(rng.standard_normal(n), 1200.0, 6500.0, order=2)
    t = np.arange(n) / SAMPLE_RATE
    env = np.exp(-t / 0.018)
    chirp_f = 900.0 * np.exp(-t / 0.02) + 120.0
    chirp = np.sin(2 * np.pi * np.cumsum(chirp_f) / SAMPLE_RATE) * np.exp(-t / 0.03)
    return (noise * 0.7 + chirp * 0.5) * env * amp


# --------------------------------------------------------------------------
# Warm synth melody
# --------------------------------------------------------------------------

def make_synth_note(freq, dur_s, amp=1.0):
    n = s2i(dur_s)
    t = np.arange(n) / SAMPLE_RATE
    # triangle-ish wave (sum of odd harmonics) softened by a warm low-pass
    wave = np.zeros(n)
    for k, h in enumerate([1, 3, 5], start=0):
        wave += ((-1) ** k) / (h ** 2) * np.sin(2 * np.pi * freq * h * t)
    wave = lowpass(wave, 2200.0, order=2)
    attack_n = min(int(0.03 * SAMPLE_RATE), n // 4)
    release_n = min(int(dur_s * 0.6 * SAMPLE_RATE), n - attack_n)
    env = np.ones(n)
    if attack_n > 0:
        env[:attack_n] = np.linspace(0, 1, attack_n)
    if release_n > 0:
        env[-release_n:] = np.linspace(1, 0, release_n) ** 1.5
    wave = wave / (np.max(np.abs(wave)) + 1e-9)
    return wave * env * amp


# --------------------------------------------------------------------------
# Pad (chord bed, variable-length chords matched to act windows)
# --------------------------------------------------------------------------

def make_pad_segment(freqs, start_s, end_s, amp=1.0):
    dur = end_s - start_s
    n = s2i(dur)
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / SAMPLE_RATE
    seg = np.zeros(n)
    for f in freqs:
        detune = 1.0 + 0.0015 * np.sin(2 * np.pi * 0.07 * t + f)
        seg += np.sin(2 * np.pi * f * detune * t)
    fade_n = min(int(1.0 * SAMPLE_RATE), n // 2)
    env = np.ones(n)
    if fade_n > 0:
        env[:fade_n] = np.linspace(0, 1, fade_n)
        env[-fade_n:] = np.linspace(1, 0, fade_n)
    seg *= env
    seg = seg / (np.max(np.abs(seg)) + 1e-9)
    return seg * amp


# --------------------------------------------------------------------------
# Whoosh / boom (editorial transition cues)
# --------------------------------------------------------------------------

def make_whoosh(center_s, dur_s=0.55, f_start=1800, f_end=350, amp=1.0):
    t = t_axis()
    env = envelope_window(center_s - 0.05, 0.08, dur_s)
    rng = np.random.default_rng(int(center_s * 1000))
    noise = rng.standard_normal(N)
    out = np.zeros(N)
    start_sample = int(max(center_s - 0.1, 0) * SAMPLE_RATE)
    end_sample = int(min(center_s + dur_s + 0.1, TOTAL_DURATION_S) * SAMPLE_RATE)
    if end_sample <= start_sample:
        return out
    seg_noise = noise[start_sample:end_sample]
    seg_len = len(seg_noise)
    n_steps = 8
    step = max(seg_len // n_steps, 1)
    filtered = np.zeros(seg_len)
    for i in range(0, seg_len, step):
        j = min(i + step, seg_len)
        frac = i / max(seg_len, 1)
        center_f = f_start + (f_end - f_start) * frac
        lo = max(center_f * 0.6, 60)
        hi = min(center_f * 1.6, SAMPLE_RATE / 2 - 100)
        if hi <= lo:
            continue
        filtered[i:j] = bandpass(seg_noise[i:j], lo, hi, order=2)
    out[start_sample:end_sample] = filtered
    out *= env * amp
    return out


def make_boom(center_s, dur_s=0.9, amp=1.0):
    t = t_axis()
    env = envelope_window(center_s, 0.03, dur_s)
    tone = np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.5 * t)
    rng = np.random.default_rng(int(center_s * 777))
    thump_noise = lowpass(rng.standard_normal(N), 120.0, order=2)
    out = (tone * 0.8 + thump_noise * 0.2) * env * amp
    return out


def make_riser(start_s, end_s, amp=1.0):
    """Noise + rising-pitch sweep building into an impact at end_s."""
    out = np.zeros(N)
    dur = end_s - start_s
    if dur <= 0:
        return out
    s = max(s2i(start_s), 0)
    e = min(s2i(end_s), N)
    n = e - s
    if n <= 0:
        return out
    t = np.arange(n) / SAMPLE_RATE
    frac = t / dur
    rng = np.random.default_rng(int(start_s * 333) % 9999 + n)
    noise = rng.standard_normal(n)
    center_f = 400 + frac * 5200
    filtered = np.zeros(n)
    n_steps = 10
    step = max(n // n_steps, 1)
    for i in range(0, n, step):
        j = min(i + step, n)
        cf = center_f[i]
        filtered[i:j] = bandpass(noise[i:j], cf * 0.7, cf * 1.3, order=2)
    tone = np.sin(2 * np.pi * (200 + frac * 900) * t) * 0.3
    env = frac ** 1.5
    out[s:e] = (filtered * 0.8 + tone) * env * amp
    return out


def duck_envelope(narration_start_s, narration_end_s):
    t = t_axis()
    duck_amp = db_to_amp(DUCK_DB)
    env = np.ones(N)
    fade_n = int(DUCK_FADE_S * SAMPLE_RATE)
    s = int(narration_start_s * SAMPLE_RATE)
    e = int(narration_end_s * SAMPLE_RATE)
    env[s:e] = duck_amp
    if s - fade_n >= 0:
        env[s - fade_n:s] = np.linspace(1.0, duck_amp, fade_n)
    if e + fade_n <= N:
        env[e:e + fade_n] = np.linspace(duck_amp, 1.0, fade_n)
    return env


# Simple A-minor-pentatonic-ish scale over the two low octaves used by the pad,
# for a restrained melodic motif (not a dense arp).
MELODY_SCALE = {
    "Am": [220.00, 261.63, 293.66, 329.63, 392.00],  # A C D E G (A3 oct)
    "F": [174.61, 220.00, 261.63, 293.66, 349.23],   # F A C D F
    "C": [196.00, 261.63, 293.66, 329.63, 392.00],   # G C D E G
    "G": [196.00, 246.94, 293.66, 349.23, 392.00],   # G B D F G
}

CHORDS = {
    "Am": (110.00, 164.81, 220.00),
    "F": (87.31, 130.81, 174.61),
    "C": (65.41, 130.81, 196.00),
    "G": (98.00, 146.83, 196.00),
}


def main():
    meta = json.loads((AUDIO_DIR / "segments.json").read_text(encoding="utf-8"))
    narration_start = meta["narration_start_s"]
    narration_end = meta["narration_end_s"]
    acts = meta["segments"]

    # Act windows -> (start, end, chord, energy 0..1, melody_on, hat_on)
    plan = [
        dict(name="act1", start=acts[0]["start_s"], end=acts[0]["end_s"], chord="Am", energy=0.30, melody=False, hats=False),
        dict(name="act2", start=acts[1]["start_s"], end=acts[1]["end_s"], chord="F", energy=0.45, melody=True, hats=False),
        dict(name="act3", start=acts[2]["start_s"], end=acts[2]["end_s"], chord="C", energy=0.62, melody=True, hats=True),
        dict(name="act4", start=acts[3]["start_s"], end=acts[3]["end_s"], chord="G", energy=0.85, melody=True, hats=True),
        dict(name="act5", start=acts[4]["start_s"], end=acts[4]["end_s"], chord="Am", energy=0.32, melody=False, hats=False),
        dict(name="act6", start=acts[5]["start_s"], end=acts[5]["end_s"], chord="F", energy=0.78, melody=True, hats=True),
        dict(name="outro", start=narration_end, end=TOTAL_DURATION_S, chord="C", energy=0.18, melody=True, hats=False),
    ]

    pad = np.zeros(N)
    kick_hat = np.zeros(N)
    melody = np.zeros(N)
    sfx = np.zeros(N)
    cues = []

    for seg in plan:
        start, end, chord, energy = seg["start"], seg["end"], seg["chord"], seg["energy"]
        dur = end - start
        if dur <= 0:
            continue

        pad_amp = 0.5 + 0.25 * energy
        pad[s2i(start):s2i(start) + len(make_pad_segment(CHORDS[chord], start, end, pad_amp))] += \
            make_pad_segment(CHORDS[chord], start, end, pad_amp)

        # Kick grid: denser as energy rises.
        if energy < 0.4:
            kick_every = BEAT_S * 4
        elif energy < 0.6:
            kick_every = BEAT_S * 2
        elif energy < 0.75:
            kick_every = BEAT_S * 1.5
        else:
            kick_every = BEAT_S * 1.0
        kick_amp = 0.5 + 0.5 * energy
        t_k = start
        kick_idx = 0
        while t_k < end:
            add_at(kick_hat, t_k, make_kick(amp=kick_amp))
            # syncopated extra kick at high energy
            if energy >= 0.75 and kick_idx % 2 == 1:
                add_at(kick_hat, min(t_k + BEAT_S * 0.5, end - 0.01), make_kick(amp=kick_amp * 0.6, dur_s=0.16))
            t_k += kick_every
            kick_idx += 1

        if seg["hats"]:
            subdiv = BEAT_S * 0.5 if energy < 0.75 else BEAT_S * 0.25
            t_h = start + subdiv
            n_h = 0
            while t_h < end:
                open_h = seg["hats"] and (n_h % 4 == 3)
                add_at(kick_hat, t_h, make_hat(amp=0.10 + 0.05 * energy, open_hat=open_h))
                t_h += subdiv
                n_h += 1

        if seg["melody"]:
            scale = MELODY_SCALE[chord]
            rng = np.random.default_rng(hash(seg["name"]) % (2 ** 31))
            t_m = start + BEAT_S
            note_len = BEAT_S * 1.5
            while t_m < end - note_len * 0.5:
                if rng.random() < 0.72:  # restrained: leave rests
                    freq = scale[rng.integers(0, len(scale))]
                    add_at(melody, t_m, make_synth_note(freq, note_len, amp=0.22 + 0.1 * energy))
                t_m += note_len
            cues.append({"time_s": round(start, 2), "type": "melody_phrase_start", "note": f"warm synth motif enters over {chord}"})

    # --- Editorial transition cues (riser -> impact / snap / whoosh), aligned to act boundaries ---
    transitions = [
        dict(t=acts[0]["end_s"], riser_lead=1.2, kind="snap", amp=0.55, note="cut into Act 2 (Enter code-anime)"),
        dict(t=acts[1]["end_s"] + (acts[2]["start_s"] - acts[1]["end_s"]), riser_lead=1.4, kind="impact", amp=0.75, note="cut into Act 3 (architecture)"),
        dict(t=acts[3]["start_s"], riser_lead=1.6, kind="boom", amp=0.9, note="cut into Act 4 asset showcase (biggest hit pre-climax)"),
        dict(t=acts[4]["start_s"], riser_lead=0.5, kind="whoosh_soft", amp=0.45, note="pull back into Act 5 screening — let footage breathe"),
        dict(t=acts[5]["start_s"], riser_lead=1.3, kind="impact", amp=0.7, note="rebuild into Act 6 roadmap/CTA"),
        dict(t=narration_end, riser_lead=0.9, kind="snap_boom", amp=0.65, note="final CTA accent leading to resolve"),
    ]

    for tr in transitions:
        t_hit = tr["t"]
        if tr["kind"] == "whoosh_soft":
            sfx += make_whoosh(t_hit, dur_s=0.6, f_start=900, f_end=300, amp=tr["amp"])
            cues.append({"time_s": round(t_hit, 2), "type": "whoosh", "amp": tr["amp"], "note": tr["note"]})
            continue
        sfx += make_riser(t_hit - tr["riser_lead"], t_hit, amp=tr["amp"])
        if tr["kind"] == "snap":
            add_at(sfx, t_hit, make_snap(amp=tr["amp"]))
        elif tr["kind"] == "impact":
            add_at(sfx, t_hit, make_snap(amp=tr["amp"] * 0.8))
            sfx += make_boom(t_hit, dur_s=0.6, amp=tr["amp"] * 0.7)
        elif tr["kind"] == "boom":
            sfx += make_boom(t_hit, dur_s=0.9, amp=tr["amp"])
            add_at(sfx, t_hit, make_snap(amp=tr["amp"] * 0.6))
        elif tr["kind"] == "snap_boom":
            add_at(sfx, t_hit, make_snap(amp=tr["amp"]))
            sfx += make_boom(t_hit, dur_s=0.7, amp=tr["amp"] * 0.8)
        cues.append({"time_s": round(t_hit, 2), "type": tr["kind"], "amp": tr["amp"], "riser_from_s": round(t_hit - tr["riser_lead"], 2), "note": tr["note"]})

    # Opening title boom (kept from prior cut).
    sfx += make_boom(0.25, dur_s=1.0, amp=0.85)
    cues.insert(0, {"time_s": 0.25, "type": "boom", "amp": 0.85, "note": "opening title card"})

    # Final resolve: soft swelling tail landing on the tonic at 89s, fading to silence by 90s.
    resolve_start = narration_end + 1.0  # ~84.19s
    resolve_chord = CHORDS["C"]
    resolve_pad = make_pad_segment(resolve_chord, resolve_start, TOTAL_DURATION_S, amp=0.5)
    add_at(pad, resolve_start, resolve_pad)
    # gentle final swell shimmer centered at 89s
    shimmer_n = s2i(2.0)
    t_sh = np.arange(shimmer_n) / SAMPLE_RATE
    shimmer = np.sin(2 * np.pi * 440.0 * t_sh) * np.exp(-((t_sh - 1.0) ** 2) / (2 * 0.5 ** 2)) * 0.12
    add_at(sfx, 88.0, shimmer)
    cues.append({"time_s": 89.0, "type": "resolve", "note": "final tonic swell resolves, tail to silence by 90s"})

    mix = pad * 0.85 + kick_hat * 1.0 + melody * 0.9 + sfx * 0.7

    # Hard fade-out over the last 0.8s to guarantee silence at exactly 90.0s.
    fade_n = s2i(0.8)
    mix[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)

    duck = duck_envelope(narration_start, narration_end)
    mix *= duck

    peak = np.max(np.abs(mix))
    target_amp = db_to_amp(MIX_PEAK_DBFS)
    if peak > 0:
        mix = mix * (target_amp / peak)

    stereo = np.stack([mix, mix], axis=1).astype(np.float32)

    import soundfile as sf
    out_wav = DEMO_DIR / "music.wav"
    sf.write(str(out_wav), stereo, SAMPLE_RATE, subtype="PCM_16")

    final_peak = float(np.max(np.abs(stereo)))
    final_peak_dbfs = 20 * np.log10(final_peak) if final_peak > 0 else -float("inf")

    cues_sorted = sorted(cues, key=lambda c: c["time_s"])
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    cues_path = SFX_DIR / "cues.json"
    cues_path.write_text(json.dumps({
        "source": "music.wav",
        "sample_rate": SAMPLE_RATE,
        "total_duration_s": TOTAL_DURATION_S,
        "tempo_bpm": 60.0 / BEAT_S,
        "narration_window_s": [narration_start, narration_end],
        "cues": cues_sorted,
    }, indent=2), encoding="utf-8")

    print(f"Wrote {out_wav} ({TOTAL_DURATION_S}s), peak {final_peak_dbfs:.2f} dBFS, ducked [{narration_start:.2f}-{narration_end:.2f}]s by {DUCK_DB} dB")
    print(f"Wrote {cues_path} ({len(cues_sorted)} cues)")


if __name__ == "__main__":
    main()
