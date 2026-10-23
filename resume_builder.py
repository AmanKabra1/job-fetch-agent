"""
Tailored resume builder for Aman Kabra.
========================================

Generate a job-specific resume in your own format. Paste a job description and
the builder auto-emphasizes the skills that match the role (reorders them to
the front of each category, bolds them, and rewrites the summary line to lead
with your top matching stack). Output is written to ./resume/ as PDF and/or
Word (.docx).

USAGE
-----
  # Generate from a job description file (recommended):
  python resume_builder.py new --title "Backend Developer" --company "Acme" --jd jd.txt

  # Or paste/point the JD inline:
  python resume_builder.py new --title "Node.js Developer" --company "Acme" \
      --jd-text "We need a Node.js / NestJS engineer with MySQL and AWS ..."

  # No JD -> plain base resume:
  python resume_builder.py new --title "Software Engineer" --company "Acme"

  # Pick format(s): pdf | docx | both (default: both)
  python resume_builder.py new --title "..." --company "..." --jd jd.txt --format pdf

  # List everything you've generated:
  python resume_builder.py list

  # Delete a generated resume (both formats for that base name), or everything:
  python resume_builder.py delete "Aman_Kabra_Acme_Backend-Developer_2026-06-15"
  python resume_builder.py delete --all

Edit your details in resume_profile.py — both formats stay in sync.
"""

import os
import re
import sys
import argparse
import datetime as dt

import resume_profile as P

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume")


# --------------------------------------------------------------------------- #
# TAILORING
# --------------------------------------------------------------------------- #
def find_matched_skills(jd_text: str) -> set:
    """Return the set of SKILLS labels whose aliases appear in the JD text."""
    if not jd_text:
        return set()
    text = " " + jd_text.lower() + " "
    matched = set()
    for label, aliases in P.SKILL_KEYWORDS.items():
        for alias in aliases:
            # word-boundary match so "go" doesn't fire on "google", "rest" not "restaurant"
            pattern = r"(?<![a-z0-9])" + re.escape(alias.strip()) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                matched.add(label)
                break
    return matched


def tailor_skills(matched: set):
    """Reorder each skill category so matched skills come first (stable)."""
    tailored = {}
    for category, items in P.SKILLS.items():
        hits = [s for s in items if s in matched]
        rest = [s for s in items if s not in matched]
        tailored[category] = hits + rest
    return tailored


def build_summary(matched: set) -> str:
    """Rewrite the summary line to lead with the top matching stack."""
    # Preferred display order for the summary lead-in.
    # Java sits LAST on purpose: you're steering toward Node/Python/AI roles, so the
    # summary should lead with those and only mention Java when the JD asks for it.
    priority = [
        # languages / frameworks only: LLM, RAG, REST, Microservices, AWS, Docker are
        # already stated by the fixed template text and the skills section, so listing
        # them in {stack} produced "...RESTful APIs using RESTful APIs, LLM Integration".
        "NestJS", "Node.js", "TypeScript", "Express.js", "Python", "FastAPI", "Django",
        "Go (Golang)", "Angular 17 (Signals, standalone components, RxJS)",
        "Java (Spring Boot)", "Spring Boot",
    ]
    # Friendly short names for the summary sentence.
    short = {
        "Java (Spring Boot)": "Java",
        "Go (Golang)": "Go",
        "Angular 17 (Signals, standalone components, RxJS)": "Angular",
        "RAG (Retrieval-Augmented Generation)": "RAG",
        "AWS S3": "AWS",
    }
    lead = [s for s in priority if s in matched]
    if len(lead) < 3:
        # Top up with defaults so the sentence always reads well.
        for s in P.DEFAULT_STACK:
            if s not in lead:
                lead.append(s)
    lead = [short.get(s, s) for s in lead][:5]
    stack = ", ".join(lead[:-1]) + ", and " + lead[-1] if len(lead) > 1 else lead[0]
    return P.SUMMARY_TEMPLATE.format(stack=stack)


def resume_plain_text(summary, skills, ats_keywords=None, headline=None,
                      experience=None, best_project=None) -> str:
    """The resume's text exactly as an ATS parser would read it (same content the PDF /
    DOCX renderers draw). Used to ESTIMATE the ATS score from the real document rather
    than from a few fragments."""
    L = [P.NAME, " | ".join([P.LOCATION, P.PHONE, P.EMAIL, P.LINKEDIN, P.GITHUB])]
    if headline:
        L.append(headline)
    L += ["", "PROFESSIONAL SUMMARY", summary, "", "EXPERIENCE"]
    for j in (experience or P.EXPERIENCE):
        L += [f"{j['company']} {j['dates']}", f"{j['title']} {j['location']}"]
        L += [f"- {b}" for b in j["bullets"]]
    L += ["", "TECHNICAL SKILLS"]
    for cat, items in skills.items():
        L.append(f"{cat}: " + ", ".join(items))
    if ats_keywords:
        L.append("Core Competencies: " + ", ".join(ats_keywords))
    L += ["", "PROJECTS"]
    projs = []
    if best_project and best_project.get("name"):
        projs.append((best_project.get("name"), best_project.get("tech_stack") or "",
                      [best_project.get("tailored_description") or best_project.get("description", "")]
                      + list(best_project.get("tailored_bullets") or best_project.get("bullets") or [])))
    if not (best_project and best_project.get("name")) and P.PROJECTS:
        p0 = P.PROJECTS[0]
        projs.append((p0.get("name"), p0.get("stack", ""), list(p0.get("bullets", []))))
    for p in _other_projects(best_project):
        projs.append((p.get("name"), p.get("stack", ""), list(p.get("bullets", []))))
    for name, stack, bl in projs:
        stack = ", ".join(stack) if isinstance(stack, list) else stack
        L.append(f"{name} | {stack}")
        L += [f"- {b}" for b in bl if b]
    L += ["", "EDUCATION", f"{P.EDUCATION['school']} {P.EDUCATION['dates']}",
          f"{P.EDUCATION['degree']} {P.EDUCATION['location']}", "", "CERTIFICATIONS",
          " | ".join(P.CERTIFICATIONS)]
    return "\n".join(L)


MAX_HIGHLIGHT_PER_LINE = 3


def _top_matches(items, matched):
    """The JD-matched skills to highlight on one skills line: only the first few (matched
    skills are already sorted to the front), so the section stays readable."""
    return set([s for s in items if s in matched][:MAX_HIGHLIGHT_PER_LINE])


def _proj_links(proj, html=True):
    """GitHub + live-demo links of a profile project (either may be missing)."""
    out = []
    for label, key in (("GitHub", "github"), ("Live Demo", "live")):
        url = proj.get(key) or (proj.get("link") if key == "live" else "")
        if url:
            out.append((label, url))
    if html:
        return " | ".join(f'<a href="{u}">{l}</a>' for l, u in out)
    return " | ".join(f"{l}: {u.replace('https://', '').rstrip('/')}" for l, u in out)


def _other_projects(best_project=None):
    """The extra projects shown beside the lead project (3 in total; kept short so the
    resume stays one page). Lead = the JD-matched project if any, else the first profile project."""
    lead = (best_project or {}).get("name") or (P.PROJECTS[0]["name"] if P.PROJECTS else "")
    return [p for p in P.PROJECTS if p.get("name") != lead][:2]


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text or "x"


def base_filename(company: str = "", title: str = "") -> str:
    """Evergreen file name: <First>_<Last>_Resume (e.g. Aman_Kabra_Resume).

    Deliberately carries NO job title, company, date or 'ATS' word. Recruiters and
    ATS portals show the file name as-is, so a name stuck to one job or one day looks
    stale/mass-produced the moment the file is reused or forwarded. Tailoring lives
    INSIDE the document; the name stays valid for any job on any day. The
    `company`/`title` args are accepted (and ignored) so old call sites keep working."""
    return f"{slugify(P.NAME).replace('-', '_')}_Resume"


_NAME_NOISE = re.compile(
    r"(tailor(?:ed)?|ats|optimi[sz]ed|standard|version|final|latest|new|copy|"
    r"resume|cv|\d{1,4}[-_.]\d{1,2}[-_.]\d{1,4}|\d+)", re.I)


def evergreen_name_from(filename_stem: str) -> str:
    """Reduce an UPLOADED file's stem to a job/date-free person name (for the
    upload-tailor flow), falling back to the saved profile's name."""
    # Drop only WHOLE noise tokens (so "Chandrashekhar" or "Newman" survive).
    toks = [t for t in re.split(r"[\s_\-.]+", filename_stem or "") if t]
    keep = [re.sub(r"[^A-Za-z]", "", t) for t in toks
            if not re.fullmatch(_NAME_NOISE.pattern, t, re.I) and not re.fullmatch(r"v?\d+", t, re.I)]
    s = "_".join(k for k in keep if k)
    return s if len(s) >= 2 else "Resume"


# --------------------------------------------------------------------------- #
# ONE-PAGE GUARANTEE
# --------------------------------------------------------------------------- #
# Every generated resume must fit on a SINGLE page whatever the job description adds
# (headline, Core Competencies line, a long tailored project...). Instead of hoping the fixed
# font sizes fit, each renderer takes a `scale` (fonts, line spacing, gaps, margins) and the
# fit_* helpers below shrink it step by step until the page count is exactly 1.
MIN_SCALE = 0.62            # absolute floor; reached only after content has been trimmed too
READABLE_SCALE = 0.88       # shrink fonts down to here BEFORE cutting any content (8.5pt -> ~7.5pt)
DOCX_LINE_SPACING = 0.92    # Word "multiple": Calibri single spacing (~1.22em) is looser than the PDF
# Word lays text out differently from reportlab (Calibri vs Helvetica, spacing model), so the
# Word scale = PDF scale * this factor, calibrated against real Word page counts.
DOCX_SCALE_FACTOR = 0.92   # measured: Word still fits at 1.00, breaks at 1.05 -> ~12% safety margin
_STEPS = [round(1.0 - 0.02 * i, 2) for i in range(0, 20)]


def _trim_cfg(trim: int) -> dict:
    """Content trimming ladder used only when shrinking the type alone is not enough:
    0 = everything; 1 = project bullets capped at 3; 2 = + at most one extra project and
    older roles keep 3 bullets; 3 = + no extra projects, project bullets capped at 2,
    older roles keep 2 bullets."""
    return {0: {"pb": None, "others": None, "exp": None},
            1: {"pb": 3, "others": None, "exp": None},
            2: {"pb": 3, "others": 1, "exp": 3},
            3: {"pb": 2, "others": 0, "exp": 2}}[max(0, min(3, trim))]


def _cap(items, n):
    items = list(items or [])
    return items if n is None else items[:n]


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def fit_pdf(render_kwargs: dict):
    """Render the PDF on exactly ONE page: keep all content and shrink the type down to
    READABLE_SCALE first; if that is not enough, trim content one level at a time (see
    _trim_cfg), each time restarting at full size; only as a last resort go below
    READABLE_SCALE. Returns (pdf_bytes, scale, pages, trim)."""
    import io
    last = None
    for trim in range(0, 4):
        floor = READABLE_SCALE if trim < 3 else MIN_SCALE
        for sc in _STEPS:
            if sc < floor:
                break
            buf = io.BytesIO()
            render_pdf(buf, scale=sc, trim=trim, **render_kwargs)
            data = buf.getvalue()
            last = (data, sc, _pdf_pages(data), trim)
            if last[2] <= 1:
                return last
    return last


def fit_docx(render_kwargs: dict, pdf_scale: float = None, trim: int = None):
    """Render the Word file with the SAME shrink + trim the PDF needed (same content), the
    scale times DOCX_SCALE_FACTOR. Returns (docx_bytes, scale)."""
    import io
    if pdf_scale is None or trim is None:
        _d, pdf_scale, _p, trim = fit_pdf(render_kwargs)
    sc = max(MIN_SCALE * DOCX_SCALE_FACTOR, round(pdf_scale * DOCX_SCALE_FACTOR, 3))
    buf = io.BytesIO()
    render_docx(buf, scale=sc, trim=trim, **render_kwargs)
    return buf.getvalue(), sc


# --------------------------------------------------------------------------- #
# PDF RENDERER  (reportlab)
# --------------------------------------------------------------------------- #
def render_pdf(path, summary, skills, matched, target_title, target_company,
               ats_keywords=None, best_project=None, headline=None, experience=None, scale=1.0, trim=0):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
        ListFlowable, ListItem,
    )
    from reportlab.lib import colors

    DARK = colors.HexColor("#1A1A1A")
    ACCENT = colors.HexColor("#1E3A5F")

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=14 * mm * max(0.8, scale), rightMargin=14 * mm * max(0.8, scale),
        topMargin=6 * mm * max(0.7, scale), bottomMargin=6 * mm * max(0.7, scale),
        title=f"{P.NAME} - Resume", author=P.NAME,
    )
    content_w = doc.width

    # Sizes/spacing tuned so the full resume (incl. an ATS line) fits on ONE page.
    name_st = ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=18 * scale,
                             alignment=TA_CENTER, textColor=DARK, spaceAfter=1 * scale, leading=20 * scale)
    contact_st = ParagraphStyle("contact", fontName="Helvetica", fontSize=8.2 * scale,
                                alignment=TA_CENTER, textColor=DARK, leading=10 * scale)
    summary_st = ParagraphStyle("summary", fontName="Helvetica", fontSize=8.5 * scale,
                                alignment=TA_JUSTIFY, textColor=DARK, leading=10.0 * scale)
    body_st = ParagraphStyle("body", fontName="Helvetica", fontSize=8.5 * scale,
                             textColor=DARK, leading=10.0 * scale)
    bullet_st = ParagraphStyle("bullet", parent=body_st, leftIndent=10, bulletIndent=0)
    role_l = ParagraphStyle("role_l", fontName="Helvetica-Bold", fontSize=9.4 * scale, textColor=DARK)
    role_r = ParagraphStyle("role_r", fontName="Helvetica-Bold", fontSize=8.6 * scale,
                            textColor=DARK, alignment=2)
    sub_l = ParagraphStyle("sub_l", fontName="Helvetica-Oblique", fontSize=8.4 * scale, textColor=DARK)
    sub_r = ParagraphStyle("sub_r", fontName="Helvetica-Oblique", fontSize=8.4 * scale,
                           textColor=DARK, alignment=2)

    cfg = _trim_cfg(trim)
    story = []

    def section(title):
        story.append(Spacer(1, 3 * scale))
        story.append(Paragraph(title.upper(),
                     ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=9.8 * scale,
                                    textColor=ACCENT, spaceAfter=1 * scale, leading=10.5 * scale)))
        story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                                spaceBefore=1 * scale, spaceAfter=2.5 * scale))

    def two_col(left, right, lstyle, rstyle):
        t = Table([[Paragraph(left, lstyle), Paragraph(right, rstyle)]],
                  colWidths=[content_w * 0.68, content_w * 0.32])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    def bullets(items):
        # NOTE: do NOT pass value="bullet" on ListItem — reportlab then renders the
        # literal word "bullet" as the marker. The ListFlowable's start="•" supplies
        # the real bullet glyph for every item.
        return ListFlowable(
            [ListItem(Paragraph(b, bullet_st), leftIndent=12)
             for b in items],
            bulletType="bullet", bulletFontSize=6.5 * scale, start="•",
            leftIndent=12, spaceBefore=0.5 * scale, spaceAfter=0.5 * scale,
        )

    def bold_matched(skill):
        """Plain text; callers bold only the top JD matches of a line (see _top_matches)."""
        return skill

    # Header
    story.append(Paragraph(P.NAME, name_st))
    contact = " &nbsp;|&nbsp; ".join([
        P.LOCATION, P.PHONE,
        f'<a href="mailto:{P.EMAIL}">{P.EMAIL}</a>',
        f'<a href="{P.LINKEDIN}">LinkedIn</a>',
        f'<a href="{P.GITHUB}">GitHub</a>',
    ])
    story.append(Paragraph(contact, contact_st))
    if headline:
        # Role headline directly under the name: title + top stack mirrors the JD's
        # wording — the highest-weighted spot for recruiter/ATS title matching.
        story.append(Paragraph(headline, ParagraphStyle(
            "headline", fontName="Helvetica-Bold", fontSize=9.4 * scale, alignment=TA_CENTER,
            textColor=ACCENT, leading=11.5 * scale, spaceBefore=1 * scale)))
    story.append(Spacer(1, 2 * scale))

    # Professional summary
    section("Professional Summary")
    story.append(Paragraph(summary, summary_st))

    # Experience
    section("Experience")
    for i, job in enumerate(experience or P.EXPERIENCE):
        if i:
            story.append(Spacer(1, 2.5 * scale))
        story.append(two_col(job["company"], job["dates"], role_l, role_r))
        story.append(two_col(job["title"], job["location"], sub_l, sub_r))
        story.append(Spacer(1, 0.5 * scale))
        story.append(bullets(_cap(job["bullets"], cfg["exp"] if i else None)))

    # Technical skills
    section("Technical Skills")
    for category, items in skills.items():
        top = _top_matches(items, matched)
        line = f"<b>{category}:</b> " + ", ".join(f"<b>{s}</b>" if s in top else s for s in items)
        story.append(Paragraph(line, body_st))
        story.append(Spacer(1, 1 * scale))
    if ats_keywords:
        kw = ", ".join(bold_matched(k) for k in ats_keywords)
        story.append(Paragraph(f"<b>Core Competencies:</b> {kw}", body_st))
        story.append(Spacer(1, 1 * scale))

    # Projects
    section("Projects")

    # Show FIRST project: either matched (if >= 75%) or default
    if best_project and best_project.get("name"):
        # SWAP: Show matched project as FIRST (score >= 75%)
        proj = best_project
        tech = proj.get("tech_stack", [])
        tech_str = ", ".join(tech) if isinstance(tech, list) else str(tech)
        github_link = proj.get("github_url", proj.get("link", ""))
        head = (f'<b>{proj.get("name", "Project")}</b> | <i>{tech_str}</i>')
        if github_link:
            head += f' | <a href="{github_link}">GitHub</a>'
        story.append(Paragraph(head, body_st))
        story.append(Spacer(1, 1 * scale))

        # Use tailored description if available, otherwise use original
        desc = proj.get("tailored_description") or proj.get("description", "")
        if desc:
            story.append(Paragraph(desc, body_st))
            story.append(Spacer(1, 1 * scale))

        # Use tailored bullets if available, otherwise use original
        bullet_points = proj.get("tailored_bullets") or proj.get("bullets", [])
        if bullet_points:
            story.append(bullets(_cap(bullet_points, cfg["pb"])))
    else:
        # No match: show first project from profile (default)
        proj = P.PROJECTS[0] if P.PROJECTS else {}
        head = (f'<b>{proj.get("name", "Project")}</b> | <i>{proj.get("stack", "")}</i> | '
                f'{_proj_links(proj)}')
        story.append(Paragraph(head, body_st))
        story.append(Spacer(1, 1 * scale))
        if proj.get("bullets"):
            story.append(bullets(_cap(proj.get("bullets", []), cfg["pb"])))

    # Show OTHER projects from profile (2nd onwards, always visible)
    # Skip matched project to avoid duplication
    for proj in _other_projects(best_project)[:cfg["others"]]:
        story.append(Spacer(1, 2.5 * scale))
        head = (f'<b>{proj.get("name", "Project")}</b> | <i>{proj.get("stack", "")}</i> | '
                f'{_proj_links(proj)}')
        story.append(Paragraph(head, body_st))
        story.append(Spacer(1, 1 * scale))
        if proj.get("bullets"):
            story.append(bullets(_cap(proj.get("bullets", []), cfg["pb"])))

    # Education
    section("Education")
    story.append(two_col(P.EDUCATION["school"], P.EDUCATION["dates"], role_l, role_r))
    story.append(two_col(P.EDUCATION["degree"], P.EDUCATION["location"], sub_l, sub_r))

    # Certifications
    section("Certifications")
    story.append(Paragraph("  |  ".join(P.CERTIFICATIONS), body_st))

    doc.build(story)


# --------------------------------------------------------------------------- #
# WORD RENDERER  (python-docx)
# --------------------------------------------------------------------------- #
def render_docx(path, summary, skills, matched, target_title, target_company,
                ats_keywords=None, best_project=None, headline=None, experience=None, scale=1.0, trim=0):
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    DARK = RGBColor(0x1A, 0x1A, 0x1A)
    ACCENT = RGBColor(0x1E, 0x3A, 0x5F)

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.38 * max(0.7, scale))
        section.bottom_margin = Inches(0.38 * max(0.7, scale))
        section.left_margin = Inches(0.5 * max(0.8, scale))
        section.right_margin = Inches(0.5 * max(0.8, scale))
    usable_width = doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin

    # Tuned compact so the resume stays on ONE page.
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(8.8 * scale)
    normal.font.color.rgb = DARK

    def no_space(p, before=0, after=1):
        pf = p.paragraph_format
        pf.space_before = Pt(before * scale)
        pf.space_after = Pt(after * scale)
        pf.line_spacing = DOCX_LINE_SPACING
        return p

    def add_bottom_border(p):
        pPr = p._p.get_or_add_pPr()
        pbdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "1E3A5F")
        pbdr.append(bottom)
        pPr.append(pbdr)

    def section_heading(title):
        p = no_space(doc.add_paragraph(), before=4, after=2)
        run = p.add_run(title.upper())
        run.bold = True
        run.font.size = Pt(10 * scale)
        run.font.color.rgb = ACCENT
        add_bottom_border(p)

    def two_col(left, right, left_bold=True, italic=False):
        p = no_space(doc.add_paragraph())
        tab_stops = p.paragraph_format.tab_stops
        tab_stops.add_tab_stop(usable_width, WD_TAB_ALIGNMENT.RIGHT)
        lr = p.add_run(left)
        lr.bold = left_bold
        lr.italic = italic
        p.add_run("\t")
        rr = p.add_run(right)
        rr.italic = italic
        if not italic:
            rr.bold = left_bold
        return p

    def bullet(text):
        p = no_space(doc.add_paragraph(style="List Bullet"), after=0.5)
        p.paragraph_format.left_indent = Inches(0.22)
        p.add_run(text)
        return p

    # Header
    p = no_space(doc.add_paragraph(), after=1)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(P.NAME)
    r.bold = True
    r.font.size = Pt(18 * scale)
    r.font.color.rgb = DARK

    p = no_space(doc.add_paragraph(), after=2)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = p.add_run(" | ".join([P.LOCATION, P.PHONE, P.EMAIL, P.LINKEDIN, P.GITHUB]))
    c.font.size = Pt(8 * scale)

    if headline:
        p = no_space(doc.add_paragraph(), after=1)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hr = p.add_run(headline)
        hr.bold = True
        hr.font.size = Pt(9.5 * scale)
        hr.font.color.rgb = ACCENT

    cfg = _trim_cfg(trim)

    # Summary
    section_heading("Professional Summary")
    no_space(doc.add_paragraph()).add_run(summary)

    # Experience
    section_heading("Experience")
    for ji, job in enumerate(experience or P.EXPERIENCE):
        two_col(job["company"], job["dates"], left_bold=True, italic=False)
        two_col(job["title"], job["location"], left_bold=False, italic=True)
        for b in _cap(job["bullets"], cfg["exp"] if ji else None):
            bullet(b)

    # Technical skills
    section_heading("Technical Skills")
    for category, items in skills.items():
        p = no_space(doc.add_paragraph(), after=2)
        cr = p.add_run(f"{category}: ")
        cr.bold = True
        top = _top_matches(items, matched)
        for idx, s in enumerate(items):
            run = p.add_run(s + (", " if idx < len(items) - 1 else ""))
            if s in top:
                run.bold = True
    if ats_keywords:
        p = no_space(doc.add_paragraph(), after=2)
        cr = p.add_run("Core Competencies: ")
        cr.bold = True
        for idx, k in enumerate(ats_keywords):
            run = p.add_run(k + (", " if idx < len(ats_keywords) - 1 else ""))

    # Projects
    section_heading("Projects")

    # Show FIRST project: either matched (if >= 75%) or default
    if best_project and best_project.get("name"):
        # SWAP: Show matched project as FIRST (score >= 75%)
        proj = best_project
        p = no_space(doc.add_paragraph())
        nr = p.add_run(proj.get("name", "Project"))
        nr.bold = True
        tech = proj.get("tech_stack", [])
        tech_str = ", ".join(tech[:3]) if isinstance(tech, list) else str(tech)
        sr = p.add_run(f' | {tech_str}')
        sr.italic = True
        github_link = proj.get("github_url", proj.get("link", ""))
        if github_link:
            p.add_run(" | " + github_link).font.color.rgb = ACCENT

        # Use tailored description if available, otherwise use original
        desc = proj.get("tailored_description") or proj.get("description", "")
        if desc:
            bullet(desc)

        # Use tailored bullets if available, otherwise use original
        bullet_points = proj.get("tailored_bullets") or proj.get("bullets", [])
        for b in _cap(bullet_points, cfg["pb"]):
            bullet(b)
    else:
        # No match: show first project from profile (default)
        proj = P.PROJECTS[0] if P.PROJECTS else {}
        p = no_space(doc.add_paragraph())
        nr = p.add_run(proj.get("name", "Project"))
        nr.bold = True
        sr = p.add_run(f' | {proj.get("stack", "")} | ')
        sr.italic = True
        p.add_run(_proj_links(proj, html=False)).font.color.rgb = ACCENT
        for b in _cap(proj.get("bullets", []), cfg["pb"]):
            bullet(b)

    # Show OTHER projects from profile (2nd onwards, always visible)
    # Skip matched project to avoid duplication
    for proj in _other_projects(best_project)[:cfg["others"]]:
        p = no_space(doc.add_paragraph())
        nr = p.add_run(proj.get("name", "Project"))
        nr.bold = True
        sr = p.add_run(f' | {proj.get("stack", "")} | ')
        sr.italic = True
        p.add_run(_proj_links(proj, html=False)).font.color.rgb = ACCENT
        for b in _cap(proj.get("bullets", []), cfg["pb"]):
            bullet(b)


    # Education
    section_heading("Education")
    two_col(P.EDUCATION["school"], P.EDUCATION["dates"], left_bold=True, italic=False)
    two_col(P.EDUCATION["degree"], P.EDUCATION["location"], left_bold=False, italic=True)

    # Certifications
    section_heading("Certifications")
    no_space(doc.add_paragraph()).add_run("  |  ".join(P.CERTIFICATIONS))

    doc.save(path)


# --------------------------------------------------------------------------- #
# COMMANDS
# --------------------------------------------------------------------------- #
def read_jd(args) -> str:
    if args.jd_text:
        return args.jd_text
    if args.jd:
        if not os.path.exists(args.jd):
            sys.exit(f"JD file not found: {args.jd}")
        with open(args.jd, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""


def cmd_new(args):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    jd_text = read_jd(args)
    matched = find_matched_skills(jd_text)
    skills = tailor_skills(matched)
    summary = build_summary(matched)

    base = base_filename(args.company, args.title)
    fmt = args.format
    written = []

    if fmt in ("pdf", "both"):
        pdf_path = os.path.join(OUTPUT_DIR, base + ".pdf")
        pdf_data, _sc, _pg, _tr = fit_pdf(dict(summary=summary, skills=skills, matched=matched,
                                          target_title=args.title, target_company=args.company))
        with open(pdf_path, "wb") as _f:
            _f.write(pdf_data)
        written.append(pdf_path)
    if fmt in ("docx", "both"):
        docx_path = os.path.join(OUTPUT_DIR, base + ".docx")
        docx_data, _sc = fit_docx(dict(summary=summary, skills=skills, matched=matched,
                                       target_title=args.title, target_company=args.company))
        with open(docx_path, "wb") as _f:
            _f.write(docx_data)
        written.append(docx_path)

    print(f"Target role : {args.title} @ {args.company}")
    if jd_text:
        if matched:
            print(f"Emphasized  : {', '.join(sorted(matched))}")
        else:
            print("Emphasized  : (no skill keywords matched in the JD)")
    else:
        print("Emphasized  : (no JD supplied - base resume)")
    print("Created:")
    for w in written:
        print(f"  - {w}")


def cmd_list(args):
    if not os.path.isdir(OUTPUT_DIR):
        print("No resumes generated yet.")
        return
    files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith((".pdf", ".docx")))
    if not files:
        print("No resumes generated yet.")
        return
    print(f"Resumes in {OUTPUT_DIR}:")
    for f in files:
        full = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(full) / 1024
        print(f"  - {f}  ({size:.0f} KB)")


def cmd_delete(args):
    if not os.path.isdir(OUTPUT_DIR):
        print("Nothing to delete.")
        return

    if args.all:
        targets = [f for f in os.listdir(OUTPUT_DIR) if f.endswith((".pdf", ".docx"))]
    elif args.name:
        # Accept a base name (delete both formats) or an exact filename.
        name = args.name
        targets = []
        for f in os.listdir(OUTPUT_DIR):
            if f == name or os.path.splitext(f)[0] == os.path.splitext(name)[0]:
                targets.append(f)
    else:
        sys.exit("Provide a resume name to delete, or use --all.")

    if not targets:
        print(f"No matching resume found for: {args.name}")
        return

    for f in targets:
        os.remove(os.path.join(OUTPUT_DIR, f))
        print(f"Deleted: {f}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    parser = argparse.ArgumentParser(
        description="Build a tailored resume for a specific job (PDF + Word).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="generate a tailored resume")
    p_new.add_argument("--title", required=True, help="target job title")
    p_new.add_argument("--company", required=True, help="target company")
    p_new.add_argument("--jd", help="path to a job description text file")
    p_new.add_argument("--jd-text", dest="jd_text", help="job description text inline")
    p_new.add_argument("--format", choices=["pdf", "docx", "both"], default="both",
                       help="output format (default: both)")
    p_new.set_defaults(func=cmd_new)

    p_list = sub.add_parser("list", help="list generated resumes")
    p_list.set_defaults(func=cmd_list)

    p_del = sub.add_parser("delete", help="delete a generated resume (or --all)")
    p_del.add_argument("name", nargs="?", help="resume base name or filename to delete")
    p_del.add_argument("--all", action="store_true", help="delete every generated resume")
    p_del.set_defaults(func=cmd_delete)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
