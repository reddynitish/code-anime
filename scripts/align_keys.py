"""Register keyframe candidates to the reference camera and rank them by fit.

Ideogram edits drift slightly in zoom/crop. ORB features + RANSAC homography
(robust to the moving character) warp each candidate back onto the reference
framing, then the static background is compared to score camera consistency.

  python3 scripts/align_keys.py output/keyframes/bedroom_door_r1 assets/references/ref3_latest_male_night.png
"""
import argparse, json
from pathlib import Path

import cv2
import numpy as np

W, H = 1024, 576  # LTX wants multiples of 32


def load(path):
    return cv2.resize(cv2.imread(str(path)), (W, H), interpolation=cv2.INTER_AREA)


def align(ref, img, orb, matcher):
    g1, g2 = (cv2.cvtColor(x, cv2.COLOR_BGR2GRAY) for x in (ref, img))
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    matches = sorted(matcher.match(d2, d1), key=lambda m: m.distance)[:800]
    src = np.float32([k2[m.queryIdx].pt for m in matches])
    dst = np.float32([k1[m.trainIdx].pt for m in matches])
    Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    warped = cv2.warpPerspective(img, Hm, (W, H), borderMode=cv2.BORDER_REPLICATE)
    return warped, Hm, int(inl.sum())


def bg_error(ref, warped):
    # Median absolute difference ignores the moving character (a minority of pixels).
    d = cv2.absdiff(cv2.GaussianBlur(ref, (9, 9), 0), cv2.GaussianBlur(warped, (9, 9), 0)).mean(axis=2)
    return float(np.median(d)), float(np.percentile(d, 75))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run_dir')
    p.add_argument('reference')
    a = p.parse_args()
    run = Path(a.run_dir)
    out = run / 'aligned'
    out.mkdir(exist_ok=True)
    ref = load(a.reference)
    cv2.imwrite(str(out / 'k0_reference.png'), ref)
    orb = cv2.ORB_create(5000)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    report = {}
    for f in sorted(run.glob('*_[0-9][0-9].png')):
        img = load(f)
        warped, Hm, inliers = align(ref, img, orb, matcher)
        med, p75 = bg_error(ref, warped)
        scale = float(np.sqrt(abs(np.linalg.det(Hm[:2, :2]))))
        cv2.imwrite(str(out / f.name), warped)
        key = f.stem.rsplit('_', 1)[0]
        report.setdefault(key, []).append({'file': f.name, 'inliers': inliers, 'bg_median': round(med, 2),
                                           'bg_p75': round(p75, 2), 'zoom_correction': round(scale, 3)})
    for key, rows in report.items():
        rows.sort(key=lambda r: (r['bg_p75'], -r['inliers']))
        print(key)
        for r in rows:
            print('  ', r)
    (run / 'alignment.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
