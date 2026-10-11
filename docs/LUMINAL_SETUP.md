# Luminal image API setup

The provided key is configured in `~/.config/code-anime/luminal.json`, outside the
repository. The directory has mode700 and the file has mode600. The key is never
printed by the client or forwarded as authentication to image download hosts.

API: `https://images.luminal.cloud`.
Image endpoint: `POST /v2/image/precise-edit/ideogram-4-5`.
Asynchronous polling: `GET /v1/generations/{generation_id}`.
Balance: `GET /v1/balance`.

The project calls only the image endpoint. Individual drawings are made remotely;
background compositing, timing and video encoding are local. No video-generation
endpoint is used.

`quality=high` is $0.20 per returned image; `medium` is $0.06. Request records and
cost headers persist under `output/2d/jobs`. Failed accepted generations are
archived before retrying. Unknown submission outcomes are not blindly resubmitted.

## Commands

Python with Pillow is required. The Codex bundled Python was used for this run.

```sh
python3 scripts/luminal_images.py balance
python3 scripts/draw_sequence.py --keys
python3 scripts/draw_sequence.py --frames
python3 scripts/assemble_drawings.py
```

Completed jobs are reused; invoking a phase again does not submit them again.
The image client limits reservations for this first pass to $15.

Sources: [Luminal pricing](https://www.luminal.com/pricing),
[Luminal API differences](https://images.luminal.cloud/docs/),
[Ideogram precise edit contract](https://developer.ideogram.ai/api-reference/images/precise-edit/ideogram-4-5).
