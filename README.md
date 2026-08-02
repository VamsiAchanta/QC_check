# IFU QC Checker

Automates QC checks on IFU (Instructions for Use) PDF documents:

1. **Page Number Verification** — sequence, missing/duplicate numbers, consistent format, and **odd/even footer placement** (odd pages on the right, even pages on the left, positioned in the footer area). Supports two numbering styles: `"Page X of Y"` text, or a bare standalone number (configurable, see below). Cover/back-cover pages can be exempted from requiring a printed number.
2. **Manufacturer Information** — manufacturer name/address, EC REP address, importer/distributor address, contact info consistency
3. **Regulatory Symbols** — presence of required symbol captions (see limitation note below)
4. **Date Verification** — manufacturing/revision/effective/version dates present and in a valid, correctly formatted date

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

Edit `config.py` — this is the only file you should need to touch to adapt the checker to a different manufacturer, symbol set, or date format. It holds:

- Approved manufacturer name / address / EC REP address / importer address
- **`manufacturer_info_page`** — where that information is required to appear: `"last"` (default), a specific 1-indexed page number, or `None` to allow it anywhere. If found elsewhere but not on the required page, the report distinguishes "missing entirely" from "found but misplaced"
- **`page_number_mode`** — `"labeled"` for `"Page X of Y"` text, or `"bare_number"` for a standalone digit with no wording (uses word coordinates, restricted to the footer zone)
- **`unnumbered_pages`** — pages allowed to have no printed number at all (e.g. `["first", "last"]` for a cover and back-cover page)
- Expected `Page X of Y` pattern
- **Odd/even footer placement rule** — `enforce_left_right_placement` (on by default: odd pages must be right-aligned in the footer, even pages left-aligned) and `footer_zone_ratio` (how close to the bottom of the page counts as "footer")
- Required regulatory symbol labels
- Required date field labels and expected date format

## Project structure

```
ifu-qc-checker/
├── config.py              # <- edit this with your approved master data
├── run.py                 # batch runner: processes input_pdfs/*.pdf
├── requirements.txt
├── src/
│   └── ifu_qc_checker.py  # core check logic (IFUQualityChecker class)
├── input_pdfs/            # <- drop PDF files to check here
└── output_reports/        # JSON reports land here after each run
```

## Limitation: regulatory symbols

Symbols (CE mark, biohazard, temperature-limit icon, etc.) are graphics, not text. The default check only verifies that the *text caption* near a symbol is present in the extracted PDF text. For true shape-based symbol detection, `IFUQualityChecker.check_regulatory_symbols_by_image()` is provided as a stub that renders each page to an image and does template matching against reference symbol images — install the optional dependencies in `requirements.txt` and supply your own template PNGs to enable it.

## CI usage

`run.py` exits non-zero if any processed PDF fails its checks, so it can be wired directly into a CI pipeline as a QC gate.
