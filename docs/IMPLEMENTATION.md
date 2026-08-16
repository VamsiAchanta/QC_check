# IFU QC Checker — Implementation Reference

This document explains *how* the checker works internally: the data it extracts from a PDF, the exact rules each check applies, the config keys that control them, and how the two hand-built test fixtures exercise those rules. For usage instructions, see [README.md](../README.md).

## 1. Architecture overview

```
input_pdfs/*.pdf
      │
      ▼
IFUQualityChecker._load()          (src/ifu_qc_checker.py)
  → pdfplumber.open(pdf)
  → for each page: extract_text(), extract_words(), (width, height)
      │
      ▼
pages_text[]     pages_words[]     pages_size[]
      │                │                │
      └───────┬────────┴────────┬───────┘
              ▼                 ▼
   check_page_numbers() ...   check_text_encoding()
   check_page_number_format_consistency()
   check_page_placement()
              │                 │
              └────────┬────────┘
                       ▼
                  QCReport
                (Issue list: category, severity, message, page)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  print_report()    to_json()      to_pdf()
   (console)      (output_reports)  (output_reports, reportlab)
```

`IFUQualityChecker.__init__` loads the whole PDF once into three parallel per-page lists, and every check method reads from those — nothing re-opens the PDF. `run_all()` (bottom of `src/ifu_qc_checker.py`) is the entry point and simply calls each check in sequence:

```python
def run_all(self):
    self.check_page_numbers()
    self.check_page_number_format_consistency()
    self.check_page_placement()
    self.check_text_encoding()
    return self.report
```

Every finding is a `QCReport.add(category, severity, message, page=None)` call. `severity` is `"FAIL"` (blocks pass) or `"WARN"` (informational). `QCReport.passed()` is simply `len(self.fails()) == 0`.

## 2. Check 1 — Page Number Verification

Category label in the report: `"1. Page Number Verification"`.

### 2.1 Detection (`_detect_page_numbers`)

This is the shared engine every page-number rule reads from. It supports two document styles, chosen via `config["page_number_mode"]`:

**`"labeled"`** (default) — pages carry text like `"Page 3 of 42"`. The full page text is matched against `config["page_number_pattern"]` (default `r"Page\s+(\d+)\s+of\s+(\d+)"`). Group 1 is the page number, group 2 is the declared total. The matching line is then located again in the word-coordinate data (`extract_words()`) so its on-page position (`x0`, `x1`, `top`) is known for the placement check.

**`"bare_number"`** — pages show just a standalone digit, no `"Page"/"of"` wording (common in compact IFUs). Because there's no surrounding text to anchor on, detection works purely from word coordinates:

```python
digit_re = re.compile(r"\d{1," + str(max_digits) + "}")
candidates = [
    w for w in words
    if digit_re.fullmatch(w["text"])
    and w["top"] >= page_height * footer_zone_ratio
]
best = min(candidates, key=lambda w: min(w["x0"], page_width - w["x1"]))
```

Every standalone number in the bottom `footer_zone_ratio` slice of the page (default bottom 15%, i.e. `top >= height * 0.85`) is a candidate; the one closest to a page **edge** wins, since a real page number sits near the margin, not mid-footer. `bare_number_max_digits` (default 4) bounds how many digits count, to avoid matching unrelated numbers.

Both modes populate the same shape: `{idx: {"num", "raw", "total"?, "x0", "x1", "top", "page_width", "page_height"}}`, cached on `self._page_number_info` so repeated checks don't redo the work.

### 2.2 `check_page_numbers()` — the core rules

Runs, per document, in this order:

| Rule | Logic | Severity |
|---|---|---|
| Missing number | Page not in `info` and not in the resolved `unnumbered_pages` set | FAIL |
| Declared total mismatch | (`"labeled"` mode only) `d["total"] != total_pages` | FAIL |
| Duplicate number | Same `num` detected on 2+ physical pages | FAIL |
| Missing in sequence | `expected_seq - declared_nums` is non-empty | FAIL |
| Out-of-sequence | Declared numbers, read in physical page order, aren't non-decreasing | FAIL |
| Bare-number position mismatch | (`"bare_number"` mode only) `d["num"] != idx` — the printed number must equal the page's actual physical position | FAIL |

`unnumbered_pages` (config) accepts `"first"`, `"last"`, or explicit 1-indexed ints — resolved once per run via `_resolve_unnumbered_pages()`. This is how a cover page or an unnumbered divider page is exempted from the "missing number" rule.

Example real output (from `input_pdfs/test_scenario_page_placement.pdf`, an 8-page fixture with page 6 left blank, page 7 misprinted as "5" instead of "7"):

```
❌ No page number found in the footer area (page 6)
❌ Duplicate page number '5' found on physical pages [5, 7]
❌ Missing page number(s): [6, 7]
❌ Printed page number '5' does not match its physical position in the document (page 7)
```

### 2.3 `check_page_number_format_consistency()`

Independent of the numeric rules above — this checks *formatting*, not value. Each page's raw matched text (e.g. `"Page 3 of 42"`) is turned into a template by substituting the number (and total, if present) with placeholders: `"Page {N} of {T}"`. The most common template across the document becomes the majority; any page whose template differs (different capitalization, spacing, punctuation, leading zeros, wording) is flagged — even though it still matches the loose regex.

### 2.4 `check_page_placement()`

Gated by `config["enforce_left_right_placement"]` (default `True` in this project's `config.py`, `False` if unset). For every detected page number:

1. If `top < page_height * footer_zone_ratio` → FAIL, "not positioned in the footer/below area."
2. Compute `center_x = (x0 + x1) / 2`. `is_right_half = center_x > page_width / 2`.
3. `expects_right = (declared_num % 2 == 1)` — **odd pages must be right-aligned in the footer, even pages left-aligned.**
4. Mismatch → FAIL with the specific side that was expected vs. found.

Note this uses the *declared* page number, not the physical page index — so a misprinted number (like the duplicate "5" on physical page 7 above) is judged by what's printed, not where it physically sits, which is why that fixture's page 7 didn't also fail placement: it printed "5" (odd) and was correctly right-aligned.

## 3. Check 2 — Text Encoding / Garbled Text Verification

Category label in the report: `"2. Text Encoding / Garbled Text"`.

### 3.1 Why this check exists

A PDF's visible glyphs and its underlying character codes are two separate things, connected by the font's encoding table (and optionally a `ToUnicode` CMap). When a font is swapped or embedded incorrectly, that mapping can break: the page can still *render* something, but the codes no longer resolve to the intended Unicode characters. Text-extraction tools (`pdfplumber`, built on `pdfminer.six`) then surface whatever those codes *do* resolve to — typically the Unicode replacement character (`�`), Private-Use-Area glyphs from an icon font, or literal `?` substitutions from encoders that can't represent a character at all. This check inspects `pages_text` (the same extracted text every other check uses) for exactly those symptoms.

### 3.2 The three rules (`check_text_encoding`)

```python
_GARBLED_CHAR_RE = re.compile(
    "[\uFFFD\u2500-\u25FF\uE000-\uF8FF"
    "\x00-\x08\x0B\x0C\x0E-\x1F]"
)
_REPEATED_SYMBOL_RE = re.compile(r"([?<>#$%^*~`|\\@])\1{2,}")
```

| Rule | Trigger | Severity | Rationale |
|---|---|---|---|
| Undefined character | Any char matching `_GARBLED_CHAR_RE`: `U+FFFD` (replacement char), `U+E000–U+F8FF` (Private Use Area), `U+2500–U+25FF` (box-drawing / geometric shapes), or a stray C0 control byte | **FAIL** | These are unambiguous — normal IFU prose never legitimately contains them |
| Repeated symbol run | 3+ of the same ASCII junk symbol in a row (`???`, `<<<`, `###`, …) via `_REPEATED_SYMBOL_RE` | WARN | A common *visual* signature of font-substitution garbage, but not impossible in legitimate content, so kept as a warning |
| High junk-symbol density | `text.count('?') + text.count('<') + text.count('>') >= garbled_symbol_warn_threshold` (default 5) | WARN | A single `<` or `>` is often legitimate (`"<50°C"`); many on one page usually isn't |

The FAIL rule is deliberately narrow (only characters with no legitimate use in body text) so it never fires on real content; the two WARN rules are density/pattern heuristics, so they stay advisory.

Real output from `input_pdfs/test_scenario_undefined_text.pdf`:

```
❌ Unreadable/undefined character(s) found in extracted text — likely a font/encoding
   issue (e.g. a font was swapped and its character codes no longer map to the correct
   glyphs): '\ue001', '\ue002', '\ue003', '�' (page 2)
⚠️ Repeated symbol run(s) found (3+ in a row) for character(s) <, ? — may indicate
   garbled text from a font substitution issue (page 3)
⚠️ Unusually high count of '?' / '<' / '>' characters (11) — verify this page isn't
   rendering garbled text due to a font/encoding problem (page 4)
```

## 4. Report outputs

`QCReport` (dataclass, `src/ifu_qc_checker.py`) holds a flat list of `Issue(category, severity, message, page)` and renders it three ways:

- **`print_report()`** — grouped by category, ❌/⚠️ markers, printed to console by `run.py`.
- **`to_json(path)`** — `{source_file, generated_at, result, fail_count, warn_count, issues[]}`, written to `output_reports/<name>.qc_report.json`. Machine-readable, meant for CI.
- **`to_pdf(path)`** — a formatted PDF (via `reportlab`) with a PASS/FAIL summary table and one color-coded issues table per category, written to `output_reports/<name>.qc_report.pdf`.

`run.py` exits non-zero if *any* processed PDF has `report.passed() == False`, so it can gate a CI pipeline directly.

## 5. Configuration reference (`config.py`)

| Key | Code default (if key omitted) | This project's `config.py` value | Used by |
|---|---|---|---|
| `page_number_mode` | `"labeled"` | `"bare_number"` | `_detect_page_numbers` |
| `page_number_pattern` | *(required in labeled mode)* | `r"Page\s+(\d+)\s+of\s+(\d+)"` | `_detect_page_numbers` (labeled mode only) |
| `bare_number_max_digits` | `4` | `4` | `_detect_page_numbers` (bare mode only) |
| `unnumbered_pages` | `[]` | `["first", "last"]` | `_resolve_unnumbered_pages` |
| `enforce_left_right_placement` | `False` | `True` | `check_page_placement` gate |
| `footer_zone_ratio` | `0.85` | `0.85` | bare-number detection + placement footer check |
| `garbled_symbol_warn_threshold` | `5` | `5` | `check_text_encoding` high-density rule |

## 6. Test fixtures

Both fixtures live in `input_pdfs/` and were generated by one-off scripts (not committed — `input_pdfs/*.pdf` is gitignored) to exercise real extraction behavior, not just unit-test the regex in isolation.

### `test_scenario_page_placement.pdf` (8 pages)

Built with `reportlab.pdfgen.canvas`. Planted defects, one per rule:

| Page | Defect | Rule exercised |
|---|---|---|
| 1 | Cover, no number | exempted via `unnumbered_pages: ["first", ...]` |
| 2 | "2" in footer, left | correct even/left — no finding |
| 3 | "3" in footer, right | correct odd/right — no finding |
| 4 | "4" in footer, **right** | placement FAIL (even page, wrong side) |
| 5 | "5" in footer, right | correct — no finding |
| 6 | no footer number at all | missing-number FAIL |
| 7 | "5" printed again (should be "7") | duplicate FAIL + bare-number position-mismatch FAIL + missing-"7" FAIL |
| 8 | back cover, no number | exempted via `unnumbered_pages: [..., "last"]` |

### `test_scenario_undefined_text.pdf` (4 pages)

This one required a **real** font/encoding defect, not a fabricated string, since the whole point of Check 2 is testing what `pdfplumber` actually extracts from a broken font mapping. `reportlab` can't produce that directly (it only draws valid, correctly-mapped text), so this PDF was hand-assembled at the raw PDF object level:

```
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica
   /Encoding << /Type /Encoding /BaseEncoding /WinAnsiEncoding
                 /Differences [1 /uniFFFD /uniE001 /uniE002 /uniE003] >> >>
```

Page 2's content stream draws the raw byte codes `<01020304>` using this font. Per the Adobe Glyph List naming convention, `pdfminer.six` (which `pdfplumber` sits on) resolves glyph names of the form `uniXXXX` straight back to that Unicode code point when there's no `ToUnicode` CMap — so `extract_text()` on that page genuinely returns `�`, exactly reproducing what happens when a real document's font gets swapped and its character codes desync from the intended glyphs.

| Page | Content | Rule exercised |
|---|---|---|
| 1 | Clean text incl. a legitimate `<50C` | control — confirms no false positives |
| 2 | Custom-font bytes → real `�`/PUA extraction | undefined-character FAIL |
| 3 | Literal `???` / `<<<` in plain text | repeated-symbol WARN (+ high-density WARN, expected overlap) |
| 4 | Many scattered `?`/`<`/`>` | high-density WARN only |

All pages in both fixtures carry correctly-placed footer numbers, so every finding in each report is attributable only to the check under test — the Page Number check passes cleanly on the encoding fixture, and vice versa.

## 7. Extending the checker

To add a new check:

1. Write a `check_*(self)` method on `IFUQualityChecker` that reads from `self.pages_text` / `self.pages_words` / `self.pages_size` and calls `self.report.add(category, severity, message, page=...)` for each finding.
2. Add any tunables to `CONFIG` in `config.py` with a comment explaining them, read via `self.config.get("key", default)`.
3. Call the new method from `run_all()`.
4. Document it in `README.md`'s numbered checklist and configuration section.
