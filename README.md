# Label printing (GoDEX G530, ZPL)

A local web app for product labels with two ways to make them:

- **Designer** (`/`): a drag-and-drop editor like a small Canva. You can add text, images, your logo, QR codes and shapes. Move, resize and rotate them with the mouse, set fonts, sizes and weights in the side panel, and save designs by name. **1-bit preview** shows exactly what the printer will get.
- **Simple form** (`/form`): fill in fixed fields (title, details, QR) and print.

## How it works

The designer draws the label in the browser at exactly 300 dpi (1 canvas pixel = 1 printer dot), so what you see is what prints. Images are converted to black and white right in the editor: *threshold* mode for logos, *dither* mode for photos. On Print, the browser sends the finished bitmap to the server, which turns it into ZPL with the same calibration as the simple form.

The simple form renders on the server:

The label is rendered as a 300 dpi black-and-white bitmap with Pillow: text (any UTF-8, including Czech diacritics), the QR code and the logo. The bitmap is sent as a single ZPL `^GFA` graphic field to the printer's raw port 9100.
This way the job only uses basic ZPL commands (`^XA ^PW ^LL ^LH ^FO ^GFA ^PQ ^XZ`), which GoDEX's ZPL emulation supports reliably. Fonts, diacritics and rotation don't depend on the printer.

## Run

```sh
nix-shell            # NixOS: provides uv + zlib for Pillow
uv run app.py        # open http://127.0.0.1:5000
```

## Setup

1. Set `printer.host` in `config.toml` to the G530's IP address. The printer's self-test / configuration printout shows it.
2. Make sure the printer accepts ZPL. In GoDEX's GoLabel / NetSetting tool, the command language should be set to **Auto** or **ZPL**. If the printer prints the ZPL as text, or prints nothing, this setting is the cause.
3. Print a test label and check the orientation. If the label comes out upside down, change `label.rotate` to `270`. If your stock feeds 50 mm wide, use `rotate = 0`.
4. If the print is cut off at one end or stops before the end of the label, tune `head_offset_mm`. The label runs centred under a wider print head, so start from roughly 7 mm. For smaller corrections after that, adjust `shift_down_mm` / `shift_right_mm`. They use the portrait directions you see on the finished label, and negative values work. If the printer feeds multiple labels or stops mid-label, run media calibration on the printer.

## Files

- `label.py`: rendering, ZPL conversion and network send. It can be used without the web UI:
  `label.send(label.to_zpl(label.render({...}), cfg), cfg)`
- `app.py`: the Flask server. `templates/editor.html` is the designer page, `templates/index.html` the simple form.
- `designs/`: designs saved from the designer, one JSON file each, with images embedded.
- `static/vendor/fabric-5.3.0.min.js`: Fabric.js, the canvas library behind the designer. It's included in the repo so the app works offline.
- `config.toml`: printer, label size, layout sizes and fonts. It is re-read on every request.
- `assets/logo.png`: the logo, uploaded through the form.
- `assets/fonts/DMSans.ttf`: the DM Sans font (variable weight). `OFL.txt` is its licence and must stay next to it.
