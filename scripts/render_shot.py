"""Render a whole shot: LTX in-betweens for every consecutive key pair, then one MP4.

Keys are evenly spaced across the shot. Each segment shares its boundary key with
the next, so the duplicate first frame of every later segment is dropped. Segments
already rendered (meta.json present) are reused.

  python3 scripts/render_shot.py specs/bedroom_door_keys_v2.json --seconds 10 --out output/shots/bedroom_door_v1
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ('Hand-drawn anime animation, static locked-off camera, night bedroom. A young man with messy black hair, '
          'grey t-shirt and olive sweatpants moves naturally from the first pose to the last pose. Smooth continuous '
          'body motion, consistent character, no flicker, same room and lighting.')


def aligned(path):
    p = Path(path)
    if p.parent.name == 'references':
        return ROOT / 'output/keyframes/bedroom_door_r1/aligned/k0_reference.png'
    return ROOT / p.parent / 'aligned' / p.name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keys')
    ap.add_argument('--seconds', type=float, default=10)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--w', type=int, default=768)
    ap.add_argument('--h', type=int, default=448)
    ap.add_argument('--steps', type=int, default=30)
    ap.add_argument('--only', type=int, nargs='*', help='segment indices to render')
    ap.add_argument('--seg-frames', type=int, help='override frames per segment (8n+1)')
    ap.add_argument('--hold-start', type=float, default=0, help='seconds to hold the first frame')
    ap.add_argument('--hold-end', type=float, default=0, help='seconds to hold the last frame')
    a = ap.parse_args()

    keys = json.loads(Path(a.keys).read_text())
    gaps = len(keys) - 1
    seg_frames = a.seg_frames or round(a.seconds * a.fps / gaps / 8) * 8 + 1  # LTX needs 8n+1
    print(f'{len(keys)} keys, {gaps} segments of {seg_frames} frames', flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    for i in range(gaps):
        seg = a.out / f'seg{i:02d}'
        if (seg / 'meta.json').exists() or (a.only is not None and i not in a.only):
            continue
        subprocess.run([sys.executable, str(ROOT / 'scripts/ltx_inbetween.py'), str(aligned(keys[i])), str(aligned(keys[i + 1])),
                        '--prompt', PROMPT, '--frames', str(seg_frames), '--steps', str(a.steps), '--w', str(a.w), '--h', str(a.h),
                        '--seed', str(1000 + i), '--out', str(seg)], check=True)

    frames = a.out / 'frames'
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    n = 0
    first = a.out / 'seg00' / 'f0000.png'
    for _ in range(round(a.hold_start * a.fps)):
        shutil.copy(first, frames / f'{n:05d}.png')
        n += 1
    for i in range(gaps):
        seg = a.out / f'seg{i:02d}'
        if not (seg / 'meta.json').exists():
            print('missing', seg.name, '- stopping assembly there')
            break
        for f in sorted(seg.glob('f*.png'))[(1 if i else 0):]:
            shutil.copy(f, frames / f'{n:05d}.png')
            n += 1
    for _ in range(round(a.hold_end * a.fps)):
        shutil.copy(frames / f'{n - 1:05d}.png', frames / f'{n:05d}.png')
        n += 1
    mp4 = a.out / 'shot.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-framerate', str(a.fps), '-i', str(frames / '%05d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', str(mp4)], check=True)
    print(f'{n} frames -> {mp4} ({n / a.fps:.2f}s)')


if __name__ == '__main__':
    main()
