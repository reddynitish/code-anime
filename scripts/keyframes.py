"""Generate keyframe candidates with Ideogram 4.5 (via Luminal) from a reference image.

Each key in a shot spec gets N candidates from the Generate endpoint (edit mode,
source image attached). Jobs persist under <out>/jobs so reruns never resubmit
paid work. Pick winners afterwards with a contact sheet; LTX animates between them.

  python3 scripts/keyframes.py specs/bedroom_door.json --n 8 --quality high --cap 50
"""
import argparse, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from luminal_images import request, multipart, PRICE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def spent(jobs: Path) -> float:
    return sum(json.loads(p.read_text()).get('reserved_usd', 0) for p in jobs.glob('*.json'))


def submit(jobs, key, prompt, images, n, quality, seed, cap):
    path = jobs / f'{key}.json'
    if path.exists():
        return json.loads(path.read_text())
    cost = PRICE[quality] * n
    if spent(jobs) + cost > cap:
        raise SystemExit(f'cap ${cap} would be exceeded by {key} (${cost:.2f})')
    body, ctype = multipart({'prompt': prompt, 'quality': quality, 'num_images': str(n),
                             'async': 'true', 'seed': str(seed)},
                            [('images', i) for i in images])
    job = {'key': key, 'state': 'submitting', 'prompt': prompt, 'images': [str(i) for i in images],
           'quality': quality, 'n': n, 'reserved_usd': cost, 'submitted_ms': int(time.time() * 1000)}
    path.write_text(json.dumps(job, indent=2))
    try:
        _, headers, result = request('/v2/image/generate/ideogram-4-5', body, ctype)
    except Exception as e:
        if 'HTTP 429' in str(e) or 'HTTP 503' in str(e):  # never charged; safe to resubmit
            path.unlink()
            return None
        job.update(state='submission_uncertain', error=str(e))
        path.write_text(json.dumps(job, indent=2))
        raise
    job.update(state='pending', generation_id=result.get('generation_id') or headers.get('x-luminal-generation-id'))
    path.write_text(json.dumps(job, indent=2))
    print('submitted', key, job['generation_id'], flush=True)
    return job


def poll(jobs, out, key):
    path = jobs / f'{key}.json'
    job = json.loads(path.read_text())
    if job['state'] in ('completed', 'failed') or not job.get('generation_id'):
        return job
    _, headers, result = request('/v1/generations/' + job['generation_id'])
    if result.get('status') == 'pending':
        return job
    if result.get('status') == 'failed':
        job.update(state='failed', response=result)
    else:
        files = []
        for i, item in enumerate(result.get('data', [])):
            if not item.get('url') or not item.get('is_image_safe', True):
                continue
            dest = out / f'{key}_{i:02d}.png'
            req = urllib.request.Request(item['url'], headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://ideogram.ai/'})
            with urllib.request.urlopen(req, timeout=90) as r:
                dest.write_bytes(r.read())
            files.append(str(dest))
        job.update(state='completed', outputs=files, charged_usd=headers.get('x-luminal-cost-usd'))
    path.write_text(json.dumps(job, indent=2))
    print(job['state'], key, len(job.get('outputs', [])), 'images', flush=True)
    return job


def main():
    p = argparse.ArgumentParser()
    p.add_argument('spec')
    p.add_argument('--n', type=int, default=8)
    p.add_argument('--quality', default='high', choices=list(PRICE))
    p.add_argument('--cap', type=float, default=50.0, help='USD ceiling for this run directory')
    p.add_argument('--only', nargs='*')
    a = p.parse_args()

    spec = json.loads(Path(a.spec).read_text())
    out = ROOT / spec['out']
    jobs = out / 'jobs'
    jobs.mkdir(parents=True, exist_ok=True)
    keys = [k for k in spec['keys'] if not a.only or k['id'] in a.only]
    queue = list(keys)
    pending = set()
    while queue or pending:
        while queue:
            k = queue[0]
            imgs = [ROOT / i for i in k.get('images', [spec['reference']])]
            prompt = spec['style'] + '\n\n' + k['prompt']
            if submit(jobs, k['id'], prompt, imgs, a.n, a.quality, k.get('seed', 7), a.cap) is None:
                break  # rate limited: poll what is in flight, then retry
            pending.add(queue.pop(0)['id'])
        time.sleep(10)
        for key in list(pending):
            if poll(jobs, out, key)['state'] != 'pending':
                pending.discard(key)
    print(f'run total reserved ${spent(jobs):.2f}')


if __name__ == '__main__':
    main()
