"""
Word-free page estimator for .docx files.

Why: keeping a tailored resume on exactly ONE page needs a page count, and the only exact page
counter for .docx is Microsoft Word — which exists on a Windows PC but NOT on the hosted
(Vercel/Linux) site. This module estimates how full the page is using only python-docx +
reportlab font metrics, so the hosted site can shrink a Word file just enough, too.

estimate_fill(docx_bytes) -> float   1.00 = the body exactly fills one page; 0.8 = 80% full;
                                     1.3 = spills onto a second page.

It is deliberately a little CONSERVATIVE (over-estimates by a few %, see BIAS): a slightly
over-tight resume is better than one that spills a single line onto page 2. The constants were
calibrated against real Microsoft Word output with calibrate_pagefit.py (kept next to this file's
git history / notes); re-run that if you change anything here.
"""

import io
import math
import re

from reportlab.pdfbase.pdfmetrics import stringWidth

# --------------------------------------------------------------------------- #
# Calibration constants (tuned against Microsoft Word)
# --------------------------------------------------------------------------- #
BIAS = 1.0                 # global multiplier on the final fill (safety margin)
BULLET_INDENT_PT = 18.0    # indent for list paragraphs when the file does not say
CELL_PAD_PT = 10.8         # default table cell left+right margin (0.075in each)

# font family -> (reportlab base font, width factor vs that base, natural line-height factor)
_SANS = ("Helvetica", 1.0, 1.17)
_FONTS = {
    "calibri": ("Helvetica", 0.90, 1.22),
    "arial": ("Helvetica", 1.0, 1.15),
    "helvetica": ("Helvetica", 1.0, 1.15),
    "verdana": ("Helvetica", 1.17, 1.215),
    "tahoma": ("Helvetica", 1.04, 1.207),
    "segoe ui": ("Helvetica", 1.0, 1.33),
    "trebuchet ms": ("Helvetica", 1.0, 1.16),
    "open sans": ("Helvetica", 1.04, 1.36),
    "roboto": ("Helvetica", 0.98, 1.17),
    "lato": ("Helvetica", 0.97, 1.2),
    "times new roman": ("Times-Roman", 1.0, 1.15),
    "times": ("Times-Roman", 1.0, 1.15),
    "cambria": ("Times-Roman", 1.06, 1.17),
    "georgia": ("Times-Roman", 1.12, 1.14),
    "garamond": ("Times-Roman", 0.93, 1.12),
    "book antiqua": ("Times-Roman", 1.08, 1.15),
    "palatino linotype": ("Times-Roman", 1.08, 1.15),
    "courier new": ("Courier", 1.0, 1.13),
    "consolas": ("Courier", 0.92, 1.17),
}
_SERIF_HINT = re.compile(r"serif|roman|garamond|georgia|cambria|palatino|antiqua|minion|baskerville", re.I)


def _font_info(name: str):
    n = (name or "").strip().lower()
    if n in _FONTS:
        return _FONTS[n]
    for k, v in _FONTS.items():
        if k in n:
            return v
    if _SERIF_HINT.search(n) and "sans" not in n:
        return ("Times-Roman", 1.05, 1.15)
    return _SANS


def _width(text: str, font: str, bold: bool, size: float) -> float:
    base, wf, _lh = _font_info(font)
    if bold:
        base = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[base]
    return stringWidth(text, base, size) * wf


# --------------------------------------------------------------------------- #
# Style resolution
# --------------------------------------------------------------------------- #
_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _doc_defaults(doc):
    """(font name, size pt, space_before pt, space_after pt, line multiple) from w:docDefaults."""
    el = doc.styles.element
    font, size, before, after, line = "Calibri", 11.0, 0.0, 0.0, 1.0
    try:
        rf = el.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts/@w:ascii")
        if rf:
            font = rf[0]
        sz = el.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:sz/@w:val")
        if sz:
            size = int(sz[0]) / 2.0
        sp = el.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:spacing")
        if sp:
            a = sp[0]
            g = lambda k: a.get("{%s}%s" % (_NS["w"], k))
            if g("after") is not None:
                after = int(g("after")) / 20.0
            if g("before") is not None:
                before = int(g("before")) / 20.0
            if g("line") is not None and (g("lineRule") in (None, "auto")):
                line = int(g("line")) / 240.0
    except Exception:
        pass
    return font, size, before, after, line


def _style_chain(style):
    while style is not None:
        yield style
        style = style.base_style


def _style_attr(par, attr, defaults):
    """First explicit paragraph_format value of `attr` on the paragraph or its style chain."""
    v = getattr(par.paragraph_format, attr)
    if v is not None:
        return v
    for st in _style_chain(par.style):
        v = getattr(st.paragraph_format, attr, None)
        if v is not None:
            return v
    return None


def _run_font(par, run, defaults):
    """(font name, size pt, bold) for a run."""
    name = run.font.name
    size = run.font.size.pt if run.font.size else None
    bold = run.bold
    if name is None or size is None or bold is None:
        cs = run.style if run.style is not None else None
        for st in list(_style_chain(cs)) + list(_style_chain(par.style)):
            if st is None:
                continue
            f = st.font
            if name is None and f.name:
                name = f.name
            if size is None and f.size:
                size = f.size.pt
            if bold is None and f.bold is not None:
                bold = f.bold
    return (name or defaults[0], size or defaults[1], bool(bold))


# --------------------------------------------------------------------------- #
# Paragraph / table height
# --------------------------------------------------------------------------- #
def _stack(parts):
    """Total height of consecutive paragraphs, given (before, body, after, contextual, style) each."""
    total, prev = 0.0, None
    for before, body, after, ctx, sid in parts:
        if prev is not None and ctx and prev[4] == sid:
            total -= prev[2]                  # drop the previous paragraph's space-after ...
            before = 0.0                      # ... and this one's space-before
        total += before + body + after
        prev = (before, body, after, ctx, sid)
    return total


def _para_height(par, width_pt, defaults, first_in_cell=False):
    """(before, body, after, contextual, style_id) of one paragraph laid out in `width_pt`."""
    from docx.shared import Length  # noqa: F401  (python-docx returns Length for exact spacing)

    d_font, d_size, d_before, d_after, d_line = defaults
    is_list = bool(par._p.xpath("./w:pPr/w:numPr")) or (par.style is not None and par.style.name.lower().startswith("list"))
    left = _style_attr(par, "left_indent", defaults)
    right = _style_attr(par, "right_indent", defaults)
    first = _style_attr(par, "first_line_indent", defaults)
    left_pt = left.pt if left is not None else (BULLET_INDENT_PT if is_list else 0.0)
    right_pt = right.pt if right is not None else 0.0
    first_pt = first.pt if first is not None else 0.0
    avail = max(20.0, width_pt - left_pt - right_pt)

    # words with their fonts
    items = []     # (text, font, size, bold)
    max_size = 0.0
    for run in par.runs:
        if not run.text:
            continue
        f, s, b = _run_font(par, run, defaults)
        max_size = max(max_size, s)
        for tok in re.findall(r"\S+\s*", run.text):
            items.append((tok, f, s, b))
    if not items:
        f, s = d_font, d_size
        for st in _style_chain(par.style):
            if st.font.size:
                s = st.font.size.pt
                break
        max_size = s
        font_for_lh = f
        n_lines = 1
    else:
        font_for_lh = items[0][1]
        n_lines = 1
        cur = -first_pt if first_pt < 0 else first_pt       # hanging: first line starts further left
        cur = max(0.0, first_pt)
        for tok, f, s, b in items:
            w = _width(tok.rstrip(), f, b, s)
            wsp = _width(tok, f, b, s)
            if cur + w > avail and cur > 0:
                n_lines += 1
                cur = 0.0
            cur += wsp
    # explicit line breaks inside the paragraph
    n_lines += par._p.xpath("count(.//w:br[not(@w:type) or @w:type='textWrapping'])") or 0
    n_lines = int(n_lines)

    # line height
    lh_factor = _font_info(font_for_lh)[2]
    natural = max_size * lh_factor
    ls = _style_attr(par, "line_spacing", defaults)
    rule = None
    try:
        rule = _style_attr(par, "line_spacing_rule", defaults)
    except Exception:
        pass
    if ls is None:
        line_h = natural * d_line
    elif hasattr(ls, "pt"):                       # exact / at-least in points
        rule_s = str(rule).upper() if rule is not None else ""
        line_h = max(natural, ls.pt) if "AT_LEAST" in rule_s else ls.pt
    else:
        line_h = natural * float(ls)

    before = _style_attr(par, "space_before", defaults)
    after = _style_attr(par, "space_after", defaults)
    before_pt = before.pt if before is not None else d_before
    after_pt = after.pt if after is not None else d_after
    if first_in_cell:
        before_pt = 0.0

    # inline pictures
    pic_h = 0.0
    for cy in par._p.xpath(".//wp:extent/@cy"):         # 'wp' is in python-docx's own namespace map
        try:
            pic_h = max(pic_h, int(cy) / 12700.0)
        except ValueError:
            pass
    height = max(n_lines * line_h, pic_h)
    # Word skips the space between two paragraphs of the SAME style when that style (or the
    # paragraph) sets "don't add space between paragraphs of the same style" — list styles do.
    ctx = bool(par._p.xpath("./w:pPr/w:contextualSpacing")) or any(
        st.element.xpath("./w:pPr/w:contextualSpacing") for st in _style_chain(par.style))
    sid = par.style.style_id if par.style is not None else ""
    return before_pt, height, after_pt, ctx, sid


def _table_height(table, body_w, defaults):
    from docx.text.paragraph import Paragraph
    # column widths from the grid; fall back to an even split
    grid = [int(g) / 20.0 for g in table._tbl.xpath("./w:tblGrid/w:gridCol/@w:w")]
    total = 0.0
    for row in table.rows:
        cells = row.cells
        n = max(1, len(cells))
        widths = grid if len(grid) == n and sum(grid) > 0 else [body_w / n] * n
        if sum(widths) > body_w * 1.02:
            k = body_w / sum(widths)
            widths = [w * k for w in widths]
        row_h, seen = 0.0, set()
        for c, w in zip(cells, widths):
            if id(c._tc) in seen:                  # merged cells repeat the same tc
                continue
            seen.add(id(c._tc))
            h = _stack([_para_height(p, max(20.0, w - CELL_PAD_PT), defaults, first_in_cell=(i == 0))
                        for i, p in enumerate(c.paragraphs)])
            row_h = max(row_h, h)
        total += row_h
    return total


def estimate_fill(docx_bytes: bytes) -> float:
    """How full the page is (1.0 = exactly one page). See module docstring."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(docx_bytes))
    defaults = _doc_defaults(doc)
    sec = doc.sections[0]
    page_h = sec.page_height.pt
    avail_h = page_h - sec.top_margin.pt - sec.bottom_margin.pt
    body_w = sec.page_width.pt - sec.left_margin.pt - sec.right_margin.pt
    if avail_h <= 50 or body_w <= 50:
        return 1.0

    pages_done = 0.0          # whole pages consumed by explicit page breaks
    cur = 0.0
    run = []                  # consecutive paragraphs (contextual spacing needs neighbours)

    def flush():
        nonlocal cur, run
        cur += _stack(run)
        run = []

    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            if p.paragraph_format.page_break_before:
                flush()
                pages_done += max(1.0, math.ceil(cur / avail_h))
                cur = 0.0
            run.append(_para_height(p, body_w, defaults))
            if child.xpath(".//w:br[@w:type='page']"):
                flush()
                pages_done += max(1.0, math.ceil(cur / avail_h))
                cur = 0.0
        elif tag == "tbl":
            flush()
            cur += _table_height(Table(child, doc), body_w, defaults)
    flush()
    return round((pages_done * avail_h + cur) / avail_h * BIAS, 4)
