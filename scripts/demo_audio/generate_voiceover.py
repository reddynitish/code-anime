#!/usr/bin/env python3
"""Generate the demo90 voiceover from narration.txt using edge-tts.

Kokoro TTS was attempted first but its g2p dependency chain (misaki ->
spacy -> thinc -> blis) fails to build on Python 3.14 (no prebuilt
wheels yet). edge-tts is the documented fallback: free, no API key,
no voice cloning, and ships natural neural voices.
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import edge_tts

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "output" / "demo90"
AUDIO_DIR = DEMO_DIR / "audio"
NARRATION_TXT = DEMO_DIR / "narration.txt"
VOICE = "en-US-AndrewNeural"  # Warm, Confident, Authentic, Honest
RATE = "+0%"
SAMPLE_RATE = 48000
TOTAL_DURATION_S = 90.0
LEAD_IN_S = 1.0
GAP_BETWEEN_ACTS_S = 0.55
TARGET_PEAK_DBFS = -3.0

ACT_TITLES = [
    "Act 1 - The Solo Storyteller's Dilemma",
    "Act 2 - Enter code-anime: The Studio in Code",
    "Act 3 - The Geometry-First Architecture",
    "Act 4 - Production Asset Showcase",
    "Act 5 - Continuous Video Excerpt (Screening)",
    "Act 6+7 - Engineering Roadmap & Conclusion / Call to Action",
]


def load_paragraphs() -> list[str]:
    raw = NARRATION_TXT.read_text(encoding="utf-8")
    paras = [p.strip().replace("\n", " ") for p in raw.split("\n\n")]
    paras = [p for p in paras if p]
    return paras


async def synth_one(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(str(mp3_path))


def mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            str(wav_path),
        ],
        check=True,
    )


def db_to_amp(db: float) -> float:
    return 10.0 ** (db / 20.0)


def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = AUDIO_DIR / "_raw_tts"
    raw_dir.mkdir(parents=True, exist_ok=True)

    paragraphs = load_paragraphs()
    if len(paragraphs) != len(ACT_TITLES):
        print(f"WARNING: {len(paragraphs)} paragraphs vs {len(ACT_TITLES)} act titles", file=sys.stderr)

    clips = []
    for i, text in enumerate(paragraphs, start=1):
        mp3_path = raw_dir / f"act{i}.mp3"
        wav_path = raw_dir / f"act{i}.wav"
        asyncio.run(synth_one(text, mp3_path))
        mp3_to_wav(mp3_path, wav_path)
        data, sr = sf.read(str(wav_path), dtype="float32")
        assert sr == SAMPLE_RATE
        clips.append({"text": text, "audio": data})

    timeline = np.zeros(int(TOTAL_DURATION_S * SAMPLE_RATE), dtype=np.float32)
    cursor = LEAD_IN_S
    segments = []
    for i, clip in enumerate(clips):
        audio = clip["audio"]
        dur = len(audio) / SAMPLE_RATE
        start_sample = int(cursor * SAMPLE_RATE)
        end_sample = start_sample + len(audio)
        if end_sample > len(timeline):
            end_sample = len(timeline)
            audio = audio[: end_sample - start_sample]
        timeline[start_sample:end_sample] += audio
        segments.append(
            {
                "act": i + 1,
                "title": ACT_TITLES[i] if i < len(ACT_TITLES) else f"Act {i + 1}",
                "text": clip["text"],
                "voice": VOICE,
                "rate": RATE,
                "start_s": round(cursor, 3),
                "duration_s": round(dur, 3),
                "end_s": round(cursor + dur, 3),
            }
        )
        cursor += dur + GAP_BETWEEN_ACTS_S

    narration_end_s = cursor - GAP_BETWEEN_ACTS_S

    # Normalize to target peak to avoid clipping.
    peak = float(np.max(np.abs(timeline))) if np.max(np.abs(timeline)) > 0 else 1.0
    target_amp = db_to_amp(TARGET_PEAK_DBFS)
    timeline *= (target_amp / peak)

    stereo = np.stack([timeline, timeline], axis=1)
    out_wav = DEMO_DIR / "voiceover.wav"
    sf.write(str(out_wav), stereo, SAMPLE_RATE, subtype="PCM_16")

    final_peak = float(np.max(np.abs(stereo)))
    final_peak_dbfs = 20 * np.log10(final_peak) if final_peak > 0 else -float("inf")

    meta = {
        "voice": VOICE,
        "rate": RATE,
        "sample_rate": SAMPLE_RATE,
        "total_duration_s": TOTAL_DURATION_S,
        "lead_in_s": LEAD_IN_S,
        "gap_between_acts_s": GAP_BETWEEN_ACTS_S,
        "narration_start_s": LEAD_IN_S,
        "narration_end_s": round(narration_end_s, 3),
        "narration_speech_duration_s": round(narration_end_s - LEAD_IN_S, 3),
        "peak_dbfs": round(final_peak_dbfs, 2),
        "segments": segments,
    }
    (AUDIO_DIR / "segments.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {out_wav} ({TOTAL_DURATION_S}s), narration ends at {narration_end_s:.2f}s, peak {final_peak_dbfs:.2f} dBFS")


if __name__ == "__main__":
    main()
