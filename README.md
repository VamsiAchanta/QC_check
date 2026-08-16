# IFU QC Checker

Automates QC checks on IFU (Instructions for Use) PDF documents:

1. **Page Number Verification** — sequence, missing/duplicate numbers, consistent format, and **odd/even footer placement** (odd pages on the right, even pages on the left, positioned in the footer area). Supports two numbering styles: `"Page X of Y"` text, or a bare standalone number (configurable, see below). Cover/back-cover pages can be exempted from requiring a printed number.
2. **Text Encoding / Garbled Text Verification** — flags pages where a font/encoding problem (e.g. a swapped font whose character codes no longer map to the correct glyphs) has produced unreadable text: the Unicode replacement character, stray control bytes, Private-Use-Area/box-drawing glyphs (FAIL), or an unusually high count of `?` / `<` / `>` characters or repeated symbol runs like `???`/`<<<` (WARN)
3. **Manufacturer Symbol Verification** — confirms the ISO 7000-3082 "Manufacturer" factory pictogram is present on the required page (last page by default) using real image template matching, since the symbol is graphics, not text. Skips itself with a WARN if the optional image-processing dependencies aren't installed.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

**Drop-and-run (batch mode):** put one or more PDFs into `input_pdfs/`, then:

```bash
python run.py
```

Every PDF in `input_pdfs/` is checked. Reports print to the console and are saved in `output_reports/` as both:
- `<filename>.qc_report.json` — machine-readable, for scripting/CI
- `<filename>.qc_report.pdf` — formatted, presentation-ready report with color-coded FAIL/WARN tables

**Single file mode:**

```bash
python run.py path/to/any/document.pdf
```

## Configuration

Edit `config.py` — this is the only file you should need to touch to adapt the checker. It holds:

- **`page_number_mode`** — `"labeled"` for `"Page X of Y"` text, or `"bare_number"` for a standalone digit with no wording (uses word coordinates, restricted to the footer zone)
- **`unnumbered_pages`** — pages allowed to have no printed number at all (e.g. `["first", "last"]` for a cover and back-cover page)
- Expected `Page X of Y` pattern
- **Odd/even footer placement rule** — `enforce_left_right_placement` (on by default: odd pages must be right-aligned in the footer, even pages left-aligned) and `footer_zone_ratio` (how close to the bottom of the page counts as "footer")
- **`garbled_symbol_warn_threshold`** — how many `?`/`<`/`>` characters on a single page trigger a garbled-text WARN (default `5`)
- **`require_manufacturer_symbol`** — turn the manufacturer-symbol check on/off (default `True`)
- **`manufacturer_symbol_page`** — which page must carry the symbol: `"last"` (default), `"first"`, or a specific 1-indexed page int
- **`manufacturer_symbol_template`** — path to the reference symbol image; `None` (default) uses the bundled `assets/manufacturer_symbol_template.png`
- **`manufacturer_symbol_render_dpi`** / **`manufacturer_symbol_match_threshold`** — rendering resolution and minimum match confidence (0-1) for the template match (defaults `150` / `0.6`)

## Project structure

```
ifu-qc-checker/
├── config.py              # <- edit this with your approved master data
├── run.py                 # batch runner: processes input_pdfs/*.pdf
├── requirements.txt
├── src/
│   └── ifu_qc_checker.py  # core check logic (IFUQualityChecker class)
├── assets/
│   └── manufacturer_symbol_template.png  # reference image for the symbol check
├── input_pdfs/            # <- drop PDF files to check here
└── output_reports/        # JSON reports land here after each run
```

## CI usage

`run.py` exits non-zero if any processed PDF fails its checks, so it can be wired directly into a CI pipeline as a QC gate.

## Implementation details

For a deep dive into how each check actually works internally (detection algorithms, exact rules, the report data model, and how the test fixtures were built), see [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).
