"""
CONFIG — edit this file with your organization's approved master data.
This is the ONLY file you should need to touch to adapt the checker
to a different product / manufacturer / symbol set.
"""

CONFIG = {
    # ---- 2. Manufacturer Information ----
    "manufacturer_name": "Medtronic Navigation, Inc.",
    "manufacturer_address": "200 Medtronic Drive, Lafayette, Colorado 80026, USA",
    # Not visible in the reference page provided — set this if your
    # documents include it; leave as None to skip that check.
    "ec_rep_address": "Medtronic B.V., Earl Bakkenstraat 10, 6422 PJ Heerlen, Netherlands",
    "importer_address": None,

    # Where manufacturer info is required to appear in the PDF:
    #   "last"       -> must appear on the last physical page (default)
    #   <int>        -> must appear on that specific 1-indexed page, e.g. 1
    #   None         -> search the whole document (no location requirement)
    "manufacturer_info_page": "last",

    # ---- 1. Page Number Verification ----
    # Pattern used to find "Page X of Y" style footers/headers.
    "page_number_pattern": r"Page\s+(\d+)\s+of\s+(\d+)",

    # Left/right placement rule: ODD page numbers must appear in the
    # footer on the RIGHT side of the page; EVEN page numbers must
    # appear in the footer on the LEFT side.
    "enforce_left_right_placement": True,
    # Fraction of page height (from the top) below which content is
    # considered to be in the "footer" zone. 0.85 = bottom 15% of page.
    "footer_zone_ratio": 0.85,

    # ---- 3. Regulatory Symbols ----
    # Text labels/captions expected near each required symbol.
    # (True graphical shape-matching is available as an optional
    # extension — see src/ifu_qc_checker.py:check_regulatory_symbols_by_image)
    "required_symbol_labels": [
        "Manufacturer",
        "Authorized Representative",
        "Date of manufacture",
        "Consult instructions for use",
        "Caution",
        "Temperature limit",
        "Keep dry",
        "CE",
    ],

    # ---- 4. Date Verification ----
    "required_date_labels": [
        "Manufacturing date",
        "Revision date",
        "Effective date",
        "Version date",
    ],
    # Expected display format, e.g. "01 Jan 2026"
    "date_display_regex": r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
}
