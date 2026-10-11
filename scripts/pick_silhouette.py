"""Silhouette auto-picker for in-between candidates.

Character masks come from differencing against the clean plate (plate.py). A good
in-between C for A→B has its mask centroid halfway between A's and B's, a similar
area, and sits inside the region the character sweeps between A and B. Copies of
A or B and wandering/duplicate figures score badly.

  python3 scripts/pick_silhouette.py <keys.json> <spec.json> <out_keys.json> [--plate plate.png] [--check manual_picks]
"""
import argparse, glob, json
from pathlib import Path

import cv2
import numpy as np

from plate import aligned, build_plate, char_mask


def stats(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) < 500:
        return None
    return np.array([xs.mean(), ys.mean()]), float(len(xs))


def score(mA, mB, mC):
    sA, sB, sC = stats(mA), stats(mB), stats(mC)
    if not (sA and sB and sC):
        return 1e9
    (cA, aA), (cB, aB), (cC, aC) = sA, sB, sC
    mid = (cA + cB) / 2
    span = np.linalg.norm(cA - cB) + 15
    pos = np.linalg.norm(cC - mid) / span
    # reject near-copies of either end: C must move away from both
    copy = max(0.0, 0.25 - min(np.linalg.norm(cC - cA), np.linalg.norm(cC - cB)) / span)
    iou = lambda x, y: float((x & y).sum()) / max(1.0, float((x | y).sum()))
    copy += max(0.0, max(iou(mC, mA), iou(mC, mB)) - 0.75) * 4  # silhouette nearly identical to an end
    area = abs(aC - (aA + aB) / 2) / ((aA + aB) / 2)
    sweep = cv2.dilate(np.maximum(mA, mB), np.ones((41, 41), np.uint8))
    outside = float((mC & (1 - sweep)).sum()) / aC
    return pos + 2 * copy + 0.5 * area + 2 * outside


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keys')
    ap.add_argument('spec')
    ap.add_argument('out')
    ap.add_argument('--plate')
    ap.add_argument('--check', type=int, nargs='*', help='manual picks to compare against')
    a = ap.parse_args()
    keys = json.loads(Path(a.keys).read_text())
    spec = json.loads(Path(a.spec).read_text())
    plate = cv2.imread(a.plate) if a.plate else build_plate(keys)
    m = lambda p: char_mask(cv2.imread(str(aligned(p))), plate)
    out, agree = [keys[0]], 0
    masks = [m(k) for k in keys]
    for i, k in enumerate(spec['keys']):
        cands = sorted(glob.glob(f"{spec['out']}/{k['id']}_[0-9][0-9].png"))
        scored = sorted((score(masks[i], masks[i + 1], m(c)), c) for c in cands)
        best = scored[0][1]
        pick = int(best[-6:-4])
        line = f"{k['id']}: pick {pick} ({scored[0][0]:.2f}) ranking {[int(c[-6:-4]) for _, c in scored]}"
        if a.check:
            agree += pick == a.check[i]
            line += f"  manual {a.check[i]}"
        print(line)
        out += [best, keys[i + 1]]
    if a.check:
        print(f'agreement {agree}/{len(a.check)}')
    Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
