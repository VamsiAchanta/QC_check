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

    # ---- 3. Manufacturer Symbol Verification ----
    # Requires the pip extras `pymupdf`, `opencv-python`, `numpy`
    # (see requirements.txt); the check WARNs and skips itself if they
    # aren't installed rather than failing the run.
    "require_manufacturer_symbol": True,
    # Which page must carry the symbol: "last" (default), "first", or a
    # specific 1-indexed page int.
    "manufacturer_symbol_page": "last",
    # Path to the reference symbol image used for template matching.
    # None -> use the bundled assets/manufacturer_symbol_template.png
    # (the standard ISO 7000-3082 "Manufacturer" factory pictogram).
    "manufacturer_symbol_template": None,
    # Resolution (DPI) the target page is rendered at before matching.
    "manufacturer_symbol_render_dpi": 150,
    # Minimum normalized cross-correlation score (0-1) to count as a
    # match. The template is tried at several sizes since the symbol's
    # on-page size relative to the page isn't known in advance.
    "manufacturer_symbol_match_threshold": 0.6,

    # ---- 4. CE Marking Verification ----
    # Requires the same pip extras as the manufacturer symbol check.
    "require_ce_marking": True,
    "ce_marking_page": "last",
    # List of reference images — the page passes if it matches ANY one
    # of them (either variant is acceptable). None -> use the bundled
    # assets/ce_mark_template.png (bare "CE") and
    # assets/ce_mark_0344_template.png ("CE" + notified body no. 0344).
    "ce_marking_templates": None,
    "ce_marking_render_dpi": 150,
    "ce_marking_match_threshold": 0.6,

    # ---- 5. Prescription (Rx Only) Notice Verification ----
    "require_rx_only_text": True,
    # Which page must carry the notice: "last" (default), "first", or a
    # specific 1-indexed page int.
    "rx_only_page": "last",
    # Exact notice text expected (case-insensitive substring match).
    "rx_only_text": "Rx Only",
}
