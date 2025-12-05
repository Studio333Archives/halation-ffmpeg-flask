import os, shutil, uuid, math, mimetypes, subprocess, threading, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from flask import Flask, render_template, request, send_from_directory, jsonify

# -------------------------------
# Directories / Flask setup
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "results"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(TEMPLATES_DIR))
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB

# -------------------------------
# Simple job store
# -------------------------------
jobs = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=2)

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif", ".heic", ".heif"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mxf", ".mpg", ".mpeg", ".3gp"}

def secure_name(fn: str) -> str:
    fn = os.path.basename(fn)
    return "".join(c for c in fn if c.isalnum() or c in ("-", "_", ".", " ")).strip().replace(" ", "_")

def is_image(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in ALLOWED_IMAGE_EXT: return True
    mt, _ = mimetypes.guess_type(str(path))
    return bool(mt and mt.startswith("image/"))

def is_video(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in ALLOWED_VIDEO_EXT: return True
    mt, _ = mimetypes.guess_type(str(path))
    return bool(mt and mt.startswith("video/"))

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "ffmpeg error")
    return p.stdout, p.stderr

def ffprobe_duration(p: Path) -> float:
    try:
        out, _ = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)])
        return float(out.strip())
    except Exception:
        return 0.0

def build_filter(threshold: int, sigma: int, opacity: float, tint: str) -> str:
    if tint == "warm":
        tint_stage = "colorchannelmixer=rr=1.05:gg=1.00:bb=0.98"
    elif tint == "cool":
        tint_stage = "colorchannelmixer=rr=0.99:gg=1.00:bb=1.04"
    else:
        tint_stage = "hue=s=0"
    return (
        f"[0:v]format=yuv444p,split=2[b][h];"
        f"[h]lut=y='if(gte(val,{threshold}),val,0)',gblur=sigma={sigma}[soft];"
        f"[soft]{tint_stage}[hal];"
        f"[b][hal]blend=all_mode=screen:all_opacity={opacity}[v]"
    )

def spaced_values(vmin, vmax, n, caster):
    if n <= 1: return [caster(vmin)]
    step = (vmax - vmin) / (n - 1)
    return [caster(vmin + i*step) for i in range(n)]

def process_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job: return
        job["status"] = "running"

    src = Path(job["src"])
    out_dir = Path(job["out_dir"])
    count = job["count"]
    thr_vals = spaced_values(job["thr_min"], job["thr_max"], count, int)
    sig_vals = spaced_values(job["sig_min"], job["sig_max"], count, int)
    op_vals  = spaced_values(job["op_min"], job["op_max"], count, float)
    tint = job["tint"]

    # pick frame (videos)
    ts = "00:00:01.000"
    if is_video(src):
        dur = ffprobe_duration(src)
        mid = max(1.0, dur / 2.0)
        ts = f"00:00:{int(mid):02d}.000"

    generated = []
    try:
        for i in range(count):
            name = f"H{i+1:02d}"
            out_png = out_dir / f"{name}.png"
            thr = thr_vals[i]
            sig = max(1, sig_vals[i])
            op  = max(0.01, min(0.95, round(op_vals[i], 2)))
            flt = build_filter(thr, sig, op, tint)

            if is_image(src):
                cmd = ["ffmpeg","-hide_banner","-loglevel","warning","-i",str(src),
                       "-filter_complex",flt,"-map","[v]","-frames:v","1","-update","1","-y",str(out_png)]
            else:
                cmd = ["ffmpeg","-hide_banner","-loglevel","warning","-i",str(src),"-ss",ts,
                       "-filter_complex",flt,"-map","[v]","-frames:v","1","-update","1","-y",str(out_png)]

            try:
                run(cmd)
                if out_png.exists() and out_png.stat().st_size>0:
                    generated.append(name)
            except Exception:
                pass

            with jobs_lock:
                j = jobs.get(job_id)
                if not j or j["status"] == "canceled": return
                j["generated"] = generated.copy()
                j["progress"] = f"{len(generated)}/{count}"

        with jobs_lock:
            j = jobs.get(job_id)
            if j: j["status"] = "done"
    except Exception as e:
        with jobs_lock:
            j = jobs.get(job_id)
            if j:
                j["status"] = "error"
                j["error"] = str(e)

# -------------------------------
# Routes
# -------------------------------
@app.route("/")
def spa():
    return render_template("index.html")

@app.route("/api/start", methods=["POST"])
def api_start():
    f = request.files.get("file")
    if not f or not f.filename.strip():
        return jsonify({"error":"no_file"}), 400

    filename = f"{uuid.uuid4().hex}_{secure_name(f.filename)}"
    dest = UPLOAD_DIR / filename
    f.save(dest)

    # params
    try:
        count = max(1, min(36, int(request.form.get("count","12"))))
        thr_min = int(request.form.get("thr_min","225"))
        thr_max = int(request.form.get("thr_max","240"))
        sig_min = int(request.form.get("sig_min","6"))
        sig_max = int(request.form.get("sig_max","14"))
        op_min  = float(request.form.get("op_min","0.18"))
        op_max  = float(request.form.get("op_max","0.30"))
        tint = request.form.get("tint","neutral")
        if tint not in ("neutral","warm","cool"):
            tint = "neutral"
    except ValueError:
        return jsonify({"error":"bad_params"}), 400

    job_id = uuid.uuid4().hex
    out_dir = RESULTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with jobs_lock:
        jobs[job_id] = {
            "id": job_id, "status": "queued", "src": str(dest), "out_dir": str(out_dir),
            "generated": [], "progress": "0/0",
            "count": count, "thr_min": thr_min, "thr_max": thr_max,
            "sig_min": sig_min, "sig_max": sig_max,
            "op_min": op_min, "op_max": op_max,
            "tint": tint,
        }

    executor.submit(process_job, job_id)
    return jsonify({"job_id": job_id})

@app.route("/api/status/<job_id>")
def api_status(job_id):
    with jobs_lock:
        j = jobs.get(job_id)
        if not j: return jsonify({"error":"not_found"}), 404
        return jsonify({
            "status": j["status"],
            "progress": j["progress"],
            "generated": j["generated"],
            "error": j.get("error"),
        })

@app.route("/results/<job_id>/<name>.png")
def get_png(job_id, name):
    d = RESULTS_DIR / job_id
    return send_from_directory(d, f"{name}.png", max_age=0)

@app.route("/uploads/<path:fname>")
def get_upload(fname):
    return send_from_directory(UPLOAD_DIR, fname, max_age=0)

if __name__ == "__main__":
    for tool in ("ffmpeg","ffprobe"):
        if shutil.which(tool) is None:
            print(f"[ERROR] {tool} not in PATH"); raise SystemExit(1)
    app.run(host="127.0.0.1", port=5000, debug=True)
