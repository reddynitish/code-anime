"""Assemble a drawn sequence into an MP4, anime-style (each drawing held N frames).

Every drawing is aligned, its character is cut out against the clean plate and
composited over that one plate, so only the character changes between drawings.

  python3 scripts/assemble_drawn.py specs/bedroom_door_keys_v4.json --on 3 --hold-start 0.6 --hold-end 1.0 --out output/shots/bedroom_door_drawn_v1
"""
import argparse, json, shutil, subprocess
from pathlib import Path

import cv2

from plate import aligned, build_plate, char_mask, composite


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keys')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--on', type=int, default=2, help='frames each drawing is held (anime "on 2s"/"on 3s")')
    ap.add_argument('--hold-start', type=float, default=0.0)
    ap.add_argument('--hold-end', type=float, default=0.0)
    ap.add_argument('--plate', help='reuse a plate image instead of the median of these keys')
    ap.add_argument('--raw', action='store_true', help='skip compositing (debug)')
    a = ap.parse_args()

    keys = json.loads(Path(a.keys).read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    plate = cv2.imread(a.plate) if a.plate else build_plate(keys)
    cv2.imwrite(str(a.out / 'plate.png'), plate)
    drawings = a.out / 'drawings'
    shutil.rmtree(drawings, ignore_errors=True)
    drawings.mkdir()
    for i, k in enumerate(keys):
        img = cv2.imread(str(aligned(k)))
        cv2.imwrite(str(drawings / f'{i:03d}.png'), img if a.raw else composite(img, plate, char_mask(img, plate)))

    holds = [a.on] * len(keys)
    holds[0] += round(a.hold_start * a.fps)
    holds[-1] += round(a.hold_end * a.fps)
    lst = a.out / 'timing.txt'
    lines = []
    for i, h in enumerate(holds):
        lines += [f"file '{(drawings / f'{i:03d}.png').resolve()}'", f'duration {h / a.fps:.6f}']
    lines.append(f"file '{(drawings / f'{len(keys) - 1:03d}.png').resolve()}'")
    lst.write_text('\n'.join(lines))
    total = sum(holds) / a.fps
    mp4 = a.out / 'shot.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst),
                    '-vf', f'fps={a.fps},format=yuv420p', '-t', f'{total:.3f}', '-c:v', 'libx264', '-crf', '16', str(mp4)], check=True)
    print(f'{len(keys)} drawings on {a.on}s, {total:.2f}s -> {mp4}')


if __name__ == '__main__':
    main()
