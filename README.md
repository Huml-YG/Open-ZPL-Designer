# Label printing (GoDEX G530, ZPL)

A local web app for designing and printing product labels. It's a drag-and-drop designer, like a small Canva. You can add text, images (including SVG), your logo, QR codes and shapes. Move, resize and rotate them with the mouse, set fonts, sizes and weights in the side panel, and save designs by name. **1-bit preview** shows exactly what the printer will get. **Print** (or Ctrl+P) sends the label to the printer.

## How it works

The designer draws the label in the browser at exactly 300 dpi (1 canvas pixel = 1 printer dot), so what you see is what prints. Images are converted to black and white right in the editor: *threshold* mode for logos, *dither* mode for photos. On Print, the browser sends the finished bitmap to the server.

The server applies the calibration from `config.toml` (rotation and offsets). It sends the bitmap as a single ZPL `^GFA` graphic field to the printer's raw port 9100. The job only uses basic ZPL commands (`^XA ^PW ^LL ^LH ^FO ^GFA ^PQ ^XZ`), which GoDEX's ZPL emulation supports reliably. Fonts, Czech diacritics and rotation don't depend on the printer.

## Run

```sh
nix-shell            # NixOS: provides uv + zlib for Pillow
uv run app.py        # open http://127.0.0.1:5000
```

## Setup

1. Set `printer.host` in `config.toml` to the G530's IP address. The printer's self-test / configuration printout shows it.
2. Make sure the printer accepts ZPL. In GoDEX's GoLabel / NetSetting tool, the command language should be set to **Auto** or **ZPL**. If the printer prints the ZPL as text, or prints nothing, this setting is the cause.
3. Click **Print ruler** in the designer. It prints a mm scale across the whole print head. Set `head_offset_mm` to the x value at the label's edge.
4. Print a label and check it:
   - If it's upside down, switch `rotate` between `90` and `270`. If your stock feeds 50 mm wide, use `rotate = 0`.
   - If the grey arrow beside the canvas doesn't point at the edge that comes out of the printer first, set `feed_flip = true`.
   - For small position corrections, use `shift_down_mm` / `shift_right_mm`. They follow the directions on the finished (portrait) label, and negative values work.

   If the printer feeds multiple labels or stops mid-label, run media calibration on the printer.

## Files

- `app.py`: the Flask server. `templates/editor.html` is the designer page.
- `label.py`: ZPL conversion, the calibration ruler and the network send.
- `config.toml`: printer, label size, calibration and margin. It is re-read on every request.
- `designs/`: designs saved from the designer, one JSON file each, with images embedded.
- `assets/logo.png`: the logo inserted by the **Logo** button. Replace it with **Upload logo…**.
- `assets/fonts/`: fonts offered in the designer. `DMSans.ttf` is DM Sans (variable weight), and `OFL.txt` is its licence, which must stay next to it.
- `static/vendor/fabric-5.3.0.min.js`: Fabric.js, the canvas library behind the designer. It's included in the repo so the app works offline.
