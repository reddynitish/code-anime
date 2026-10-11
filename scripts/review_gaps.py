"""Cropped review sheets: anchor A | candidates | anchor B, per in-between gap."""
import json, sys, cv2, numpy as np
s = json.load(open(sys.argv[1])); anchors = json.load(open(sys.argv[2]))
al = s['out'] + '/aligned/'
for k in s['keys']:
    ia, ib = k['id'].split('_')[1:]
    n = len([1 for _ in __import__('glob').glob(f"{al}{k['id']}_*.png")])
    files = [anchors[ia]] + [f"{al}{k['id']}_{i:02d}.png" for i in range(n)] + [anchors[ib]]
    ims = []
    for j, f in enumerate(files):
        im = cv2.imread(f)[40:470, 250:850].copy()
        cv2.putText(im, 'A' if j == 0 else 'B' if j == len(files) - 1 else str(j - 1), (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 255), 3)
        ims.append(np.pad(im, ((3, 3), (3, 3), (0, 0))))
    half = (len(ims) + 1) // 2
    while len(ims) < half * 2: ims.append(np.zeros_like(ims[0]))
    cv2.imwrite(f"{s['out']}/review_{k['id']}.jpg", np.vstack([np.hstack(ims[:half]), np.hstack(ims[half:])]), [cv2.IMWRITE_JPEG_QUALITY, 82])
