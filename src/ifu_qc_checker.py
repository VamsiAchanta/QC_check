"""
IFU (Instructions for Use) QC Automation — core checker logic.

Implements the checklist:
  1. Page Number Verification
  2. Text Encoding / Garbled Text Verification
  3. Manufacturer Symbol Verification
"""

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

import pdfplumber

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib import colors


# ============================================================
# Garbled-text detection patterns (font/encoding failures)
# ============================================================

# Characters that are unambiguous evidence of a broken font/encoding
# mapping — they should never legitimately appear in IFU body text:
#   - U+FFFD          the Unicode "replacement character" (undecodable byte)
#   - U+E000-U+F8FF    Private Use Area (icon/symbol fonts misread as text)
#   - U+2500-U+259F    box-drawing characters
#   - U+25A0-U+25FF    geometric shapes (often glyph-substitution artifacts)
#   - C0 control chars other than tab/newline/carriage-return
_GARBLED_CHAR_RE = re.compile(
    "[\uFFFD\u2500-\u25FF\uE000-\uF8FF"
    "\x00-\x08\x0B\x0C\x0E-\x1F]"
)

# Runs of the same ASCII "junk" symbol (3+ in a row) — a common visual
# signature of font-substitution garbage (e.g. "???", "<<<", "###").
# Kept separate from _GARBLED_CHAR_RE (WARN, not FAIL) because a single
# stray "<" or ">" is often legitimate (e.g. "<50°C").
_REPEATED_SYMBOL_RE = re.compile(r"([?<>#$%^*~`|\\@])\1{2,}")


# ============================================================
# Data structures
# ============================================================

@dataclass
class Issue:
    category: str
    severity: str   # "FAIL" or "WARN"
    message: str
    page: int = None


@dataclass
class QCReport:
    source_file: str = ""
    issues: list = field(default_factory=list)

    def add(self, category, severity, message, page=None):
        self.issues.append(Issue(category, severity, message, page))

    def fails(self):
        return [i for i in self.issues if i.severity == "FAIL"]

    def warns(self):
        return [i for i in self.issues if i.severity == "WARN"]

    def passed(self):
        return len(self.fails()) == 0

    def print_report(self):
        print("\n" + "=" * 60)
        print(f"IFU QC REPORT — {self.source_file}")
        print("=" * 60)
        if not self.issues:
            print("✅ All checks passed — no issues found.")
        else:
            for cat in sorted(set(i.category for i in self.issues)):
                print(f"\n--- {cat} ---")
                for i in [x for x in self.issues if x.category == cat]:
                    mark = "❌" if i.severity == "FAIL" else "⚠️"
                    page_str = f" (page {i.page})" if i.page else ""
                    print(f"  {mark} {i.message}{page_str}")
        print("\n" + "-" * 60)
        print(f"Total: {len(self.fails())} FAIL, {len(self.warns())} WARN")
        print("RESULT:", "PASS ✅" if self.passed() else "FAIL ❌")
        print("=" * 60)

    def to_dict(self):
        return {
            "source_file": self.source_file,
            "generated_at": datetime.now().isoformat(),
            "result": "PASS" if self.passed() else "FAIL",
            "fail_count": len(self.fails()),
            "warn_count": len(self.warns()),
            "issues": [i.__dict__ for i in self.issues],
        }

    def to_json(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def to_pdf(self, path):
        """Generate a formatted, human-readable PDF version of this report."""
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name="ReportTitle", fontSize=18, leading=22,
            fontName="Helvetica-Bold", spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            name="ReportSubtitle", fontSize=10, leading=14,
            textColor=colors.grey, spaceAfter=16
        )
        section_style = ParagraphStyle(
            name="Section", fontSize=12, leading=16,
            fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=6,
            textColor=colors.HexColor("#1a1a1a")
        )
        body_style = ParagraphStyle(
            name="Body", fontSize=9.5, leading=13
        )
        pass_style = ParagraphStyle(
            name="Pass", fontSize=12, leading=16,
            fontName="Helvetica-Bold", textColor=colors.HexColor("#0a7d32")
        )

        story = []
        story.append(Paragraph("IFU QC Automation Report", title_style))
        story.append(Paragraph(
            f"Source file: {self.source_file}<br/>"
            f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}",
            subtitle_style
        ))

        # Summary box
        result_text = "PASS" if self.passed() else "FAIL"
        result_color = colors.HexColor("#0a7d32") if self.passed() else colors.HexColor("#c0392b")
        summary_table = Table(
            [["Result", "Failures", "Warnings"],
             [result_text, str(len(self.fails())), str(len(self.warns()))]],
            colWidths=[150, 150, 150]
        )
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 1), (0, 1), result_color),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)

        if not self.issues:
            story.append(Spacer(1, 20))
            story.append(Paragraph("All checks passed — no issues found.", pass_style))
        else:
            for cat in sorted(set(i.category for i in self.issues)):
                story.append(Paragraph(cat, section_style))
                cat_issues = [x for x in self.issues if x.category == cat]
                rows = [["Severity", "Page", "Issue"]]
                for i in cat_issues:
                    rows.append([
                        i.severity,
                        str(i.page) if i.page else "—",
                        Paragraph(i.message, body_style)
                    ])
                issue_table = Table(rows, colWidths=[60, 50, 340])
                table_style = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
                for row_idx, i in enumerate(cat_issues, start=1):
                    color = colors.HexColor("#c0392b") if i.severity == "FAIL" else colors.HexColor("#b8860b")
                    table_style.append(("TEXTCOLOR", (0, row_idx), (0, row_idx), color))
                    table_style.append(("FONTNAME", (0, row_idx), (0, row_idx), "Helvetica-Bold"))
                issue_table.setStyle(TableStyle(table_style))
                story.append(issue_table)

        doc = SimpleDocTemplate(
            str(path), pagesize=A4,
            topMargin=20 * mm, bottomMargin=15 * mm,
            leftMargin=18 * mm, rightMargin=18 * mm,
        )
        doc.build(story)


# ============================================================
# Core checker
# ============================================================

class IFUQualityChecker:
    def __init__(self, pdf_path, config):
        self.pdf_path = str(pdf_path)
        self.config = config
        self.report = QCReport(source_file=Path(pdf_path).name)
        self.pages_text = []
        self.pages_words = []   # list of word-dict lists (x0,x1,top,bottom,text)
        self.pages_size = []    # list of (width, height)
        self._load()

    def _load(self):
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                self.pages_text.append(page.extract_text() or "")
                self.pages_words.append(page.extract_words())
                self.pages_size.append((page.width, page.height))
        if not self.pages_text:
            raise ValueError("No pages found / PDF could not be read.")

    @staticmethod
    def _group_into_lines(words, tolerance=3):
        """Group words into visual lines based on similar 'top' position."""
        lines = []
        for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
            placed = False
            for line in lines:
                if abs(line[0]["top"] - w["top"]) <= tolerance:
                    line.append(w)
                    placed = True
                    break
            if not placed:
                lines.append([w])
        for line in lines:
            line.sort(key=lambda w: w["x0"])
        return lines

    def _resolve_unnumbered_pages(self, total_pages):
        """Turn config's unnumbered_pages list (which may contain 'first'/
        'last'/ints) into a concrete set of 1-indexed physical page numbers
        that are allowed to have no printed page number (e.g. cover, back
        cover)."""
        resolved = set()
        for p in self.config.get("unnumbered_pages", []):
            if p == "last":
                resolved.add(total_pages)
            elif p == "first":
                resolved.add(1)
            elif isinstance(p, int):
                resolved.add(p)
        return resolved

    # ------------------------------------------------------
    # 1. Page Number Verification
    # ------------------------------------------------------
    def _detect_page_numbers(self):
        """
        Unified page-number detection supporting two document styles:
          - "labeled"     -> "Page X of Y" (or similar) found via regex
                             on full page text
          - "bare_number" -> just a standalone digit in the footer zone
                             (no "Page"/"of" wording), located via word
                             coordinates

        Returns (and caches) {idx: {"num", "raw", "total"(optional),
        "x0","x1","top","page_width","page_height"}}.
        """
        if hasattr(self, "_page_number_info"):
            return self._page_number_info

        mode = self.config.get("page_number_mode", "labeled")
        info = {}

        if mode == "bare_number":
            max_digits = self.config.get("bare_number_max_digits", 4)
            footer_zone_ratio = self.config.get("footer_zone_ratio", 0.85)
            digit_re = re.compile(r"\d{1," + str(max_digits) + "}")

            for idx, words in enumerate(self.pages_words, start=1):
                page_width, page_height = self.pages_size[idx - 1]
                candidates = [
                    w for w in words
                    if digit_re.fullmatch(w["text"])
                    and w["top"] >= page_height * footer_zone_ratio
                ]
                if not candidates:
                    continue
                # Prefer the candidate closest to a page edge (left or
                # right margin) — real page numbers sit near the edge,
                # not in the middle of the footer.
                best = min(
                    candidates,
                    key=lambda w: min(w["x0"], page_width - w["x1"])
                )
                info[idx] = {
                    "num": int(best["text"]), "raw": best["text"],
                    "x0": best["x0"], "x1": best["x1"], "top": best["top"],
                    "page_width": page_width, "page_height": page_height,
                }
        else:
            pattern = self.config["page_number_pattern"]
            for idx, text in enumerate(self.pages_text, start=1):
                match = re.search(pattern, text)
                if not match:
                    continue
                num, total = int(match.group(1)), int(match.group(2))
                page_width, page_height = self.pages_size[idx - 1]
                lines = self._group_into_lines(self.pages_words[idx - 1])
                match_line = next(
                    (line for line in lines
                     if re.search(pattern, " ".join(w["text"] for w in line))),
                    None
                )
                x0 = min((w["x0"] for w in match_line), default=None) if match_line else None
                x1 = max((w["x1"] for w in match_line), default=None) if match_line else None
                top = min((w["top"] for w in match_line), default=None) if match_line else None
                info[idx] = {
                    "num": num, "total": total, "raw": match.group(0),
                    "x0": x0, "x1": x1, "top": top,
                    "page_width": page_width, "page_height": page_height,
                }

        self._page_number_info = info
        return info

    def check_page_numbers(self):
        mode = self.config.get("page_number_mode", "labeled")
        total_pages = len(self.pages_text)
        info = self._detect_page_numbers()
        unnumbered = self._resolve_unnumbered_pages(total_pages)

        # Missing: any page with no detected number, unless exempted
        for idx in range(1, total_pages + 1):
            if idx in info or idx in unnumbered:
                continue
            reason = (
                f"matching expected pattern '{self.config['page_number_pattern']}'"
                if mode == "labeled" else "in the footer area"
            )
            self.report.add(
                "1. Page Number Verification", "FAIL",
                f"No page number found {reason}", page=idx
            )

        # Declared-total check only applies to "Page X of Y" style docs
        if mode == "labeled":
            for idx, d in info.items():
                if d["total"] != total_pages:
                    self.report.add(
                        "1. Page Number Verification", "FAIL",
                        f"Declared total pages ({d['total']}) does not "
                        f"match actual document length ({total_pages})",
                        page=idx
                    )

        # Duplicates
        seen = {}
        for idx, d in info.items():
            seen.setdefault(d["num"], []).append(idx)
        for num, idxs in seen.items():
            if len(idxs) > 1:
                self.report.add(
                    "1. Page Number Verification", "FAIL",
                    f"Duplicate page number '{num}' found on physical "
                    f"pages {idxs}"
                )

        # Missing numbers within the expected sequence (excluding
        # exempted cover/back-cover style pages)
        expected_seq = [i for i in range(1, total_pages + 1) if i not in unnumbered]
        declared_nums = [d["num"] for d in info.values()]
        missing = sorted(set(expected_seq) - set(declared_nums))
        if missing:
            self.report.add(
                "1. Page Number Verification", "FAIL",
                f"Missing page number(s): {missing}"
            )

        # Sequence order
        physical_order = [info[i]["num"] for i in sorted(info)]
        if physical_order != sorted(physical_order):
            self.report.add(
                "1. Page Number Verification", "FAIL",
                "Declared page numbers are out of sequence relative to "
                f"physical page order: {physical_order}"
            )

        # Bare-number documents: printed number should equal the page's
        # actual physical position in the file.
        if mode == "bare_number":
            for idx, d in info.items():
                if d["num"] != idx:
                    self.report.add(
                        "1. Page Number Verification", "FAIL",
                        f"Printed page number '{d['num']}' does not match "
                        f"its physical position in the document (page {idx})",
                        page=idx
                    )

    def check_page_number_format_consistency(self):
        """
        Verifies every page uses the exact same page-number formatting
        (capitalization, spacing, punctuation, leading zeros) — not just
        that each one loosely matches the pattern.
        """
        info = self._detect_page_numbers()
        if len(info) < 2:
            return

        def template_of(d):
            t = d["raw"].replace(str(d["num"]), "{N}", 1)
            if "total" in d:
                t = t.replace(str(d["total"]), "{T}", 1)
            return t

        templates = {idx: template_of(d) for idx, d in info.items()}
        counts = {}
        for t in templates.values():
            counts[t] = counts.get(t, 0) + 1
        majority_template = max(counts, key=counts.get)

        for idx, t in templates.items():
            if t != majority_template:
                raw = info[idx]["raw"]
                self.report.add(
                    "1. Page Number Verification", "FAIL",
                    f"Inconsistent page number format: '{raw}' does not "
                    f"match the format used elsewhere in the document "
                    f"(expected pattern like '{majority_template}')",
                    page=idx
                )

    def check_page_placement(self):
        """
        Odd/even page number placement check:
        odd-numbered pages should show their page number in the
        FOOTER on the RIGHT side; even-numbered pages should show
        it in the FOOTER on the LEFT side.
        """
        if not self.config.get("enforce_left_right_placement", False):
            return

        footer_zone_ratio = self.config.get("footer_zone_ratio", 0.85)
        info = self._detect_page_numbers()

        for idx, d in info.items():
            if d["x0"] is None:
                self.report.add(
                    "1. Page Number Verification", "WARN",
                    "Could not determine on-page position of the page "
                    "number for placement check", page=idx
                )
                continue

            declared_num = d["num"]
            page_width, page_height = d["page_width"], d["page_height"]
            center_x = (d["x0"] + d["x1"]) / 2

            if d["top"] < page_height * footer_zone_ratio:
                self.report.add(
                    "1. Page Number Verification", "FAIL",
                    "Page number is not positioned in the footer/below "
                    "area of the page", page=idx
                )

            is_right_half = center_x > (page_width / 2)
            expects_right = (declared_num % 2 == 1)

            if expects_right and not is_right_half:
                self.report.add(
                    "1. Page Number Verification", "FAIL",
                    f"Page {declared_num} (odd) should be positioned on "
                    "the RIGHT side of the footer, but was found on the "
                    "left", page=idx
                )
            elif not expects_right and is_right_half:
                self.report.add(
                    "1. Page Number Verification", "FAIL",
                    f"Page {declared_num} (even) should be positioned on "
                    "the LEFT side of the footer, but was found on the "
                    "right", page=idx
                )

    # ------------------------------------------------------
    # 2. Text Encoding / Garbled Text Verification
    # ------------------------------------------------------
    def check_text_encoding(self):
        """
        Flags extracted text that indicates a font/encoding problem rather
        than real content — e.g. a font substitution where the PDF's
        internal character codes no longer map to the glyphs actually
        shown (common after changing/embedding fonts incorrectly), which
        pdfplumber surfaces as the Unicode replacement character, stray
        control bytes, or Private-Use-Area/box-drawing glyphs.
        """
        symbol_warn_threshold = self.config.get("garbled_symbol_warn_threshold", 5)

        for idx, text in enumerate(self.pages_text, start=1):
            if not text:
                continue

            garbled_chars = _GARBLED_CHAR_RE.findall(text)
            if garbled_chars:
                uniq = sorted(set(garbled_chars))
                self.report.add(
                    "2. Text Encoding / Garbled Text", "FAIL",
                    "Unreadable/undefined character(s) found in extracted "
                    "text — likely a font/encoding issue (e.g. a font was "
                    "swapped and its character codes no longer map to the "
                    f"correct glyphs): {', '.join(repr(c) for c in uniq)}",
                    page=idx
                )

            repeated = _REPEATED_SYMBOL_RE.findall(text)
            if repeated:
                self.report.add(
                    "2. Text Encoding / Garbled Text", "WARN",
                    "Repeated symbol run(s) found (3+ in a row) for "
                    f"character(s) {', '.join(sorted(set(repeated)))} — "
                    "may indicate garbled text from a font substitution issue",
                    page=idx
                )

            symbol_hits = sum(text.count(ch) for ch in "?<>")
            if symbol_hits >= symbol_warn_threshold:
                self.report.add(
                    "2. Text Encoding / Garbled Text", "WARN",
                    f"Unusually high count of '?' / '<' / '>' characters "
                    f"({symbol_hits}) — verify this page isn't rendering "
                    "garbled text due to a font/encoding problem",
                    page=idx
                )

    # ------------------------------------------------------
    # 3. Manufacturer Symbol Verification
    # ------------------------------------------------------
    def check_manufacturer_symbol(self):
        """
        Confirms the ISO 7000-3082 "Manufacturer" pictogram (factory
        icon) is present on the required page (last page by default).
        This is graphical shape detection via image template matching
        against a reference PNG, not a text/caption search — the symbol
        is graphics, and may be embedded as a raster image or drawn as
        vector art with no accompanying text at all.
        """
        if not self.config.get("require_manufacturer_symbol", False):
            return

        try:
            import pymupdf
            import cv2
            import numpy as np
        except ImportError:
            self.report.add(
                "3. Manufacturer Symbol", "WARN",
                "Manufacturer-symbol check skipped — install pymupdf, "
                "opencv-python and numpy (see requirements.txt) to enable "
                "image-based symbol detection"
            )
            return

        total_pages = len(self.pages_text)
        location = self.config.get("manufacturer_symbol_page", "last")
        if location == "last":
            target_idx = total_pages
        elif location == "first":
            target_idx = 1
        elif isinstance(location, int) and 1 <= location <= total_pages:
            target_idx = location
        else:
            target_idx = total_pages

        template_path = self.config.get("manufacturer_symbol_template") or (
            Path(__file__).resolve().parent.parent
            / "assets" / "manufacturer_symbol_template.png"
        )
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            self.report.add(
                "3. Manufacturer Symbol", "WARN",
                f"Manufacturer-symbol check skipped — reference template "
                f"image not found at '{template_path}'"
            )
            return

        dpi = self.config.get("manufacturer_symbol_render_dpi", 150)
        threshold = self.config.get("manufacturer_symbol_match_threshold", 0.6)

        doc = pymupdf.open(self.pdf_path)
        page = doc[target_idx - 1]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        page_gray = img[:, :, 0] if pix.n == 1 else cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY)
        doc.close()

        # The symbol's on-page size relative to the page is unknown, so
        # try the template at several plausible sizes (as a fraction of
        # page width) and keep the best match across all of them. Ratios
        # below ~0.06 are excluded: at that size the resized template is
        # only a few dozen pixels wide, and matching against mostly-blank
        # page background spuriously scores high regardless of content.
        best_score = -1.0
        page_h, page_w = page_gray.shape
        template_h, template_w = template.shape
        for width_ratio in (0.07, 0.09, 0.12, 0.16, 0.20, 0.25):
            resized_w = max(10, int(page_w * width_ratio))
            resized_h = max(10, int(template_h * (resized_w / template_w)))
            if resized_h >= page_h or resized_w >= page_w:
                continue
            resized = cv2.resize(template, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(page_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            best_score = max(best_score, max_val)

        if best_score < threshold:
            self.report.add(
                "3. Manufacturer Symbol", "FAIL",
                "Required manufacturer symbol (ISO 7000-3082 factory "
                f"pictogram) not found on page {target_idx} "
                f"(best match confidence {best_score:.2f}, need >= {threshold})",
                page=target_idx
            )

    # ------------------------------------------------------
    def run_all(self):
        self.check_page_numbers()
        self.check_page_number_format_consistency()
        self.check_page_placement()
        self.check_text_encoding()
        self.check_manufacturer_symbol()
        return self.report
