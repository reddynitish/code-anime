"""Auto-pick in-between candidates and merge them into a denser key sequence.

For each gap A→B, the best candidate C minimises d(A,C)+d(C,B) (a short path, so
no wild pose) plus |d(A,C)-d(C,B)| (an even split, so not a copy of A or B).
Distances compare blurred greyscale crops of the action area on aligned images.

  python3 scripts/pick_inbetween.py specs/bedroom_door_keys_v2.json specs/bedroom_door_r3_quarter.json specs/bedroom_door_keys_v3.json
"""
import glob, json, sys
from pathlib import Path

import cv2
import numpy as np

ROI = (slice(40, 470), slice(250, 850))


def aligned(path):
    p = Path(path)
    if p.parent.name == 'references':
        return 'output/keyframes/bedroom_door_r1/aligned/k0_reference.png'
    return str(p.parent / 'aligned' / p.name)


def feat(path):
    im = cv2.imread(aligned(path), cv2.IMREAD_GRAYSCALE)[ROI]
    return cv2.GaussianBlur(cv2.resize(im, (300, 215)), (7, 7), 0).astype(np.float32)


def d(x, y):
    return float(np.abs(x - y).mean())


def main():
    seq = json.load(open(sys.argv[1]))
    spec = json.load(open(sys.argv[2]))
    out_seq, picks = [seq[0]], {}
    for i, k in enumerate(spec['keys']):
        fa, fb = feat(seq[i]), feat(seq[i + 1])
        best = None
        for c in sorted(glob.glob(f"{spec['out']}/{k['id']}_[0-9][0-9].png")):
            fc = feat(c)
            da, db = d(fa, fc), d(fc, fb)
            score = da + db + abs(da - db)
            if best is None or score < best[0]:
                best = (score, c, round(da, 2), round(db, 2))
        picks[k['id']] = {'file': best[1], 'score': round(best[0], 2), 'dA': best[2], 'dB': best[3], 'dAB': round(d(fa, fb), 2)}
        out_seq += [best[1], seq[i + 1]]
    json.dump(out_seq, open(sys.argv[3], 'w'), indent=1)
    for k, v in picks.items():
        print(k, v)
    print(len(out_seq), 'keys ->', sys.argv[3])


if __name__ == '__main__':
    main()
