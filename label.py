"""Turn label bitmaps from the web designer into ZPL (^GFA) and send them.

The designer rasterises everything (fonts, diacritics, QR, images) in the
browser, so the printer only needs the basic ZPL graphic-field command -
which the GoDEX ZPL emulation handles reliably.
"""

from __future__ import annotations

import io
import socket
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.toml"


def load_config() -> dict:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def dots(mm: float, dpi: int) -> int:
    return round(mm * dpi / 25.4)


@lru_cache
def _font_file(path: str, bold: bool) -> str:
    if path:
        p = Path(path)
        return str(p if p.is_absolute() else ROOT / p)
    pattern = "DejaVu Sans:bold" if bold else "DejaVu Sans"
    res = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError("No font found - set [fonts] regular/bold in config.toml")
    return res.stdout.strip()


def _font(cfg: dict, bold: bool, size_px: int) -> ImageFont.FreeTypeFont:
    fonts = cfg.get("fonts", {})
    path = fonts.get("bold" if bold else "regular", "")
    weight = fonts.get("bold_weight" if bold else "regular_weight", 700 if bold else 400)
    dpi = cfg["printer"]["dpi"]
    return _load_font(_font_file(path, bold), max(size_px, 6), weight, dpi)


@lru_cache(maxsize=256)
def _load_font(file: str, size_px: int, weight: int, dpi: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(file, size_px)
    try:
        axes = font.get_variation_axes()
    except OSError:
        return font  # static font: weight comes from the file itself
    # Variable font: set weight, and optical size to the real printed point size.
    point_size = size_px / dpi * 72
    values = []
    for ax in axes:
        name = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
        if name == "Weight":
            v = weight
        elif name == "Optical size":
            v = point_size
        else:
            v = ax["default"]
        values.append(min(max(v, ax["minimum"]), ax["maximum"]))
    font.set_variation_by_axes(values)
    return font


def design_size(cfg: dict) -> tuple[int, int]:
    """Portrait design canvas in dots: the short side of the stock is the width."""
    dpi, lab = cfg["printer"]["dpi"], cfg["label"]
    short, long_ = sorted((lab["stock_width_mm"], lab["stock_height_mm"]))
    return dots(short, dpi), dots(long_, dpi)


def qr_image(data: str, ec: str = "M") -> Image.Image:
    """QR code with 1 pixel per module and no quiet zone."""
    levels = {"L": qrcode.constants.ERROR_CORRECT_L, "M": qrcode.constants.ERROR_CORRECT_M,
              "Q": qrcode.constants.ERROR_CORRECT_Q, "H": qrcode.constants.ERROR_CORRECT_H}
    qr = qrcode.QRCode(error_correction=levels.get(ec, levels["M"]), border=0, box_size=1)
    qr.add_data(data or " ")
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image().convert("L")


def finalize(canvas: Image.Image, cfg: dict) -> Image.Image:
    """Threshold a grayscale design image to 1-bit and apply the shift calibration."""
    dpi, lab = cfg["printer"]["dpi"], cfg["label"]
    canvas = canvas.convert("L").point(lambda p: 0 if p < 128 else 255)
    # Calibration shift in design (portrait) coordinates; content pushed past
    # the edge is cropped, the exposed area stays white.
    dx = dots(lab.get("shift_right_mm", 0), dpi)
    dy = dots(lab.get("shift_down_mm", 0), dpi)
    if dx or dy:
        shifted = Image.new("L", canvas.size, 255)
        shifted.paste(canvas, (dx, dy))
        canvas = shifted
    return canvas.convert("1")


def image_from_png(data: bytes, cfg: dict) -> Image.Image:
    """Turn a design bitmap made by the web editor into a print-ready 1-bit image."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img).convert("L")
    size = design_size(cfg)
    if img.size != size:  # should not happen; never stretch - pad/crop instead
        fixed = Image.new("L", size, 255)
        fixed.paste(img, (0, 0))
        img = fixed
    return finalize(img, cfg)


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
    d.text((dots(32, dpi), dots(1, dpi)), "y=0 (comes out last)", font=small, fill=0)

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
