"""
CONFIG — edit this file to adapt the checker's page-numbering rules
and garbled-text sensitivity to a different document layout.
"""

CONFIG = {
    # ---- 1. Page Number Verification ----
    # "labeled"     -> pages show "Page X of Y" style text
    # "bare_number" -> pages show just a standalone number (no "Page"/"of")
    "page_number_mode": "bare_number",

    # Only used when page_number_mode == "labeled"
    "page_number_pattern": r"Page\s+(\d+)\s+of\s+(\d+)",
    # Only used when page_number_mode == "bare_number": max digit length
    # a page number can be, to avoid false-matching unrelated numbers.
    "bare_number_max_digits": 4,

    # Pages allowed to have NO printed page number at all (e.g. a cover
    # page or a manufacturer/back-cover page commonly aren't numbered).
    # Accepts "first", "last", or specific 1-indexed page ints.
    "unnumbered_pages": ["first", "last"],

    # Left/right placement rule: ODD page numbers must appear in the
    # footer on the RIGHT side of the page; EVEN page numbers must
    # appear in the footer on the LEFT side.
    "enforce_left_right_placement": True,
    # Fraction of page height (from the top) below which content is
    # considered to be in the "footer" zone. 0.85 = bottom 15% of page.
    "footer_zone_ratio": 0.85,

    # ---- 2. Text Encoding / Garbled Text Verification ----
    # A page is WARNed if it contains this many (or more) '?' / '<' / '>'
    # characters — a common symptom of a font/encoding problem where
    # character codes no longer map to the intended glyphs.
    "garbled_symbol_warn_threshold": 5,
}
