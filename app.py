"""Local web app for designing and printing product labels (drag & drop designer).

Run:  uv run app.py   then open http://127.0.0.1:5000
"""

import base64
import io
import json
import re

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory
from PIL import ImageFont

import label

app = Flask(__name__)
FONTS_DIR = label.ROOT / "assets" / "fonts"
DESIGNS_DIR = label.ROOT / "designs"


def _send_or_error(zpl: str, cfg: dict, copies: int = 1):
    try:
        label.send(zpl, cfg)
    except OSError as e:
        return jsonify(ok=False, error=f"Cannot reach printer {cfg['printer']['host']}: {e}"), 502
    return jsonify(ok=True, copies=copies)


def _copies(value) -> int:
    try:
        return max(1, min(int(value or 1), 9999))
    except ValueError:
        return 1


# ---------------------------------------------------------------- editor ---

@app.get("/")
def editor():
    return render_template("editor.html")


@app.get("/api/config")
def api_config():
    cfg = label.load_config()
    w, h = label.design_size(cfg)
    return jsonify(dpi=cfg["printer"]["dpi"], width=w, height=h,
                   margin_mm=cfg["layout"]["margin_mm"], printer=cfg["printer"]["host"],
                   rotate=cfg["label"].get("rotate", 0) % 360,
                   feed_flip=bool(cfg["label"].get("feed_flip", False)),
                   corner_radius_mm=cfg["label"].get("corner_radius_mm", 0))


@app.get("/api/fonts")
def api_fonts():
    fonts = []
    for f in sorted(FONTS_DIR.glob("*.[ot]tf")):
        family = ImageFont.truetype(str(f), 10).getname()[0]
        fonts.append({"family": family, "url": f"/fonts/{f.name}"})
    return jsonify(fonts)


@app.get("/fonts/<path:name>")
def font_file(name):
    return send_from_directory(FONTS_DIR, name)


@app.post("/api/qr")
def api_qr():
    d = request.get_json(silent=True) or {}
    img = label.qr_image(d.get("data", ""), d.get("ec", "M"))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    src = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return jsonify(src=src, modules=img.width)


def _editor_zpl():
    """ZPL from the bitmap the editor rendered (multipart: image, copies)."""
    file = request.files.get("image")
    if not file:
        abort(400, "missing image")
    cfg = label.load_config()
    copies = _copies(request.form.get("copies"))
    return label.to_zpl(label.image_from_png(file.read(), cfg), cfg, copies), cfg, copies


@app.post("/api/print")
def api_print():
    zpl, cfg, copies = _editor_zpl()
    return _send_or_error(zpl, cfg, copies)


@app.post("/api/zpl")
def api_zpl():
    zpl, _, _ = _editor_zpl()
    return Response(zpl, mimetype="text/plain",
                    headers={"Content-Disposition": "attachment; filename=label.zpl"})


# --- saved designs (designs/<name>.json) ---

def _design_path(name: str):
    if not re.fullmatch(r"[\w\- .]{1,80}", name) or name.startswith("."):
        abort(400, "invalid design name")
    return DESIGNS_DIR / f"{name}.json"


@app.get("/api/designs")
def list_designs():
    return jsonify(sorted(p.stem for p in DESIGNS_DIR.glob("*.json")))


@app.get("/api/designs/<name>")
def get_design(name):
    p = _design_path(name)
    if not p.exists():
        abort(404)
    return Response(p.read_text(encoding="utf-8"), mimetype="application/json")


@app.put("/api/designs/<name>")
def save_design(name):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "expected JSON object")
    DESIGNS_DIR.mkdir(exist_ok=True)
    _design_path(name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return jsonify(ok=True)


@app.delete("/api/designs/<name>")
def delete_design(name):
    _design_path(name).unlink(missing_ok=True)
    return jsonify(ok=True)


# --------------------------------------------------------------- printer ---

@app.post("/calibrate")
def calibrate():
    cfg = label.load_config()
    return _send_or_error(label.calibration_zpl(cfg), cfg)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
