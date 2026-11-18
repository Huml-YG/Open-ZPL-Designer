"""Settings dialog support: read, validate and write config.toml.

Writes go through tomlkit, so comments and layout in config.toml survive.
Each setting is described once in FIELDS (section, key, type, limits).
"""

from __future__ import annotations

import os
import socket
import tempfile

import tomlkit

import label

# name -> (section, key, kind, min, max, optional)
# kind: str | int | float | bool | choice:<a>|<b>
FIELDS = {
    "host":                  ("printer", "host", "str", None, None, False),
    "port":                  ("printer", "port", "int", 1, 65535, False),
    "dpi":                   ("printer", "dpi", "choice:203|300|600", None, None, False),
    "darkness":              ("printer", "darkness", "int", -30, 30, True),
    "speed":                 ("printer", "speed", "int", 1, 14, True),
    "dither_gamma":          ("printer", "dither_gamma", "float", 0.05, 5, False),
    "dither_preview_gamma":  ("printer", "dither_preview_gamma", "float", 0.1, 10, False),
    "dither_preview_slider": ("printer", "dither_preview_slider", "float", 0.1, 5, False),
    "stock_width_mm":        ("label", "stock_width_mm", "float", 5, 120, False),
    "stock_height_mm":       ("label", "stock_height_mm", "float", 5, 400, False),
    "corner_radius_mm":      ("label", "corner_radius_mm", "float", 0, 20, False),
    "orientation":           ("label", "orientation", "choice:portrait|landscape", None, None, False),
    "shift_down_mm":         ("label", "shift_down_mm", "float", -30, 30, False),
    "shift_right_mm":        ("label", "shift_right_mm", "float", -30, 30, False),
    "feed_flip":             ("label", "feed_flip", "bool", None, None, False),
    "margin_mm":             ("layout", "margin_mm", "float", 0, 20, False),
}
DEFAULTS = {"port": 9100, "dpi": 300, "dither_gamma": 1.0, "dither_preview_gamma": 1.0,
            "dither_preview_slider": 1.0, "corner_radius_mm": 0.0, "orientation": "portrait",
            "shift_down_mm": 0.0, "shift_right_mm": 0.0, "feed_flip": False, "margin_mm": 3.0}


def current(cfg: dict | None = None) -> dict:
    cfg = cfg or label.load_config()
    out = {name: cfg.get(sec, {}).get(key, DEFAULTS.get(name)) for name, (sec, key, *_) in FIELDS.items()}
    out["dpi"] = str(out["dpi"])
    out["flip"] = cfg["label"].get("rotate", 0) % 360 in (90, 180)   # "print rotated 180°"
    return out


def _parse(name: str, value):
    sec, key, kind, lo, hi, optional = FIELDS[name]
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if optional:
            return None
        raise ValueError(f"{name}: a value is required")
    if kind == "str":
        v = str(value).strip()
        if any(c.isspace() for c in v):
            raise ValueError(f"{name}: must not contain spaces")
        return v
    if kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"{name}: expected true/false")
    if kind.startswith("choice:"):
        choices = kind[7:].split("|")
        if str(value) not in choices:
            raise ValueError(f"{name}: must be one of {', '.join(choices)}")
        return int(value) if name == "dpi" else str(value)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: not a number") from None
    if kind == "int":
        if v != int(v):
            raise ValueError(f"{name}: must be a whole number")
        v = int(v)
    if not (lo <= v <= hi):
        raise ValueError(f"{name}: must be between {lo} and {hi}")
    return v


def save(data: dict) -> None:
    """Validate everything first, then write config.toml in one go."""
    values = {name: _parse(name, data.get(name)) for name in FIELDS}
    flip = data.get("flip", False)
    if not isinstance(flip, bool):
        raise ValueError("flip: expected true/false")

    path = label.CONFIG_PATH
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    for name, v in values.items():
        sec, key, *_ = FIELDS[name]
        table = doc.setdefault(sec, tomlkit.table())
        if v is None:
            table.pop(key, None)
        elif key in table and table[key] == v:
            continue                      # unchanged: keep the original formatting
        else:
            table[key] = v
    lab = {k: values[k] for k in ("stock_width_mm", "stock_height_mm", "orientation")}
    rot = label.auto_rotate(lab, flip)
    if doc["label"].get("rotate") != rot:
        doc["label"]["rotate"] = rot

    # atomic replace, so a crash never leaves a half-written config
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config.", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def test_connection(host: str, port: int) -> str:
    """Open (and close) a TCP connection to the printer's raw port."""
    with socket.create_connection((host, port), timeout=3):
        pass
    return f"{host}:{port} is reachable"
