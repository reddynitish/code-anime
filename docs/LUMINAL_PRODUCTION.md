# Luminal Production Asset Strategy & API Capabilities

## 1. Executive Summary & Strategy Shift

The project previously attempted a dense in-between flipbook approach (25–49 micro-frames) via Ideogram 4.5. While Ideogram holds line quality and style faithfully, interpolating full-frame dense in-betweens frame-by-frame creates noticeable spatial flicker, misalignments, and wastes credits without delivering fluid animation.

As established in the latest video generation research (Wan 2.2 / LTX), **modern anime AI video generation relies on generating clean, high-fidelity anchor frames (I2V / FLF start and end frames) and feeding them to continuous video models**, supplemented by clean background plates and reusable character turnarounds.

Luminal credits ($1,931.08 available) will now be used intentionally to generate **permanent reusable production assets** and **first/last frame anchors** for the 10-second bedroom door scene, rather than disposable flipbook in-betweens.

---

## 2. Luminal API Capabilities & Verified Routes

From inspecting the live documentation (`https://images.luminal.cloud/docs/`):

### Available Endpoints
- `POST /v2/image/generate/ideogram-4-5`: Text-to-image or image edit with up to 5 source files.
- `POST /v2/image/precise-edit/ideogram-4-5`: Precise editing with 1 primary `image` plus up to 4 `reference_images`.
- `GET /v1/generations/{generation_id}`: Poll asynchronous generation status.
- `GET /v1/generations?since=<ms>&limit=<n>`: List recent generations.
- `GET /v1/balance`: Check account balance (available credit).

### Verified Rate Limits & Concurrency
- **Concurrent in-flight generations**: 8 maximum (`client-inflight-limit`).
- **Requests per minute**: 60 requests/min across both POST endpoints.
- **Images per minute**: 120 images/min.
- **Polling rate**: 600 polls/min.
- **Payload size**: 160 MiB multipart, 1 MiB JSON.

### Pricing Tiers (Per Returned Image)
- `very_low`: $0.0080 (edits only, requires source image).
- `low`: $0.0300 (fast preview).
- `medium`: $0.0600 (default for edits / Precise Edit).
- `high`: $0.2000 (default for text-to-image, best-of-candidates, highest fidelity).

### Inpainting, Outpainting & Mask Capabilities
- **Mask support**: PNG/JPEG/WebP masks are accepted directly in multipart uploads (`mask` field).
  - Generate endpoint allows up to 4 source images when a mask is provided.
  - Precise edit allows 1 source image + 3 references when a mask is provided.
- **Outpainting / Aspect expansion**: Not exposed as dedicated outpaint endpoints; aspect ratio must adhere to Ideogram's supported ratios (1:6 to 6:1, max 25 MB). Outpainting is handled by canvas expansion + inpainting mask.
- **Asset identifiers**: `image_asset_identifiers` are explicitly **refused** (`400 invalid_request_error`); raw image file bytes must be uploaded via multipart form data.

---

## 3. DeepSeek Text API Status & Unknowns

- **Configuration status**: In `~/.config/code-anime/luminal.json`, only `api_key` and `image_base_url` (`https://images.luminal.cloud`) are configured.
- **Base URL status**: The text API base URL is **unverified / missing** in the config. Public docs at `images.luminal.cloud/docs/` do not disclose the text API route (stating only: *"your Luminal API keys from the dashboard, the same ones the Text API uses"*).
- **Hard rule compliance**: We do **not** guess text API hostnames or trigger unauthorized autonomous requests. Text API calls for scene planning are paused until the user or Codex provides the explicit dashboard endpoint in the config.

---

## 4. Production Batch Design: 80 Images ($16.00 Cap)

The batch specification is defined in [`specs/luminal_production_batch.json`](file:///Users/nitishreddy/x-scrap/code-anime/specs/luminal_production_batch.json).

### Target Assets:
1. **Character Turnarounds (8 views)**: Front, 3/4 R, Profile R, Back-3/4 R, Full Back, Back-3/4 L, Profile L, 3/4 L. Ensures consistent adult male appearance across all future scenes and camera cuts.
2. **Hands & Object Contact (6 macro angles)**: Knuckles, lever depression, door pulling, bare feet on floor, hand on bed edge. Eliminates hand morphing in video generators.
3. **Room Background & Clean Plates (8 variations)**: Unoccupied room clean plate, hallway illumination spill, door swing increments (15°, 30°, 45°, 60°, 75°, 90°).
4. **Wan 2.2 / LTX Image-to-Video Anchor Controls (10 key moments)**:
   - Waking in bed
   - Halfway sitting up
   - Sitting on bed edge
   - Rising to stand
   - Beginning stride
   - Mid-stride
   - Reaching door handle
   - Depressing handle
   - Pulling door open
   - Standing in illuminated doorway

### Staged Phased Rollout (56 Expected Images, 80 Maximum Spend Cap)
To verify quality before spending the full budget:
- **Phase 1 (Visual Review Gate - Completed)**:
  - 8 select representative assets (1 turnaround, 1 hand macro, 1 door swing, 1 clean plate, 4 video anchors).
  - 1 candidate each @ `quality=high` ($0.20): **8 images = $1.60 total spent**.
  - Review completed: useful asset candidates identified, held for human review gate without automatic production acceptance.
- **Phase 2 Resumption (Remaining 24 Keys × 2 Candidates)**:
  - Existing 8 jobs (n=1) remain immutable and are skipped during resumption.
  - Remaining 24 keys generate 2 candidates each (`--n 2` @ `quality=high`): **48 new images = $9.60 nominal cost**.
  - **Expected Total Images**: 8 (Phase 1) + 48 (Resumption) = **56 images** (**$11.20 expected nominal spend**).
  - **Maximum Cap Ceiling**: 80 images / $16.00 maximum spend ceiling (correcting previous theoretical 72 remaining calculation; actual resumption produces 48 new candidates across the 24 unexecuted keys).

---

## 5. Execution Commands

> [!IMPORTANT]
> As instructed, **no paid Luminal credit calls have been executed yet**. All assets and specs are prepared and validated for the user and Codex to review.

When approved, run the Phase 1 visual review batch:
```bash
python3 scripts/keyframes.py specs/luminal_production_batch.json \
  --only char_turn_front char_turn_profile_r hand_handle_grip_macro door_swing_45deg bg_clean_plate_room wan_ctrl_wake_sit wan_ctrl_walk_mid wan_ctrl_door_open \
  --n 1 --quality high --cap 2.0
```

To run the full remaining batch up to the $16.00 cap:
```bash
python3 scripts/keyframes.py specs/luminal_production_batch.json \
  --n 2 --quality high --cap 16.0
```
