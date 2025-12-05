# Halation Lab (Flask + FFmpeg)

<img width="721" height="1056" alt="Screenshot 2025-12-05 at 00 00 51" src="https://github.com/user-attachments/assets/9625baa5-fcf7-411e-838d-3a04cd7610e6" />


Single-page Flask app for generating halation/glow previews from images or videos. Upload a file via drag-and-drop UI (in `templates/index.html`), configure ranges, and get multiple PNG variants rendered in the background using FFmpeg.

This README matches the `app.py` shown below (no LUT support):

```python
# app.py (summary)
# - spa() -> renders templates/index.html
# - /api/start -> accepts file + params, enqueues a job
# - /api/status/<job_id> -> progress + list of generated frames
# - /results/<job_id>/<name>.png -> fetch variant images
# Halation graph: threshold -> blur -> tint -> screen blend
```

---

## Features

* Drag-and-drop upload (handled in `index.html`).
* Halation effect via FFmpeg filter graph:

  * threshold (highlight isolation)
  * gaussian blur
  * optional tint: neutral / warm / cool
  * screen blend over base
* Even spacing between min/max ranges for threshold, blur sigma, opacity.
* Live polling for previews while a background worker produces PNGs.
* Video inputs: mid-point frame is used for previews.

---

## Requirements

* Python 3.10+
* FFmpeg (ffmpeg and ffprobe available on PATH)

  * macOS (Homebrew): `brew install ffmpeg`
  * Ubuntu/Debian: `sudo apt-get install ffmpeg`
  * Windows: install FFmpeg and add to PATH

---

## Setup

```bash
git clone <repo-url> halation-ffmpeg-flask
cd halation-ffmpeg-flask

python3 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install Flask==3.0.3 Werkzeug==3.0.3
python app.py
```

Open: `http://127.0.0.1:5000`

---

## Usage

1. Drag and drop an image or video onto the upload area.
2. Adjust settings:

   * Variants (1–36)
   * Threshold min/max (200–255)
   * Blur sigma min/max (1–20)
   * Opacity min/max (0.05–0.9)
   * Tint: neutral, warm, cool
3. Start the job. Thumbnails appear as they are generated.
4. Click a preview URL (served from `/results/<job_id>/<name>.png`) if needed.

Notes:

* For videos, a representative frame is taken around the midpoint for previews.
* Ranges are evenly distributed across the chosen number of variants.

---

## API

### `POST /api/start`

Start a processing job.

Form fields (multipart/form-data):

* `file` (required): image or video
* `count` (int, 1–36; default 12)
* `thr_min` (int, default 225)
* `thr_max` (int, default 240)
* `sig_min` (int, default 6)
* `sig_max` (int, default 14)
* `op_min` (float, default 0.18)
* `op_max` (float, default 0.30)
* `tint` (`neutral|warm|cool`; default `neutral`)

Response:

```json
{ "job_id": "abcdef1234..." }
```

### `GET /api/status/<job_id>`

Poll job status.

Response:

```json
{
  "status": "queued|running|done|error",
  "progress": "N/T",
  "generated": ["H01","H02", "..."],
  "error": null
}
```

### `GET /results/<job_id>/<name>.png`

Fetch a rendered preview.

---

## Filter Graph (per variant)

```
[0:v]format=yuv444p,split=2[b][h];
[h]lut=y='if(gte(val,THRESHOLD),val,0)',gblur=sigma=SIGMA[soft];
[soft]TINT_STAGE[hal];
[b][hal]blend=all_mode=screen:all_opacity=OPACITY[v]
```

* `THRESHOLD`: highlight isolation (e.g., 225–240).
* `SIGMA`: gaussian blur amount (e.g., 6–14).
* `OPACITY`: blend strength (e.g., 0.18–0.30).
* `TINT_STAGE`:

  * neutral: `hue=s=0`
  * warm: `colorchannelmixer=rr=1.05:gg=1.00:bb=0.98`
  * cool:  `colorchannelmixer=rr=0.99:gg=1.00:bb=1.04`

---

## Project Structure

```
.
├─ app.py
├─ templates/
│  └─ index.html
├─ static/
│  └─ style.css
├─ uploads/    # runtime (ignored)
├─ results/    # runtime (ignored)
└─ README.md
```

Recommended `.gitignore` entries:

```
uploads/
results/
```

---

## Full-Video Export (outside the app)

To apply one chosen look to a whole video and keep audio:

```bash
ffmpeg -i input.mp4 \
-filter_complex "[0:v]format=yuv444p,split=2[b][h];[h]lut=y='if(gte(val,235),val,0)',gblur=sigma=10[soft];[soft]hue=s=0[hal];[b][hal]blend=all_mode=screen:all_opacity=0.22[v]" \
-map "[v]" -map "0:a?" -c:v libx264 -crf 18 -preset slow -c:a copy out_halation.mp4
```

Adjust threshold/sigma/opacity and tint to taste.

---

## Troubleshooting

* `TemplateNotFound`
  Ensure `templates/index.html` exists and `app.py` is run from the project root.

* `ffmpeg/ffprobe not found`
  Install FFmpeg and ensure both are on PATH. Restart the shell.

* No output images
  Check console for FFmpeg errors. Some codecs or corrupted files may fail.

* Git index lock after interruption

  ```
  rm -f .git/index.lock
  git reset
  ```

---

## License

MIT (or project’s chosen license).
