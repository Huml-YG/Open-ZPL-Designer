# Open ZPL Designer

A small local web app for designing product labels and printing them on a **GoDEX G530** thermal printer over the network.

You lay the label out in the browser in a drag-and-drop editor, a little like Canva, and print it with one click. What you see is what prints.

![The label editor with a product label on yellow stock: tools and CSV data on the left, the label in the middle, text properties with the CSV column buttons on the right](docs/editor.png)

## Features

- **Drag-and-drop editor.** Text, images (PNG, JPG, SVG…), QR codes, barcodes (EAN-13, Code 128), rectangles, ellipses and lines. Move, resize and rotate with the mouse, or type exact positions in mm. Undo/redo, snapping, copy/paste and zoom.
- **Exact print preview.** The canvas is the label in real printer dots. **1-bit preview** shows exactly which dots will be printed.
- **Images in black and white.** *Threshold* mode suits logos, *dither* mode suits photos and gradients, with a Darkness slider. Dot gain compensation makes dithered images print as they look on screen.
- **Batch printing from CSV.** Placeholders like `MAC: $B` are filled from a CSV file, one label per row, with checks before anything is printed.
- **Portable designs.** Each design is saved as a JSON file, together with the label it was made for. It opens correctly on another PC, even with a printer at a different resolution.
- **Settings dialog.** Printer address, label size and orientation, label colour, position calibration and photo tuning, all without editing files.
- **Company font built in:** DM Sans, as a variable font with every weight. Czech diacritics work everywhere.

Out of the box it's set up for 90 × 50 mm label stock, designed in portrait (50 mm wide, 90 mm tall).

## How it works

```
browser editor  ──PNG──▶  Flask server  ──ZPL over TCP 9100──▶  GoDEX G530
(Fabric.js, 1 px = 1 dot)  (rotate, offsets, 1-bit)            (prints one bitmap)
```

1. **The browser draws the whole label.** The editor canvas is exactly the size of the label in printer dots (at 300 dpi, a 50 × 90 mm label is 591 × 1063 px). Fonts, images, QR codes and barcodes are all drawn there, so what you see is what prints.
2. **On Print, the browser sends the finished label as one PNG** to the local server (`app.py`). A batch sends one PNG per CSV row, ten per request.
3. **The server turns it into ZPL** (`label.py`). It rotates the design to the way the stock runs through the printer, applies the calibration offsets, and makes it strictly 1-bit. The whole label then becomes a single ZPL graphic field (`^GFA`).
4. **The ZPL job goes to the printer's raw port 9100.** It uses only basic commands (`^XA ^PW ^LL ^LH ^FO ^GFA ^PQ ^XZ`), which the G530's ZPL emulation handles reliably. The job is exactly as wide as the label, and the printer centres it on the label itself.

Because the printer only ever receives a finished bitmap, nothing depends on its built-in fonts, code pages or barcode support.

## Setup: from cloning to the first print

### 1. What you need

- A computer on the same network as the printer, running Linux, macOS or Windows.
- [uv](https://docs.astral.sh/uv/getting-started/installation/), the Python package manager. It installs the right Python (3.12+) and the dependencies (Flask, Pillow, qrcode, python-barcode, tomlkit) by itself.
- A current browser. It's tested in Chromium/Chrome; Firefox should work too.
- The GoDEX G530 connected by Ethernet, with labels loaded.

### 2. Get the code and start the app

```sh
git clone https://github.com/Huml-YG/Open-ZPL-Designer.git
cd Open-ZPL-Designer
uv run app.py
```

**On NixOS,** run `nix-shell` first, and then `uv run app.py` inside it. `shell.nix` provides uv plus the system libraries that Pillow needs.

Open <http://127.0.0.1:5000>. The editor should appear with an empty label. The first `uv run` downloads the dependencies, which takes a moment.

### 3. Prepare the printer

1. **Find its IP address.** It's on the printer's configuration printout or self-test page, or in GoDEX's NetSetting tool. A fixed address, or a DHCP reservation, saves trouble later.
2. **Make sure it accepts ZPL.** In GoDEX GoLabel or NetSetting, set the command language (emulation) to **Auto** or **ZPL**. If labels come out with ZPL code printed as text, or nothing prints at all, this is the cause.
3. **Run media calibration** after loading the label roll, using the printer's feed button or GoLabel. This lets the printer find the gaps between labels. Skip it and the printer may feed several labels per job or stop in the middle of one.

### 4. Set up the printer and label

Click **⚙ Settings…** (left panel). See [Settings](#settings) for every option.

1. Under **Printer**, enter the printer's address and click **Test connection**.
2. Under **Label**, enter the stock size as it runs through the printer (*width across the print head*, *length in feed direction*). Choose portrait or landscape. The summary line shows the resulting canvas size.
3. Click **Save**. The editor reloads with the new setup.

### 5. Calibrate the position

Every printer and roll sits slightly differently, so the print has to be lined up once.

1. In **Settings → Position calibration**, click **Print ruler**. It prints a millimetre scale over the label area, placed by the printer exactly like a real label but without any offsets applied.
2. Look at where the ruler's 0 marks land compared with the label edges, and enter the difference as **Shift down** and **Shift right**. Negative values move the print up or left.

   Directions are as you read the finished label. For a portrait design that isn't rotated 180°, the ruler's **x** axis runs down the label from the top, and its **y** axis runs across it from the right edge. For example, if x = 0 sits 3 mm inside the top edge, set Shift down to -3.
3. Check with a real label. Draw a thin rectangle exactly on the dashed safe-margin line, print it, and measure the gap to each edge. If the top and bottom gaps differ, shift by half the difference, and do the same for left and right.

If labels come out upside down, tick **Print rotated 180°**. The grey arrow beside the canvas shows which edge of the label leaves the printer first. If it points the wrong way (it shouldn't on a G530), tick **Feed arrow points the wrong way**.

### 6. First real print

1. Add some text, an image and a QR code. Click **1-bit preview** to see the exact dots.
2. Set **Copies** and click **Print** (or press Ctrl+P). The status line in the top bar says *Sent 1 label.*, or shows the error, for example when the printer can't be reached.
3. Type a name and click **Save** to keep the design (see [Designs](#designs)).

### 7. Optional: tune photos and gradients

Thermal dots spread a little into their neighbours (dot gain), so dithered images print much darker than the raw bitmap suggests. **Settings → Photos & gradients** compensates for this, and is already tuned for the G530 with the current stock. To retune:

1. Print a black-to-transparent gradient at 25 %, 50 % and 75 % image darkness.
2. Adjust **Print lightening** until 50 % prints well.
3. Adjust **Editor darkness** and **Slider strength** until the screen matches the prints.

**1-bit preview** always shows the real, lightened bitmap, so it looks thinner than the print. Threshold-mode images aren't affected by any of these settings.

## Using the editor

**Top bar**

| | |
|---|---|
| Name, **Save**, **Open design…**, **Import…**, **New**, **Delete** | Manage designs, see [Designs](#designs). |
| **↶ Undo**, **↷ Redo** | Up to 60 steps. |
| Status line | Results and errors. Hover for the full text. |
| **1-bit preview** | Shows exactly the printed dots, tinted with the label colour. With CSV data loaded, it shows the current row filled in. |
| **Copies** | Copies of each label. |
| **Download .zpl** | Saves the ZPL job instead of printing it. |
| **Print batch (N)** | Only with CSV data, see [Batch printing](#batch-printing-csv). |
| **Print** | Ctrl+P. With CSV data loaded it says **Print row N**. |

**Left panel**

- **Add:** Text, Image…, QR code, Barcode, Rectangle, Ellipse, Line. Images keep their original, so resizing re-converts them sharply. SVGs stay vector until they're printed.
- **Data:** CSV import for batch printing.
- **Printer:** opens **⚙ Settings…**.

**Right panel (properties of the selected element)**

- **Every element:** position and size in mm, rotation, centring, layer order, duplicate, lock and delete.
- **Text:** content, font, size in points, weight, alignment, line height, letter spacing, colour (black or white) and underline.
- **Image:** threshold or dither mode, invert, and **Darkness** (0–100 %, double-click to reset to 50 %).
- **QR code:** content, error correction and module size in dots.
- **Barcode:** content, type (EAN-13 or Code 128), module width in dots and height in mm.
- **Shape:** fill, outline, outline width and corner radius.

**Shortcuts**

- Ctrl+P prints (with CSV data loaded: the current row).
- Ctrl+Z undoes; Ctrl+Y or Ctrl+Shift+Z redoes.
- Ctrl+C and Ctrl+V copy and paste; Ctrl+D duplicates.
- Del removes the selection.
- Arrow keys nudge it 0.2 mm, Shift+arrows 2 mm.
- Ctrl+scroll zooms.
- Double-click a text to edit it on the canvas.

The dashed line is the safe margin, 3 mm by default. Keep content inside it. Drag the edges of the side panels to resize them; double-click an edge to reset it.

## Designs

- **Save** stores the design under its name as `designs/<name>.json`, with all images embedded. **Open design…** lists the saved ones. **Delete** removes the saved file; the label on screen stays.
- **Import…** loads a design file from anywhere, for example one sent by a colleague. Click **Save** to add it to your designs. A damaged file or one from another program is rejected, and the design you had stays.
- **New** starts an empty label.
- **Autosave.** The current design is also kept in the browser, so a reload or a restart of the app brings it back, even if it was never saved.

**Designs are portable.** A design file records the label it was made for (stock size, orientation, corner radius, colour) and the resolution it was drawn at. Printer-specific settings (address, calibration, margin, dot gain) stay with each PC.

- **A different label:** opening or importing a design made for a different label than this PC is set up for offers to switch the label settings to match. Cancel opens it on the current label.
- **A different printer resolution:** if the printer has a different resolution (e.g. 203 instead of 300 dpi), the design is scaled so everything keeps its size in millimetres. QR codes and barcodes are snapped to whole printer dots, so they stay scannable.

## Batch printing (CSV)

Print a series of labels where some content changes per label, such as EAN, MAC address, serial number or URL.

1. **Prepare a CSV** with one row per label, for example exported from Excel:

   ```csv
   EAN;MAC;Serial;URL
   5901234123457;AA:BB:CC:00:00:01;SN-001;https://example.com/d/1
   5901234123464;AA:BB:CC:00:00:02;SN-002;https://example.com/d/2
   ```

   Comma, semicolon and tab separators are detected automatically, quoted values work, and both UTF-8 and the windows-1250 encoding of Czech Excel are read correctly.
2. **Import it** with **Import CSV…** in the left panel's Data section.
   - By default every row is a label. If the file starts with a header row (column names), tick **First row is a header**; the names then appear on the column buttons and that row isn't printed.
   - The data stays in the browser, also across reloads, until you click **Clear data**. It's never saved into the design, so one design can be printed with any CSV.
3. **Put placeholders in the design.** `$A` is the first column, `$B` the second, and so on. They work in text boxes (`MAC: $B`), QR code content (`$D`) and barcode content (`$A`). While data is loaded, buttons for each column appear under the Content field and insert the placeholder at the cursor.
   - `${AA}` is column 27 and onwards. The braced form `${B}` also works when letters follow the placeholder directly.
   - `$$` prints a literal `$`. A `$` followed by a capital letter is always read as a placeholder.
4. **Check the rows.** **◀ ▶** steps through the rows. QR codes and barcodes in the editor follow the current row, and **1-bit preview** shows the whole label filled in, exactly as it will print. Text boxes keep showing their placeholders while you edit.
5. **Print.**
   - **Print row N** (and Ctrl+P) prints only the current row, which is handy for a reprint.
   - **Print batch** prints the rows set under *Batch: rows*, all of them by default, after a confirmation with the total count. **Copies** is the number of copies of each label.
   - **Download .zpl** saves the same rows as one ZPL file.

**Checks before printing.** Before anything is sent, every row is rendered and checked:

- **Errors stop the batch:** a placeholder for a column the CSV doesn't have, and an EAN that isn't 12 or 13 digits or has a wrong check digit.
- **Warnings can be accepted:** text with a word too long to wrap in its box, such as a long URL, and filled-in content that runs past the safe margin.

If the printer can't be reached mid-batch, the status line says which rows were sent, so you can set the range and print the rest.

**Barcodes:**
- **EAN-13** takes 12 digits (the check digit is added) or 13 (the check digit is verified).
- **Code 128** takes any ASCII text, such as a MAC address or serial number.
- **Module** is the width of the thinnest bar in printer dots. 4 dots is close to the standard EAN size; keep it at 2 or more. Whole dots keep the code scannable.
- The numbers under an EAN aren't part of the barcode element. Add a text box (e.g. `$A`) under it, so you can style it freely.

## Settings

**⚙ Settings…** edits `config.toml`. **Save** checks every value, writes the file (its comments are kept) and reloads the editor. Your design and CSV data stay. You can also edit `config.toml` by hand; it's re-read on every print.

**Printer**

| Setting | |
|---|---|
| Address, Port | The printer's IP or hostname and raw port (9100). **Test connection** checks that it can be reached. |
| Resolution | 203, 300 or 600 dpi. The G530 has 300. |
| Darkness | ZPL `^MD`, −30…30. Empty = the printer's own setting. |
| Speed | ZPL `^PR`, inches per second. Empty = the printer's own setting. |

**Label.** These are the settings a design carries with it.

| Setting | |
|---|---|
| Width across the print head, Length in feed direction | The stock size as it runs through the printer. |
| Design orientation | Portrait (short side on top) or landscape. |
| Corner radius | Rounds the canvas corners like the real labels. Screen only. |
| Safe margin | The dashed guide. Keep it larger than the area the printer can't reach. |
| Label colour | The colour of the stock, shown on the canvas and in 1-bit preview. Screen only. |
| Print rotated 180° | For labels that come out upside down. |
| Feed arrow points the wrong way | For a printer that ejects the other edge first. |

**Position calibration**

| Setting | |
|---|---|
| Shift down, Shift right | Moves the whole print as you read the finished label. **Print ruler** prints the scale to measure from (see setup step 5). |

**Photos & gradients**

| Setting | |
|---|---|
| Print lightening (`dither_gamma`) | Lightens dithered images before they're sent, to make up for dot gain. Smaller is lighter, 1 is off. |
| Editor darkness (`dither_preview_gamma`) | Makes the editor show dithered images as dark as they come out on paper. Screen only. |
| Slider strength (`dither_preview_slider`) | How strongly the image Darkness slider changes the on-screen look, to match its effect on paper. Screen only. |

## Limitations

- **Black only.** The printer has one colour. Grey and colour are reproduced by dithering, and fine detail in photos is limited by 300 dpi and dot gain. Label colour is a screen preview only.
- **Batch data comes from a CSV only,** with no database, counters or date fields. Generate serial numbers in Excel or a script and import the CSV.
- **Text doesn't shrink to fit.** A long value wraps in its text box, and a word too long to wrap overflows it. The batch check warns about it, but the font size stays as designed.
- **Barcodes: EAN-13 and Code 128 only,** with no human-readable digits built in (use a text box). Other types (EAN-8, UPC, Data Matrix…) aren't supported.
- **Top edge.** With the current calibration the printer can't reach the top ~2 mm of the label. Stay inside the safe margin.
- **One printer, one label size** at a time, both set in Settings. Tested only on the GoDEX G530 (300 dpi) with 90 × 50 mm stock. Landscape designs and the 180° option haven't been checked on paper yet.
- **Changing the label size or orientation doesn't move existing elements.** A design may need rearranging after a switch.
- **No print confirmation.** "Sent" only means the job reached the printer. The app can't detect paper-out, a jam or an open lid; the printer's own lights and display show those.
- **Every job sends the whole label as a bitmap,** about 160 kB of ZPL per label. That's quick on a local network. Multiple copies go in one job (`^PQ`), so the bitmap isn't re-sent per copy. Nothing is stored in the printer's memory.
- **Local and single-user.** The server listens on 127.0.0.1 only, with no login. Designs are plain files in `designs/`. Two people saving the same name overwrite each other, and designs with large embedded images make large files.
- **Fonts:** only fonts in `assets/fonts/` are offered. To add one, put a `.ttf` or `.otf` file there and check its licence. A design that uses a font another PC doesn't have falls back to a default font there.
- **Calibration is per printer and per roll type.** A different printer, a reinstalled roll or another stock may need the ruler and offsets again. Very different stock may need the dot gain settings retuned.

## Files

| Path | What it is |
|---|---|
| `app.py` | Flask server: editor page, design storage, settings, QR/barcode images, printing endpoints |
| `label.py` | PNG → 1-bit → ZPL conversion, rotation, QR and barcode patterns, calibration ruler, network send |
| `settings.py` | Settings dialog backend: validation and comment-preserving writes to `config.toml` |
| `templates/editor.html` | The whole editor (HTML, CSS, JavaScript) |
| `config.toml` | Printer, label (size, orientation, colour), calibration, margin and dot gain. Edited through **Settings** |
| `designs/` | Saved designs, one JSON file each, with images embedded and the label they were made for. Local only: ignored by git, so back the folder up yourself |
| `assets/fonts/` | Fonts offered in the editor. `DMSans.ttf` (variable weight) and its licence `OFL.txt`, which must stay alongside it |
| `static/vendor/` | Fabric.js 5.3.0, the canvas library, bundled so the app works offline (licence in `fabric-LICENSE.txt`) |
| `docs/` | README screenshot |
| `shell.nix` | NixOS dev shell (uv + libraries Pillow needs) |

## License

[MIT](LICENSE) © 2026 David Huml.

Bundled third-party parts keep their own licences: DM Sans under the SIL Open Font License ([`assets/fonts/OFL.txt`](assets/fonts/OFL.txt)), Fabric.js under MIT ([`static/vendor/fabric-LICENSE.txt`](static/vendor/fabric-LICENSE.txt)).
