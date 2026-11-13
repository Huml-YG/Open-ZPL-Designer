"""Render a product label to a 1-bit bitmap and wrap it in ZPL (^GFA).

Everything (fonts, diacritics, QR, logo, rotation) is rasterised here, so the
printer only needs to understand the basic ZPL graphic-field command - which
the GoDEX ZPL emulation handles reliably.
"""

from __future__ import annotations

import socket
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.toml"
LOGO_PATH = ROOT / "assets" / "logo.png"


def load_config() -> dict:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def dots(mm: float, dpi: int) -> int:
    return round(mm * dpi / 25.4)


@lru_cache
def _font_file(path: str, bold: bool) -> str:
    if path:
        return path
    pattern = "DejaVu Sans:bold" if bold else "DejaVu Sans"
    res = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError("No font found - set [fonts] regular/bold in config.toml")
    return res.stdout.strip()


def _font(cfg: dict, bold: bool, size_px: int) -> ImageFont.FreeTypeFont:
    path = cfg.get("fonts", {}).get("bold" if bold else "regular", "")
    return ImageFont.truetype(_font_file(path, bold), max(size_px, 6))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.strip().split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if draw.textlength(cur + " " + w, font=font) <= max_w:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _load_logo(max_w: int, max_h: int, dither: bool) -> Image.Image | None:
    if not LOGO_PATH.exists():
        return None
    img = Image.open(LOGO_PATH)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, "white")
        img = Image.alpha_composite(bg, img)
    img = img.convert("L")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    if dither:
        return img.convert("1").convert("L")
    return img.point(lambda p: 0 if p < 128 else 255)


def _qr(data: str, size_px: int) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    n = qr.modules_count
    module = max(size_px // n, 1)  # whole dots per module -> crisp, scannable
    return qr.make_image(fill_color="black", back_color="white").get_image().convert("L").resize(
        (n * module, n * module), Image.Resampling.NEAREST
    )


def render(fields: dict, cfg: dict | None = None) -> Image.Image:
    """Render the label in its portrait design orientation as a 1-bit image."""
    cfg = cfg or load_config()
    dpi = cfg["printer"]["dpi"]
    lab, lay = cfg["label"], cfg["layout"]

    # Portrait canvas: short side of the stock is the width.
    short, long_ = sorted((lab["stock_width_mm"], lab["stock_height_mm"]))
    W, H = dots(short, dpi), dots(long_, dpi)
    m = dots(lay["margin_mm"], dpi)
    inner_w = W - 2 * m
    gap = dots(1.5, dpi)

    canvas = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(canvas)
    top, bottom = m, H - m

    # --- logo (top) ---
    logo = _load_logo(inner_w, dots(lay["logo_max_height_mm"], dpi), lay.get("logo_dither", False))
    if logo and fields.get("show_logo", True):
        canvas.paste(logo, ((W - logo.width) // 2, top))
        top += logo.height + gap

    # --- QR + caption (bottom) ---
    qr_data = (fields.get("qr_data") or "").strip()
    caption = (fields.get("qr_caption") or "").strip()
    if caption:
        cf = _font(cfg, False, dots(lay["caption_size_mm"], dpi))
        for line in reversed(_wrap(draw, caption, cf, inner_w)):
            lh = round(cf.size * 1.15)
            bottom -= lh
            draw.text((W // 2, bottom), line, font=cf, fill=0, anchor="ma")
        bottom -= gap // 2
    if qr_data:
        q = _qr(qr_data, dots(lay["qr_size_mm"], dpi))
        bottom -= q.height
        canvas.paste(q, ((W - q.width) // 2, bottom))
        bottom -= gap

    # --- text block (middle), shrunk uniformly until it fits ---
    blocks = [
        (fields.get("title", ""), True, lay["title_size_mm"], "center"),
        (fields.get("subtitle", ""), False, lay["subtitle_size_mm"], "center"),
        (fields.get("details", ""), False, lay["details_size_mm"], "left"),
    ]
    blocks = [b for b in blocks if b[0] and b[0].strip()]
    avail = bottom - top
    layout = []
    for scale in [s / 100 for s in range(100, 29, -4)]:
        layout, total = [], 0
        fits = True
        for text, bold, size_mm, align in blocks:
            f = _font(cfg, bold, dots(size_mm * scale, dpi))
            lines = _wrap(draw, text, f, inner_w)
            if any(draw.textlength(l, font=f) > inner_w for l in lines):
                fits = False
            lh = round(f.size * 1.2)
            layout.append((lines, f, lh, align))
            total += lh * len(lines) + gap // 2
        if fits and total <= avail:
            break
    y = top
    for lines, f, lh, align in layout:
        for line in lines:
            if align == "center":
                draw.text((W // 2, y), line, font=f, fill=0, anchor="ma")
            else:
                draw.text((m, y), line, font=f, fill=0)
            y += lh
        y += gap // 2

    canvas = canvas.point(lambda p: 0 if p < 128 else 255)

    # Calibration shift in design (portrait) coordinates; content pushed past
    # the edge is cropped, the exposed area stays white.
    dx = dots(lab.get("shift_right_mm", 0), dpi)
    dy = dots(lab.get("shift_down_mm", 0), dpi)
    if dx or dy:
        shifted = Image.new("L", (W, H), 255)
        shifted.paste(canvas, (dx, dy))
        canvas = shifted
    return canvas.convert("1")


def to_print_orientation(img: Image.Image, cfg: dict) -> Image.Image:
    rot = cfg["label"].get("rotate", 0) % 360
    # PIL rotates counter-clockwise; config is clockwise.
    return img.rotate(-rot, expand=True) if rot else img


def to_zpl(img: Image.Image, cfg: dict, copies: int = 1) -> str:
    """Convert a 1-bit design image into a complete ZPL job."""
    img = to_print_orientation(img, cfg)
    dpi = cfg["printer"]["dpi"]
    lab = cfg["label"]
    ll = dots(lab["stock_height_mm"], dpi)
    # GoDEX centres a ^PW narrower than the head, which shifts the origin
    # unpredictably. Always use the full head width so x=0 is the head edge
    # (as on the calibration ruler) and place the label at head_offset_mm.
    x0 = dots(lab.get("head_offset_mm", 0), dpi)
    pw = dots(cfg["printer"].get("head_width_mm", 105.7), dpi)

    # Pad width to a multiple of 8 with white so row padding bits stay blank.
    w8 = (img.width + 7) // 8 * 8
    if w8 != img.width:
        padded = Image.new("1", (w8, img.height), 1)
        padded.paste(img, (0, 0))
        img = padded
    # PIL mode "1": bit 1 = white. ZPL: bit 1 = black -> invert.
    raw = bytes(b ^ 0xFF for b in img.tobytes())
    bpr = w8 // 8

    cmds = ["^XA", f"^PW{pw}", f"^LL{ll}", "^LH0,0"]
    p = cfg["printer"]
    if "darkness" in p:
        cmds.append(f"^MD{p['darkness']}")
    if "speed" in p:
        cmds.append(f"^PR{p['speed']}")
    cmds.append(f"^FO{x0},0^GFA,{len(raw)},{len(raw)},{bpr},{raw.hex().upper()}^FS")
    cmds.append(f"^PQ{max(1, int(copies))}")
    cmds.append("^XZ")
    return "\n".join(cmds) + "\n"


def calibration_zpl(cfg: dict) -> str:
    """A ruler across the full print head, in raw printer coordinates.

    Shows where x=0 / y=0 land on the physical label, so head_offset_mm and
    shift_* can be read off directly instead of guessed.
    """
    dpi = cfg["printer"]["dpi"]
    head_mm = cfg["printer"].get("head_width_mm", 105.7)
    W, H = dots(head_mm, dpi), dots(cfg["label"]["stock_height_mm"], dpi)
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    num = _font(cfg, True, dots(2.6, dpi))
    small = _font(cfg, False, dots(2.2, dpi))

    # x ruler (across the head) in the middle of the label
    mid = H // 2
    for v in range(int(head_mm) + 1):
        x = dots(v, dpi)
        tick = 6 if v % 10 == 0 else 4 if v % 5 == 0 else 2
        d.line([(x, mid - dots(tick, dpi)), (x, mid)], fill=0, width=2)
        if v % 10 == 0:
            d.text((x + 4, mid + dots(0.8, dpi)), str(v), font=num, fill=0)
    d.line([(0, mid), (W, mid)], fill=0, width=2)
    d.text((dots(2, dpi), mid + dots(5, dpi)), "x [mm] across head ->", font=small, fill=0)

    # y ruler (feed direction) near x = 30 mm
    xr = dots(30, dpi)
    for v in range(int(cfg["label"]["stock_height_mm"]) + 1):
        y = dots(v, dpi)
        tick = 5 if v % 10 == 0 else 3 if v % 5 == 0 else 1.5
        d.line([(xr, y), (xr + dots(tick, dpi), y)], fill=0, width=2)
        if v % 10 == 0 and 0 < v < cfg["label"]["stock_height_mm"]:
            d.text((xr + dots(6, dpi), y), f"y{v}", font=small, fill=0, anchor="lm")
    d.line([(xr, 0), (xr, H)], fill=0, width=2)
    d.text((dots(32, dpi), dots(1, dpi)), "y=0 (first out?)", font=small, fill=0)

    img = img.point(lambda p: 0 if p < 128 else 255).convert("1")
    w8 = (W + 7) // 8 * 8
    padded = Image.new("1", (w8, H), 1)
    padded.paste(img, (0, 0))
    raw = bytes(b ^ 0xFF for b in padded.tobytes())
    return (f"^XA\n^PW{W}\n^LL{H}\n^LH0,0\n"
            f"^FO0,0^GFA,{len(raw)},{len(raw)},{w8 // 8},{raw.hex().upper()}^FS\n^PQ1\n^XZ\n")


def send(zpl: str, cfg: dict) -> None:
    p = cfg["printer"]
    with socket.create_connection((p["host"], p.get("port", 9100)), timeout=5) as s:
        s.sendall(zpl.encode("ascii"))
