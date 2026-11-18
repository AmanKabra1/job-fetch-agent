"""
Dev tool: calibrate docx_pagefit.estimate_fill against REAL Microsoft Word (Windows + Word only).

For several resume layouts it bisects the shrink factor at which Word flips from 1 page to 2 and
prints the estimator's fill just below / just above that point. A perfect estimator gives
below <= 1.0 < above; we want `below` close to 1.0 and never much under (that would let a page
spill) — so the margin we need is  max(0, 1 - min(below)).

Run:  python calibrate_pagefit.py
"""

import io
import os
import re
import sys
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_tailor as RT          # noqa: E402
import docx_pagefit as PF           # noqa: E402
from docx import Document           # noqa: E402
from docx.shared import Pt, Inches  # noqa: E402

LINES = [
    ("h", "PROFESSIONAL SUMMARY"),
    ("p", "Backend-focused Software Development Engineer with 2 years of experience building scalable microservices and RESTful APIs using NestJS, Node.js, and TypeScript. Optimized MySQL and PostgreSQL databases and integrated AWS services for 99.9% uptime."),
    ("h", "EXPERIENCE"),
    ("r", "Sanchi Connect Pvt Ltd|Aug 2024 - Present"),
    ("r", "Software Development Engineer I|Noida, Uttar Pradesh, India"),
    ("b", "Architected scalable RESTful APIs and microservices using NestJS, Node.js, Express.js, and TypeScript, enabling seamless inter-service communication across distributed systems."),
    ("b", "Engineered MySQL and PostgreSQL schema design, query optimizations, and stored procedures, improving efficiency by 30% and reducing average response latency."),
    ("b", "Integrated AWS S3 for cloud storage and AWS SES for transactional emails; implemented JWT-based authentication with RBAC for secure access control."),
    ("b", "Designed backend services using Docker, configured CI/CD pipelines (GitHub Actions, Jenkins), ensuring 99.9% uptime; resolved bottlenecks through profiling."),
    ("b", "Active in Agile/Scrum ceremonies and peer code reviews, improving team velocity by 20%."),
    ("r", "Talent Serve|Apr 2024 - Jul 2024"),
    ("b", "Developed backend modules with Express.js and Python (Flask/FastAPI), integrated third-party APIs and implemented authentication flows (JWT, OAuth 2.0)."),
    ("h", "TECHNICAL SKILLS"),
    ("p", "Languages: TypeScript, JavaScript (ES6+), Python, Java (Spring Boot), Go (Golang), SQL, HTML, CSS"),
    ("p", "Backend Frameworks: NestJS, Node.js, Express.js, Spring Boot, FastAPI, Flask, Django"),
    ("p", "Cloud & DevOps: AWS S3, Docker, AWS SES, CI/CD Pipelines, Git, GitHub Actions, Jenkins"),
    ("h", "PROJECTS"),
    ("r", "AI Job Search & Resume Agent | Python, FastAPI, LLM (Groq), Tavily, GitHub Actions, Vercel|Live Demo"),
    ("b", "Built a Python/FastAPI agent that pulls jobs from LinkedIn, Indeed, Naukri and ATS career pages, reads each full job description, and ranks roles by skills."),
    ("b", "Generates ATS-tailored PDF/Word resumes per job with ReportLab and python-docx; scheduled on GitHub Actions, deployed on Vercel."),
    ("h", "EDUCATION"),
    ("r", "Jaipur Engineering College and Research Centre (JECRC)|Aug 2020 - Jun 2024"),
    ("p", "Bachelor of Technology, Information Technology"),
]


def _mk(font, size, *, bullet="style", sa=2, sb=0, ls=None, hsize=None, table=False, margin=0.7, reps=1, plain=False):
    d = Document()
    if not plain:
        st = d.styles["Normal"]
        st.font.name = font
        st.font.size = Pt(size)
        st.paragraph_format.space_after = Pt(sa)
        st.paragraph_format.space_before = Pt(sb)
        if ls:
            st.paragraph_format.line_spacing = ls
        for s in d.sections:
            s.left_margin = s.right_margin = Inches(margin)
            s.top_margin = s.bottom_margin = Inches(margin)
    for _ in range(reps):
        for kind, text in LINES:
            if kind == "h":
                p = d.add_paragraph()
                r = p.add_run(text)
                r.bold = True
                if hsize and not plain:
                    r.font.size = Pt(hsize)
                p.paragraph_format.space_before = Pt(8)
            elif kind == "r":
                a, b = text.rsplit("|", 1)
                if table:
                    t = d.add_table(rows=1, cols=2)
                    t.rows[0].cells[0].text = a
                    t.rows[0].cells[1].text = b
                    t.rows[0].cells[0].paragraphs[0].runs[0].bold = True
                else:
                    p = d.add_paragraph()
                    p.add_run(a).bold = True
                    p.add_run("  |  " + b)
            elif kind == "b":
                if bullet == "style":
                    d.add_paragraph(text, style="List Bullet")
                else:
                    p = d.add_paragraph("• " + text)
                    p.paragraph_format.left_indent = Pt(14)
                    p.paragraph_format.first_line_indent = Pt(-10)
            else:
                d.add_paragraph(text)
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


DOCS = {
    "calibri10.5 list-style bullets": lambda: _mk("Calibri", 10.5, hsize=11.5),
    "arial10 manual bullets tight": lambda: _mk("Arial", 10, bullet="manual", sa=1, ls=1.0),
    "times11 spaced 1.15": lambda: _mk("Times New Roman", 11, sa=6, ls=1.15, hsize=12),
    "calibri10 table rows": lambda: _mk("Calibri", 10, table=True, sa=2),
    "cambria10 1.1 wide margins": lambda: _mk("Cambria", 10, sa=3, ls=1.1, margin=0.6),
    "python-docx defaults": lambda: _mk("Calibri", 11, plain=True),
    "verdana9 compact": lambda: _mk("Verdana", 9, bullet="manual", sa=1, ls=1.0, margin=0.5),
    "arial10 exact 12pt lines": lambda: _mk("Arial", 10, sa=2, ls=Pt(12)),
    "calibri11 default list spacing": lambda: _mk("Calibri", 11, sa=8, sb=0),
}


def word_pages(b):
    pdf = RT._word_pdf(b)
    return RT._pdf_page_count(pdf) if pdf else None


def flip_point(doc_bytes, lo=0.55, hi=1.7, steps=7):
    """Bisect the shrink factor where Word goes from 1 page to 2. Returns (f_one, f_two)."""
    if word_pages(RT.shrink_docx(doc_bytes, lo)) != 1:
        return None
    if word_pages(RT.shrink_docx(doc_bytes, hi)) == 1:
        return None
    for _ in range(steps):
        mid = (lo + hi) / 2
        if word_pages(RT.shrink_docx(doc_bytes, mid)) == 1:
            lo = mid
        else:
            hi = mid
    return lo, hi


def main():
    below_all, above_all = [], []
    for name, mk in DOCS.items():
        b = mk()
        with contextlib.redirect_stderr(io.StringIO()):
            fp = flip_point(b)
        if not fp:
            print(f"{name:34s} (could not bracket a flip point)", flush=True)
            continue
        f1, f2 = fp
        below = PF.estimate_fill(RT.shrink_docx(b, f1))
        above = PF.estimate_fill(RT.shrink_docx(b, f2))
        below_all.append(below)
        above_all.append(above)
        print(f"{name:34s} Word flips at f={f1:.3f}->{f2:.3f} | estimate just below={below:.3f} just above={above:.3f}", flush=True)
    if below_all:
        print(f"\nSUMMARY below: min={min(below_all):.3f} max={max(below_all):.3f}  | above: min={min(above_all):.3f} max={max(above_all):.3f}")
        print("  want: below ~1.00 (never far under)  and  above > 1.00 (never under)")


if __name__ == "__main__":
    main()
