"""Local web form for designing and printing product labels.

Run:  uv run app.py   then open http://127.0.0.1:5000
"""

import io

from flask import Flask, Response, jsonify, render_template, request

import label

app = Flask(__name__)


def _fields() -> dict:
    data = request.get_json(silent=True) or {}
    return {
        "title": data.get("title", ""),
        "subtitle": data.get("subtitle", ""),
        "details": data.get("details", ""),
        "qr_data": data.get("qr_data", ""),
        "qr_caption": data.get("qr_caption", ""),
        "show_logo": bool(data.get("show_logo", True)),
        "copies": int(data.get("copies") or 1),
    }


@app.get("/")
def index():
    cfg = label.load_config()
    return render_template("index.html", cfg=cfg, has_logo=label.LOGO_PATH.exists())


@app.post("/preview")
def preview():
    img = label.render(_fields())
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png")


@app.post("/zpl")
def zpl():
    f = _fields()
    cfg = label.load_config()
    body = label.to_zpl(label.render(f, cfg), cfg, f["copies"])
    return Response(body, mimetype="text/plain",
                    headers={"Content-Disposition": "attachment; filename=label.zpl"})


@app.post("/print")
def print_label():
    f = _fields()
    cfg = label.load_config()
    try:
        label.send(label.to_zpl(label.render(f, cfg), cfg, f["copies"]), cfg)
    except OSError as e:
        return jsonify(ok=False, error=f"Cannot reach printer {cfg['printer']['host']}: {e}"), 502
    return jsonify(ok=True, copies=f["copies"])


@app.post("/calibrate")
def calibrate():
    cfg = label.load_config()
    try:
        label.send(label.calibration_zpl(cfg), cfg)
    except OSError as e:
        return jsonify(ok=False, error=f"Cannot reach printer {cfg['printer']['host']}: {e}"), 502
    return jsonify(ok=True, copies=1)


@app.post("/logo")
def upload_logo():
    file = request.files.get("logo")
    if not file:
        return jsonify(ok=False, error="No file"), 400
    from PIL import Image
    Image.open(file.stream).save(label.LOGO_PATH, "PNG")
    return jsonify(ok=True)


@app.delete("/logo")
def delete_logo():
    label.LOGO_PATH.unlink(missing_ok=True)
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
