"""Clean background plate + character masks for a drawn sequence.

The plate is the per-pixel median of every aligned key: the character moves, so
the median keeps the room and drops him. A frame's character mask is where it
differs from the plate. Compositing each drawing's character over one fixed plate
removes the background boil that independent drawings otherwise have.
"""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def aligned(path):
    p = Path(path)
    if p.parent.name == 'references':
        return ROOT / 'output/keyframes/bedroom_door_r1/aligned/k0_reference.png'
    return ROOT / p.parent / 'aligned' / p.name


def build_plate(paths):
    stack = np.stack([cv2.imread(str(aligned(p))) for p in paths])
    return np.median(stack, axis=0).astype(np.uint8)


def char_mask(img, plate, thr=20, min_area=1500):
    d = cv2.absdiff(cv2.GaussianBlur(img, (5, 5), 0), cv2.GaussianBlur(plate, (5, 5), 0)).max(axis=2)
    m = (d > thr).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m)
    if n > 1:
        # the character is the largest change; other blobs are kept only near the
        # door (it opens), so blanket re-renders never reach the composite
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= min_area and (i == biggest or cents[i][0] > 0.62 * m.shape[1]):
                keep[lab == i] = 1
    # fill interior holes (dark hair/legs against the dark door read as background)
    contours, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(keep, contours, -1, 1, cv2.FILLED)
    return keep


def composite(img, plate, mask, feather=7):
    soft = cv2.GaussianBlur(cv2.dilate(mask, np.ones((9, 9), np.uint8)).astype(np.float32), (0, 0), feather)[..., None]
    return (img * soft + plate * (1 - soft)).astype(np.uint8)


if __name__ == '__main__':
    import sys
    keys = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    plate = build_plate(keys)
    cv2.imwrite(str(out / 'plate.png'), plate)
    for i, k in enumerate(keys):
        img = cv2.imread(str(aligned(k)))
        m = char_mask(img, plate)
        cv2.imwrite(str(out / f'mask_{i:03d}.png'), m * 255)
        cv2.imwrite(str(out / f'comp_{i:03d}.png'), composite(img, plate, m))
    print('plate +', len(keys), 'composites ->', out)
