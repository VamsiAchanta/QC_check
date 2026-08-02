"""
IFU (Instructions for Use) QC Automation — core checker logic.

Implements the checklist:
  1. Page Number Verification
  2. Manufacturer Information
  3. Regulatory Symbols (label/text presence — see note below)
  4. Date Verification

LIMITATION ON SYMBOLS
----------------------
Regulatory symbols (CE mark, biohazard, "keep dry", temperature
limit icon, etc.) are graphical elements, not text. This checker
detects whether the *text label/caption* near a symbol appears in
the extracted PDF text. True shape-based symbol verification is
provided as an optional stub (check_regulatory_symbols_by_image)
that renders pages to images and does template matching — wire it
up with your own symbol reference images if you need it.
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
    # 2. Manufacturer Information
    # ------------------------------------------------------
    def check_manufacturer_info(self):
        cfg = self.config
        total_pages = len(self.pages_text)
        full_text = "\n".join(self.pages_text)

        # Where manufacturer info is required to appear.
        # "last" -> last physical page. A positive int -> that 1-indexed
        # page. None -> anywhere in the document (old behavior).
        location = cfg.get("manufacturer_info_page", "last")
        if location == "last":
            target_idx = total_pages
        elif isinstance(location, int) and 1 <= location <= total_pages:
            target_idx = location
        else:
            target_idx = None  # search whole document

        target_text = self.pages_text[target_idx - 1] if target_idx else full_text
        page_label = target_idx if target_idx else None
        location_desc = f"page {target_idx}" if target_idx else "the document"

        def normalize(t):
            return re.sub(r"\s+", " ", t).strip().lower()

        def fuzzy_present(value, text):
            if not value:
                return True
            return normalize(value) in normalize(text)

        checks = [
            ("manufacturer_name", "Manufacturer name"),
            ("manufacturer_address", "Manufacturer address"),
            ("ec_rep_address", "Authorized Representative (EC REP) address"),
            ("importer_address", "Importer/Distributor address"),
        ]

        for key, label in checks:
            value = cfg.get(key)
            if value is None:
                continue
            if fuzzy_present(value, target_text):
                continue  # found where expected — pass

            # Not found on the required page/location. Check whether it
            # exists elsewhere in the document, to give a more precise
            # failure message (missing entirely vs. misplaced).
            if target_idx and fuzzy_present(value, full_text):
                self.report.add(
                    "2. Manufacturer Information", "FAIL",
                    f"{label} was found elsewhere in the document but not "
                    f"on {location_desc} as required",
                    page=page_label
                )
            else:
                self.report.add(
                    "2. Manufacturer Information", "FAIL",
                    f"{label} does not match approved master / not found "
                    f"on {location_desc}",
                    page=page_label
                )

        # Contact info consistency is checked across the whole document,
        # since the same email/phone may legitimately appear on multiple
        # pages (cover page + back page) and consistency is what matters.
        emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", full_text))
        phones = set(re.findall(r"\+?\d[\d\s\-()]{7,}\d", full_text))
        if len(emails) > 1:
            self.report.add(
                "2. Manufacturer Information", "WARN",
                f"Multiple distinct email addresses found, verify consistency: {sorted(emails)}"
            )
        if len(phones) > 1:
            self.report.add(
                "2. Manufacturer Information", "WARN",
                f"Multiple distinct phone numbers found, verify consistency: {sorted(phones)}"
            )

    # ------------------------------------------------------
    # 3. Regulatory Symbols (text-label proxy check)
    # ------------------------------------------------------
    def check_regulatory_symbols(self):
        full_text = "\n".join(self.pages_text)
        normalized = re.sub(r"\s+", " ", full_text).lower()

        for label in self.config["required_symbol_labels"]:
            if label.lower() not in normalized:
                self.report.add(
                    "3. Regulatory Symbols", "WARN",
                    f"Label/caption for symbol '{label}' not found in "
                    "extracted text — verify the symbol graphic is present "
                    "manually or via image-based check"
                )

    def check_regulatory_symbols_by_image(self, symbol_templates=None):
        """
        OPTIONAL / STUB: True graphical symbol verification via template
        matching. Requires: pip install pdf2image opencv-python
        (and poppler installed on the system for pdf2image).

        symbol_templates: dict of {symbol_name: path_to_template_png}
        """
        try:
            from pdf2image import convert_from_path
            import cv2
            import numpy as np
        except ImportError:
            self.report.add(
                "3. Regulatory Symbols", "WARN",
                "Image-based symbol check skipped — install pdf2image and "
                "opencv-python to enable it"
            )
            return

        if not symbol_templates:
            return

        images = convert_from_path(self.pdf_path)
        for page_idx, pil_img in enumerate(images, start=1):
            page_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            for symbol_name, template_path in symbol_templates.items():
                template = cv2.imread(template_path)
                if template is None:
                    continue
                result = cv2.matchTemplate(page_cv, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val < 0.7:
                    self.report.add(
                        "3. Regulatory Symbols", "WARN",
                        f"Symbol '{symbol_name}' not confidently detected "
                        f"(match={max_val:.2f})", page=page_idx
                    )

    # ------------------------------------------------------
    # 4. Date Verification
    # ------------------------------------------------------
    def check_dates(self):
        full_text = "\n".join(self.pages_text)
        normalized = re.sub(r"\s+", " ", full_text)

        for label in self.config["required_date_labels"]:
            if label.lower() not in normalized.lower():
                self.report.add(
                    "4. Date Verification", "FAIL",
                    f"Required date field '{label}' not found in document"
                )

        date_regex = self.config["date_display_regex"]
        all_dates = re.findall(date_regex, normalized)
        if not all_dates:
            self.report.add(
                "4. Date Verification", "WARN",
                f"No dates matching expected format found (pattern: {date_regex})"
            )
        else:
            for d in all_dates:
                if not self._is_valid_date(d):
                    self.report.add(
                        "4. Date Verification", "FAIL",
                        f"Date '{d}' matches format pattern but is not a "
                        "valid calendar date"
                    )

    @staticmethod
    def _is_valid_date(date_str):
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                datetime.strptime(date_str, fmt)
                return True
            except ValueError:
                continue
        return False

    # ------------------------------------------------------
    def run_all(self):
        self.check_page_numbers()
        self.check_page_number_format_consistency()
        self.check_page_placement()
        self.check_manufacturer_info()
        self.check_regulatory_symbols()
        self.check_dates()
        return self.report
