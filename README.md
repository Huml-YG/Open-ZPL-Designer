# Label printing (GoDEX G530, ZPL)

A local web form for product labels: fill in the fields, see an exact print preview, and click **Print**.

## How it works

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
- `app.py`: the Flask web form. `templates/index.html` is its page.
- `config.toml`: printer, label size, layout sizes and fonts. It is re-read on every request.
- `assets/logo.png`: the logo, uploaded through the form.
