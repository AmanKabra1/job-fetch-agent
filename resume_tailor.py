"""
Tailor an UPLOADED resume to a job description — without changing its style.
=============================================================================

The user uploads their OWN resume (.docx or .pdf) plus an optional job
description and/or an optional list of skills, and we tailor that exact
document — there is no built-in profile or template; every output is the user's
own resume:

  * For a .docx upload we edit the file IN PLACE — every font, margin, color and
    layout decision the user made is preserved. We only:
      - bold the skills the resume already has that the job is asking for, and
      - insert one "Key Skills for this Role" line near the top.
    Nothing in the resume is rewritten or fabricated.

  * For a .pdf upload there is no reliable way to edit a PDF in place, so we
    extract the text and rebuild a STRUCTURED, single-page document — detecting
    the name, contact line, section headings and bullets so the result keeps the
    resume's structure (not a flat text dump) and stays on one page.

Both paths can emit Word (.docx) and PDF. PDF is produced from the tailored
.docx via Microsoft Word (docx2pdf) so the PDF matches the Word styling exactly;
if Word isn't available we fall back to a reportlab-rendered PDF.

Honesty rule: skills the JD asks for but the resume does NOT contain are returned
as *suggestions* for the user to review — they are never silently added to the
document.
"""

import io
import os
import re
import copy
import tempfile

# --------------------------------------------------------------------------- #
# SKILL LEXICON
#   canonical label -> aliases that, if found in text (word-boundary, case-
#   insensitive), mean the skill is present. Kept broad so this works for ANY
#   uploaded resume / JD, not just one profile.
# --------------------------------------------------------------------------- #
SKILL_LEXICON = {
    # Languages
    "Python": ["python"],
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "Kotlin": ["kotlin"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", ".net", "dotnet"],
    "C": [" c "],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "Swift": ["swift"],
    "Scala": ["scala"],
    "SQL": ["sql"],
    "HTML": ["html"],
    "CSS": ["css"],
    "Bash/Shell": ["bash", "shell scripting", "shell script"],
    # Backend frameworks
    "NestJS": ["nestjs", "nest.js"],
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Express.js": ["express.js", "express", "expressjs"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Ruby on Rails": ["rails", "ruby on rails"],
    "Laravel": ["laravel"],
    ".NET Core": [".net core", "asp.net"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    # Frontend
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Angular": ["angular", "rxjs"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
    "Redux": ["redux"],
    "Tailwind CSS": ["tailwind"],
    "SASS": ["sass", "scss"],
    # Databases
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],
    "Oracle DB": ["oracle"],
    "SQLite": ["sqlite"],
    # Cloud & DevOps
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda", "ses"],
    "Google Cloud": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Docker": ["docker", "container", "containeri"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "GitHub Actions": ["github actions"],
    "Jenkins": ["jenkins"],
    "GitLab CI": ["gitlab ci", "gitlab-ci"],
    "Git": ["git"],
    "Linux": ["linux", "unix"],
    "Nginx": ["nginx"],
    # Messaging / streaming
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq", "rabbit mq"],
    "Celery": ["celery"],
    # Architecture & concepts
    "Microservices": ["microservice", "micro service", "distributed system"],
    "RESTful APIs": ["rest api", "restful", "rest "],
    "JWT": ["jwt"],
    "OAuth 2.0": ["oauth"],
    "WebSockets": ["websocket"],
    "MVC": ["mvc"],
    "Agile/Scrum": ["agile", "scrum", "kanban"],
    "TDD": ["tdd", "test driven", "test-driven"],
    "Swagger/OpenAPI": ["swagger", "openapi"],
    # Data / AI
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "Machine Learning": ["machine learning", "deep learning"],
    "LLM Integration": ["llm", "large language model", "gpt", "openai", "claude", "gemini"],
    "RAG": ["rag", "retrieval-augmented", "retrieval augmented", "vector database"],
    "LangChain": ["langchain", "lang chain"],
    "LangGraph": ["langgraph", "lang graph"],
    "AI Agents": ["agentic ai", "agentic", "ai agent", "ai agents",
                 "autonomous agent", "multi-agent", "multi agent"],
    "ETL": ["etl", "data pipeline"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    # Testing
    "Jest": ["jest"],
    "Pytest": ["pytest"],
    "JUnit": ["junit"],
    "Selenium": ["selenium"],
    "Cypress": ["cypress"],
    # Tools
    "Postman": ["postman"],
    "Jira": ["jira"],
    "n8n": ["n8n"],
}


# --------------------------------------------------------------------------- #
# TEXT MATCHING
# --------------------------------------------------------------------------- #
def _word_in(alias: str, text_lower: str) -> bool:
    """Word-boundary, case-insensitive containment (text_lower is already lower)."""
    a = alias.strip().lower()
    if not a:
        return False
    pattern = r"(?<![a-z0-9+#.])" + re.escape(a) + r"(?![a-z0-9+#])"
    return re.search(pattern, text_lower) is not None


def _clean_label(label: str) -> str:
    """Drop any parenthetical detail for the short display name."""
    return re.sub(r"\s*\(.*?\)\s*", "", label).strip()


# --------------------------------------------------------------------------- #
# UPLOAD -> TEXT
# --------------------------------------------------------------------------- #
def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded .docx or .pdf. Raises ValueError."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(t for t in parts if t and t.strip())
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages)
    if ext == ".doc":
        raise ValueError("Old .doc files aren't supported — please save as .docx or PDF.")
    raise ValueError("Unsupported file type. Upload a .docx or .pdf resume.")


# --------------------------------------------------------------------------- #
# PROFILE LINKS — a clickable word like "LinkedIn" / "GitHub" hides its address from any parser
# that only reads text (many ATS do), so the recruiter's profile record loses the URL. The real
# address lives in the link data, so we print it as visible text in the contact area.
# --------------------------------------------------------------------------- #
_PROFILE_HOSTS = (("linkedin.com", "LinkedIn", r"/in/"), ("github.com", "GitHub", None))


def _short_url(u: str) -> str:
    return re.sub(r"^https?://(?:www\.)?|/+$", "", str(u or "").strip())


def _is_profile_url(uri: str, host: str, must: str) -> bool:
    u = uri.lower()
    if host not in u:
        return False
    if must:                                       # LinkedIn profile = /in/<name>
        return re.search(must, u) is not None
    # GitHub profile = github.com/<user> (a repo link has a 2nd path segment)
    return re.match(r"^https?://(?:www\.)?github\.com/[^/?#]+/?$", u) is not None


def _pdf_link_uris(data: bytes) -> list:
    out = []
    try:
        from pypdf import PdfReader
        for page in PdfReader(io.BytesIO(data)).pages:
            for a in (page.get("/Annots") or []):
                try:
                    action = a.get_object().get("/A")
                    uri = action.get_object().get("/URI") if action else None
                    if uri:
                        out.append(str(uri))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def restore_link_text(resume_text: str, uris: list) -> str:
    """In the first lines (contact area), replace a bare 'LinkedIn' / 'GitHub' label with the
    real short address from the PDF's link data. No-op if the address is already visible."""
    lines = (resume_text or "").split("\n")
    head_n = min(len(lines), 8)
    head = "\n".join(lines[:head_n])
    for host, label, must in _PROFILE_HOSTS:
        if re.search(re.escape(host), head, re.I):
            continue
        uri = next((u for u in uris if _is_profile_url(u, host, must)), None)
        if not uri:
            continue
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])", re.I)
        for i in range(head_n):
            if pat.search(lines[i]):
                lines[i] = pat.sub(_short_url(uri), lines[i], count=1)
                break
    return "\n".join(lines)


def _restore_docx_link_text(doc):
    """Same idea inside a .docx: a hyperlink whose visible text is only 'LinkedIn' / 'GitHub'
    gets its address as text (top of the document only; formatting of the run is kept)."""
    try:
        from docx.oxml.ns import qn
        for p in doc.paragraphs[:8]:
            for h in p._p.xpath(".//w:hyperlink"):
                rid = h.get(qn("r:id"))
                if not rid or rid not in doc.part.rels:
                    continue
                target = doc.part.rels[rid].target_ref
                ts = h.xpath(".//w:t")
                shown = "".join(t.text or "" for t in ts).strip()
                if not ts or "/" in shown or "." in shown:
                    continue                           # already shows an address
                for host, label, must in _PROFILE_HOSTS:
                    if _is_profile_url(target, host, must) and shown.lower() == label.lower():
                        ts[0].text = _short_url(target)
                        for extra in ts[1:]:
                            extra.text = ""
                        break
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# ANALYSIS
# --------------------------------------------------------------------------- #
def analyze(resume_text: str, jd_text: str = "", extra_skills: str = "") -> dict:
    """Decide what to emphasize.

    Returns:
      present     [labels]      skills the JD/skills-box want AND the resume has
      typed       [labels]      skills the user typed that the resume LACKS
                                (user-asserted -> we add them to the key-skills line)
      suggestions [labels]      skills the JD wants but the resume LACKS
                                (NOT added — shown to the user to consider)
      bold_terms  [alias str]   actual tokens to bold inside the resume
      had_request bool          whether any JD/skills input was given at all
    """
    resume_l = " " + (resume_text or "").lower() + " "
    jd_l = " " + (jd_text or "").lower() + " "
    skills_l = " " + (extra_skills or "").lower() + " "
    had_request = bool((jd_text or "").strip() or (extra_skills or "").strip())

    present, suggestions, typed = [], [], []
    bold_terms = set()

    for label, aliases in SKILL_LEXICON.items():
        in_jd = any(_word_in(a, jd_l) for a in aliases)
        in_skills = any(_word_in(a, skills_l) for a in aliases)
        if not (in_jd or in_skills):
            continue
        resume_hits = [a for a in aliases if _word_in(a, resume_l)]
        clean = _clean_label(label)
        if resume_hits:
            present.append(clean)
            bold_terms.update(resume_hits)
        elif in_skills:
            # The user explicitly typed this skill -> trust them, add it.
            typed.append(clean)
        else:
            # JD wants it but it's not in the resume and user didn't claim it.
            suggestions.append(clean)

    return {
        "present": present,
        "typed": typed,
        "suggestions": suggestions,
        "expanded": _spelled_out_forms(resume_text or "", jd_text or ""),
        "bold_terms": sorted(bold_terms, key=len, reverse=True),
        "had_request": had_request,
    }


# Acronym <-> spelled-out pairs. A classic ATS filter matches the EXACT string a recruiter typed,
# so when the resume says "AWS" and the JD says "Amazon Web Services" (or the reverse) the missing
# form is worth adding. HONEST by construction: only for a skill the resume ALREADY shows in one
# form — it is the same skill, spelled the other way.
_SPELL_PAIRS = [
    ("Amazon Web Services (AWS)", r"\baws\b", r"amazon web services"),
    ("Google Cloud Platform (GCP)", r"\bgcp\b", r"google cloud platform"),
    ("Continuous Integration / Continuous Delivery (CI/CD)", r"\bci\s*/\s*cd\b|\bcicd\b",
     r"continuous (?:integration|delivery|deployment)"),
    ("Large Language Models (LLM)", r"\bllms?\b", r"large language models?"),
    ("Retrieval-Augmented Generation (RAG)", r"\brag\b", r"retrieval[- ]augmented generation"),
    ("Machine Learning (ML)", r"\bml\b", r"machine learning"),
    ("Structured Query Language (SQL)", r"\bsql\b", r"structured query language"),
    ("Object-Oriented Programming (OOP)", r"\boop\b", r"object[- ]oriented"),
    ("Representational State Transfer (REST)", r"\brest\b", r"representational state transfer"),
    ("JSON Web Token (JWT)", r"\bjwt\b", r"json web tokens?"),
    ("Role-Based Access Control (RBAC)", r"\brbac\b", r"role[- ]based access control"),
]


def _spelled_out_forms(resume_text: str, jd_text: str) -> list:
    out = []
    for display, short_rx, long_rx in _SPELL_PAIRS:
        r_short = re.search(short_rx, resume_text, re.I)
        r_long = re.search(long_rx, resume_text, re.I)
        j_short = re.search(short_rx, jd_text, re.I)
        j_long = re.search(long_rx, jd_text, re.I)
        if (r_short and j_long and not r_long) or (r_long and j_short and not r_short):
            out.append(display)
    return out


def _key_skills_line(analysis: dict, ats: bool = False) -> str:
    """The skills line we insert.

    Normal: skills you already have + skills you typed.
    ATS mode: ALSO the spelled-out / acronym form of skills your resume already shows, when the
    JD uses the other form ("Amazon Web Services (AWS)"). It NEVER adds JD keywords your resume
    lacks ('suggestions') — padding a resume with skills you cannot show is flagged by 2026 AI
    screeners and falls apart in the interview; those are only reported to you."""
    skills = list(analysis["present"])
    for t in analysis["typed"]:
        if t not in skills:
            skills.append(t)
    if ats:
        for s in analysis.get("expanded", []):
            if s not in skills:
                skills.append(s)
    return ", ".join(skills)


# --------------------------------------------------------------------------- #
# DOCX TAILORING (in place — preserves style)
# --------------------------------------------------------------------------- #
def _bold_terms_regex(bold_terms):
    if not bold_terms:
        return None
    alts = "|".join(re.escape(t) for t in bold_terms)
    return re.compile(r"(?<![A-Za-z0-9+#.])(" + alts + r")(?![A-Za-z0-9+#])", re.IGNORECASE)


def _bold_in_run(run, regex):
    """Split a run so matched substrings become bold, preserving the run's other
    formatting (font, size, color, italic) by deep-copying its properties."""
    text = run.text
    if not text:
        return
    matches = list(regex.finditer(text))
    if not matches:
        return

    segments, pos = [], 0
    for m in matches:
        if m.start() > pos:
            segments.append((text[pos:m.start()], False))
        segments.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], False))

    from docx.text.run import Run
    # Capture the run's ORIGINAL bold BEFORE we mutate it — otherwise a run that
    # starts with a matched term turns its bold on, and every later (unmatched)
    # segment then inherits that bold (making the whole run bold).
    orig_bold = run.bold
    first_text, first_bold = segments[0]
    run.text = first_text
    run.bold = True if first_bold else orig_bold
    anchor = run._r
    for seg_text, seg_bold in segments[1:]:
        new_r = copy.deepcopy(run._r)          # carries this run's rPr (its style)
        new_run = Run(new_r, run._parent)
        new_run.text = seg_text                # replaces the copied w:t content
        new_run.bold = True if seg_bold else orig_bold
        anchor.addnext(new_r)
        anchor = new_r


def _insert_key_skills(doc, line: str, label: str = "Key Skills for this Role: ",
                       bold_terms=None):
    """Insert a skills paragraph just below the header. When bold_terms is given,
    the matched skills inside the line are bolded (and the JD-added ones left
    regular) — so the line reads as 'have these (bold) + add these (regular)'."""
    if not line:
        return
    from docx.shared import Pt
    paras = doc.paragraphs
    body = line
    if len(paras) >= 2:
        new_p = paras[1].insert_paragraph_before("")
    elif paras:
        new_p = paras[0].insert_paragraph_before("")
    else:
        new_p = doc.add_paragraph()
    r1 = new_p.add_run(label)
    r1.bold = True
    body_run = new_p.add_run(body)
    # Bold the matched skills inside the body run (label run is left as-is).
    if bold_terms:
        regex = _bold_terms_regex(bold_terms)
        if regex is not None:
            _bold_in_run(body_run, regex)
    # Keep it compact; inherit document Normal style otherwise.
    try:
        new_p.paragraph_format.space_before = Pt(2)
        new_p.paragraph_format.space_after = Pt(4)
    except Exception:
        pass


def tailor_docx(data: bytes, analysis: dict, ats: bool = False) -> bytes:
    """Edit an uploaded .docx in place and return the tailored bytes."""
    from docx import Document
    doc = Document(io.BytesIO(data))
    _restore_docx_link_text(doc)

    regex = _bold_terms_regex(analysis["bold_terms"])
    if regex is not None:
        def walk_paragraphs(container):
            for p in container.paragraphs:
                for run in list(p.runs):
                    _bold_in_run(run, regex)
        walk_paragraphs(doc)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for run in list(p.runs):
                            _bold_in_run(run, regex)

    label = "Core Competencies: " if ats else "Key Skills for this Role: "
    _insert_key_skills(doc, _key_skills_line(analysis, ats=ats), label=label,
                       bold_terms=analysis["bold_terms"])

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# --------------------------------------------------------------------------- #
# PDF UPLOAD -> rebuilt DOCX (structured, one page)
# --------------------------------------------------------------------------- #
# Common resume section headings (used to detect headings in extracted text so
# the rebuilt doc keeps the original's structure instead of a flat text dump).
_SECTION_WORDS = (
    "summary", "objective", "profile", "about",
    "experience", "work experience", "employment", "professional experience",
    "education", "academic", "skills", "technical skills", "core competencies",
    "projects", "project", "certifications", "certificates", "courses",
    "achievements", "accomplishments", "awards", "publications", "languages",
    "interests", "hobbies", "contact", "references", "volunteer", "activities",
)
# Includes the private-use glyphs Word/Symbol/Wingdings fonts use for bullets
# ( etc.) — PDF text extraction emits these literally, so if they're not
# recognised as bullets they'd render as a stray symbol in the rebuilt resume.
_BULLET_CHARS = (
    "•", "◦", "▪", "‣", "·", "∙", "●", "○", "*", "-", "–", "—",
    "", "", "", "", "",
)


def _looks_like_heading(line: str) -> bool:
    """A short line that is a section title (ALL CAPS or a known section word)."""
    s = line.strip().rstrip(":").strip()
    if not s or len(s) > 40:
        return False
    low = s.lower()
    if low in _SECTION_WORDS:
        return True
    # ALL-CAPS (or mostly) short line with no sentence punctuation -> heading.
    letters = [c for c in s if c.isalpha()]
    if letters and len(s.split()) <= 5 and sum(c.isupper() for c in letters) / len(letters) >= 0.8:
        return True
    return False


def _is_bullet(line: str) -> bool:
    s = line.lstrip()
    return bool(s) and s[0] in _BULLET_CHARS and s[:2] != "--"


def _is_contact(line: str) -> bool:
    """Email / phone / links line that usually sits under the name."""
    low = line.lower()
    return ("@" in line or "http" in low or "linkedin" in low or "github" in low
            or re.search(r"\+?\d[\d\s\-()]{7,}", line) is not None or "|" in line)


def _set_bottom_border(paragraph):
    """Give a paragraph a thin bottom border (the rule under a section heading)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")        # ~0.75pt rule
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), "888888")
    pBdr.append(bottom)


# Base spacing (space_before, space_after, in pt) per block kind, before the
# density multiplier is applied.
_BLOCK_SPACING = {
    "name": (0, 1), "contact": (0, 2), "skillhead": (4, 1), "skills": (0, 2),
    "heading": (5, 1), "bullet": (0, 0), "body": (0, 0),
}
# Density presets tried loosest -> tightest. We pick the FIRST that fits one page;
# if none do, the tightest is used. This reduces SPACING/font, never content.
_DENSITY_PRESETS = (
    {"body": 9.0, "head": 10.0, "name": 17.0, "contact": 8.5, "ls": 1.0,  "sp": 1.0},
    {"body": 8.5, "head": 9.5,  "name": 16.0, "contact": 8.0, "ls": 1.0,  "sp": 0.7},
    {"body": 8.0, "head": 9.0,  "name": 15.0, "contact": 8.0, "ls": 0.98, "sp": 0.5},
    {"body": 7.5, "head": 8.5,  "name": 14.0, "contact": 7.5, "ls": 0.95, "sp": 0.3},
    {"body": 7.0, "head": 8.0,  "name": 13.0, "contact": 7.0, "ls": 0.92, "sp": 0.15},
    {"body": 6.5, "head": 7.5,  "name": 12.0, "contact": 6.5, "ls": 0.90, "sp": 0.10},
)


def _block_size(kind: str, ps: dict) -> float:
    return {"name": ps["name"], "contact": ps["contact"], "skillhead": ps["head"],
            "heading": ps["head"], "skills": ps["body"], "bullet": ps["body"],
            "body": ps["body"]}[kind]


def _parse_resume_blocks(resume_text: str, analysis: dict, ats: bool):
    """Turn extracted PDF text into ordered (kind, text) blocks: the name, up to
    two contact lines, the inserted skills section, then headings / bullets /
    body — using _looks_like_heading() and _is_bullet() to detect structure."""
    lines = [ln.rstrip() for ln in (resume_text or "").splitlines()]
    nonempty = [ln for ln in lines if ln.strip()]
    blocks = []

    body_start = 0
    if nonempty:
        name_line = nonempty[0]
        blocks.append(("name", name_line.strip()))
        body_start = lines.index(name_line) + 1
        taken = 0
        while body_start < len(lines) and taken < 2:
            ln = lines[body_start]
            if not ln.strip():
                body_start += 1
                continue
            if _is_contact(ln) and not _looks_like_heading(ln):
                blocks.append(("contact", ln.strip()))
                body_start += 1
                taken += 1
            else:
                break

    skills_line = _key_skills_line(analysis, ats=ats)
    if skills_line:
        blocks.append(("skillhead", "CORE COMPETENCIES" if ats
                       else "KEY SKILLS FOR THIS ROLE"))
        blocks.append(("skills", skills_line))

    for ln in lines[body_start:]:
        if not ln.strip():
            continue
        if _looks_like_heading(ln):
            blocks.append(("heading", ln.strip().rstrip(":").upper()))
        elif _is_bullet(ln):
            text = ln.lstrip()
            text = text[1:].strip() if text[:1] in _BULLET_CHARS else text
            blocks.append(("bullet", text))
        else:
            blocks.append(("body", ln.strip()))
    return blocks


def _estimate_height_pt(blocks, ps, usable_w_pt) -> float:
    """Rough rendered height (pt) of all blocks at a given density preset. Used to
    decide whether the resume fits one page (no real renderer in python-docx)."""
    import math
    total = 0.0
    for kind, text in blocks:
        size = _block_size(kind, ps)
        # ~0.50*fontsize per char is a deliberately wide estimate (overestimates
        # lines -> errs toward shrinking, which keeps us on one page).
        cpl = max(16, usable_w_pt / (0.50 * size))
        nlines = max(1, math.ceil(len(text) / cpl))
        line_h = ps["ls"] * 1.25 * size      # Word: Calibri single = ~1.22em, + safety
        before, after = _BLOCK_SPACING[kind]
        total += nlines * line_h + (before + after) * ps["sp"]
    return total


def rebuild_docx_from_text(resume_text: str, analysis: dict, ats: bool = False) -> bytes:
    """Rebuild a .docx from extracted PDF text, keeping resume STRUCTURE (name,
    contact, section headings, bullets) and compressing everything onto ONE page.

    A PDF can't be edited in place, so instead of a flat multi-page text dump we
    reconstruct a tight, structured single-page document: large bold centered
    name, centered contact line(s), bold UPPERCASE section headings with a bottom
    rule, real "•" bullets, and matched JD keywords bolded inline. If the content
    would overflow one page we step through tighter density presets — shrinking
    spacing and font, never dropping content."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    blocks = _parse_resume_blocks(resume_text, analysis, ats)

    doc = Document()
    # Tight one-page geometry.
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(28)      # ~0.39"
        section.left_margin = section.right_margin = Pt(40)      # ~0.55"
    sec = doc.sections[0]
    usable_w = (sec.page_width - sec.left_margin - sec.right_margin) / 12700.0  # -> pt
    usable_h = (sec.page_height - sec.top_margin - sec.bottom_margin) / 12700.0

    # Pick the loosest density that still fits one page (fall back to tightest).
    chosen = _DENSITY_PRESETS[-1]
    for ps in _DENSITY_PRESETS:
        if _estimate_height_pt(blocks, ps, usable_w) <= usable_h:
            chosen = ps
            break

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(chosen["body"])
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = chosen["ls"]

    regex = _bold_terms_regex(analysis["bold_terms"])

    def _add_text(p, text):
        p.add_run(text)
        if regex is not None:
            for run in list(p.runs):
                _bold_in_run(run, regex)

    def _para(kind):
        before, after = _BLOCK_SPACING[kind]
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before * chosen["sp"])
        p.paragraph_format.space_after = Pt(after * chosen["sp"])
        p.paragraph_format.line_spacing = chosen["ls"]
        return p

    def _heading(text, size):
        hp = _para("heading")
        hr = hp.add_run(text)
        hr.bold = True
        hr.font.size = Pt(size)
        hr.font.color.rgb = RGBColor(0x1a, 0x1a, 0x1a)
        _set_bottom_border(hp)
        return hp

    for kind, text in blocks:
        if kind == "name":
            p = _para("name")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(text)
            r.bold = True
            r.font.size = Pt(chosen["name"])
        elif kind == "contact":
            p = _para("contact")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(text)
            r.font.size = Pt(chosen["contact"])
            r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        elif kind in ("skillhead", "heading"):
            _heading(text, chosen["head"])
        elif kind == "skills":
            _add_text(_para("skills"), text)
        elif kind == "bullet":
            bp = _para("bullet")
            bp.paragraph_format.left_indent = Pt(12)
            bp.add_run("• ")           # U+2022 bullet
            _add_text(bp, text)
        else:  # body
            _add_text(_para("body"), text)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# --------------------------------------------------------------------------- #
# DOCX -> PDF
# --------------------------------------------------------------------------- #
def docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert .docx to PDF using Microsoft Word (docx2pdf). Falls back to a
    reportlab text render if Word/conversion is unavailable. Raises on total
    failure so the caller can surface a clear message."""
    # Preferred: Word, so the PDF matches the .docx styling exactly.
    try:
        import pythoncom  # noqa: needed when called from a worker thread
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None
    try:
        from docx2pdf import convert
        with tempfile.TemporaryDirectory() as td:
            in_path = os.path.join(td, "in.docx")
            out_path = os.path.join(td, "in.pdf")
            with open(in_path, "wb") as f:
                f.write(docx_bytes)
            convert(in_path, out_path)
            if os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    return f.read()
        raise RuntimeError("Word produced no PDF output")
    except Exception as word_err:
        # No Word (hosted site): first try the formatted Word-free renderer (keeps bold,
        # headings, centring, bullets, links, ONE page); the plain text dump is the last resort.
        try:
            return _fallback_formatted_pdf(docx_bytes)
        except Exception:
            pass
        try:
            return _fallback_text_pdf(docx_bytes)
        except Exception as fb_err:
            raise RuntimeError(
                f"Could not convert to PDF (Word: {word_err}; fallback: {fb_err}). "
                "The Word (.docx) file was still produced."
            )
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _fallback_formatted_pdf(docx_bytes: bytes) -> bytes:
    """Word-free docx -> PDF that keeps the resume's structure: bold/italic runs, per-paragraph
    size, centring, bullets, hyperlinks, spacing, page size/margins; table rows become one
    'a  |  b' line. Standard PDF fonts (Helvetica/Times/Courier) and a single column, so it
    reads cleanly in an ATS. Shrinks step by step until it is exactly ONE page."""
    import docx_pagefit as PF
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph as DPara
    from docx.text.run import Run as DRun
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    doc = Document(io.BytesIO(docx_bytes))
    defaults = PF._doc_defaults(doc)
    sec = doc.sections[0]
    page = (sec.page_width.pt, sec.page_height.pt)
    margins = (sec.left_margin.pt, sec.right_margin.pt, sec.top_margin.pt, sec.bottom_margin.pt)
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def runs_markup(p):
        """[(markup, size, font, bold)] pieces of a paragraph, hyperlinks kept."""
        parts = []
        for child in p._p.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "r":
                rs, href = [DRun(child, p)], None
            elif tag == "hyperlink":
                rid = child.get(qn("r:id"))
                href = doc.part.rels[rid].target_ref if rid and rid in doc.part.rels else None
                rs = [DRun(r, p) for r in child.xpath("./w:r")]
            else:
                continue
            for r in rs:
                if not r.text:
                    continue
                font, size, bold = PF._run_font(p, r, defaults)
                m = esc(r.text)
                if bold:
                    m = f"<b>{m}</b>"
                if r.italic:
                    m = f"<i>{m}</i>"
                if href and href.lower().startswith(("http", "mailto")):
                    m = f'<a href="{esc(href)}">{m}</a>'
                parts.append((m, size, font, bold))
        return parts

    # ---- collect blocks once: (markup, size, font, align, left, bullet, before, after, line_mult)
    blocks = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = DPara(child, doc)
            parts = runs_markup(p)
            if not parts:
                continue
            is_list = bool(p._p.xpath("./w:pPr/w:numPr")) or (p.style is not None and p.style.name.lower().startswith("list"))
            al = p.alignment
            if al is None:
                for st in PF._style_chain(p.style):
                    if st.paragraph_format.alignment is not None:
                        al = st.paragraph_format.alignment
                        break
            left = PF._style_attr(p, "left_indent", defaults)
            before = PF._style_attr(p, "space_before", defaults)
            after = PF._style_attr(p, "space_after", defaults)
            ls = PF._style_attr(p, "line_spacing", defaults)
            blocks.append(dict(
                markup="".join(x[0] for x in parts), size=max(x[1] for x in parts), font=parts[0][2],
                align={1: TA_CENTER, 2: TA_RIGHT}.get(int(al) if al is not None else 0, TA_LEFT),
                left=(left.pt if left is not None else (14.0 if is_list else 0.0)), bullet=is_list,
                before=(before.pt if before is not None else defaults[2]),
                after=(after.pt if after is not None else defaults[3]),
                mult=(float(ls) if ls is not None and not hasattr(ls, "pt") else defaults[4])))
        elif tag == "tbl":
            t = Table(child, doc)
            for row in t.rows:
                seen, cells = set(), []
                for c in row.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    ps = [DPara(pp._p, doc) for pp in c.paragraphs if pp.text.strip()]
                    pieces = [x for pp in ps for x in runs_markup(pp)]
                    if pieces:
                        cells.append(pieces)
                if not cells:
                    continue
                allp = [x for c in cells for x in c]
                blocks.append(dict(
                    markup="  |  ".join("".join(x[0] for x in c) for c in cells),
                    size=max(x[1] for x in allp), font=allp[0][2], align=TA_LEFT, left=0.0, bullet=False,
                    before=0.0, after=1.0, mult=defaults[4]))
    if not blocks:
        raise ValueError("empty document")

    def build(scale):
        out = io.BytesIO()
        k = max(0.45, scale)
        pdf = SimpleDocTemplate(out, pagesize=page, leftMargin=margins[0] * max(0.55, k), rightMargin=margins[1] * max(0.55, k),
                                topMargin=margins[2] * max(0.55, k), bottomMargin=margins[3] * max(0.55, k))
        story = []
        for b in blocks:
            base, _wf, lh = PF._font_info(b["font"])
            size = max(5.5, b["size"] * scale)
            # the bullet is part of the TEXT ("• ...", hanging indent) so a text-only parser sees it
            st = ParagraphStyle("b", fontName=base, fontSize=size, leading=size * lh * b["mult"],
                                alignment=b["align"], leftIndent=b["left"] + (10 if b["bullet"] else 0),
                                firstLineIndent=(-10 if b["bullet"] else 0),
                                spaceBefore=b["before"] * scale, spaceAfter=b["after"] * scale)
            bold_font = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[base]
            italic_font = {"Helvetica": "Helvetica-Oblique", "Times-Roman": "Times-Italic", "Courier": "Courier-Oblique"}[base]
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            try:
                registerFontFamily(base, normal=base, bold=bold_font, italic=italic_font, boldItalic=bold_font)
            except Exception:
                pass
            story.append(Paragraph(("•&nbsp;" + b["markup"]) if b["bullet"] else b["markup"], st))
        pdf.build(story)
        return out.getvalue()

    data = b""
    for s in (1.0, 0.96, 0.92, 0.88, 0.84, 0.80, 0.76, 0.72, 0.68, 0.64, 0.60, 0.56):
        data = build(s)
        if len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data)) <= 1:
            break
    return data


def _fallback_text_pdf(docx_bytes: bytes) -> bytes:
    """Last-resort PDF (no Word available): the docx text in a simple reportlab layout, shrunk
    step by step until it fits ONE page."""
    from docx import Document
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    doc = Document(io.BytesIO(docx_bytes))
    texts = []
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            texts.append(txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    if not texts:
        texts = ["(empty resume)"]

    def build(size):
        out = io.BytesIO()
        st = ParagraphStyle("n", fontName="Helvetica", fontSize=size, leading=size * 1.18)
        m = 12 * mm if size >= 9 else 8 * mm
        pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=15 * mm if size >= 9 else 11 * mm,
                                rightMargin=15 * mm if size >= 9 else 11 * mm, topMargin=m, bottomMargin=m)
        story = []
        for t in texts:
            story.append(Paragraph(t, st))
            story.append(Spacer(1, size * 0.3))
        pdf.build(story)
        return out.getvalue()

    data = b""
    for size in (10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
        data = build(size)
        if len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data)) <= 1:
            break
    return data


# --------------------------------------------------------------------------- #
# ONE-PAGE GUARANTEE for an uploaded .docx (edited in place)
# --------------------------------------------------------------------------- #
_WORD_OK = None            # None = untested, True/False after first try (Word is local/Windows only)
_ORIG_PAGES = {}           # sha1(original bytes) -> page count


def _word_pdf(docx_bytes: bytes):
    """docx -> PDF bytes via Microsoft Word, or None when Word is not available
    (e.g. Vercel/Linux). The first failure is remembered so we never retry slowly."""
    global _WORD_OK
    if _WORD_OK is False:
        return None
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None
    try:
        from docx2pdf import convert
        with tempfile.TemporaryDirectory() as td:
            i, o = os.path.join(td, "in.docx"), os.path.join(td, "in.pdf")
            with open(i, "wb") as f:
                f.write(docx_bytes)
            convert(i, o)
            if os.path.exists(o):
                _WORD_OK = True
                with open(o, "rb") as f:
                    return f.read()
        return None
    except Exception:
        if _WORD_OK is None:
            _WORD_OK = False
        return None
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _pdf_page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf))


def shrink_docx(docx_bytes: bytes, f: float) -> bytes:
    """Scale every font size, paragraph gap and margin of a .docx by `f` (<1) — keeps the
    user's layout, just a little tighter."""
    from docx import Document
    from docx.shared import Pt, Emu
    doc = Document(io.BytesIO(docx_bytes))

    def scale_para(p):
        pf = p.paragraph_format
        for attr in ("space_before", "space_after"):
            v = getattr(pf, attr)
            if v is not None:
                setattr(pf, attr, Emu(int(v * f)))
        for r in p.runs:
            if r.font.size is not None:
                r.font.size = Pt(max(5.5, round(r.font.size.pt * f * 2) / 2))

    for st in doc.styles:
        try:
            if st.font is not None and st.font.size is not None:
                st.font.size = Pt(max(5.5, round(st.font.size.pt * f * 2) / 2))
            pf = getattr(st, "paragraph_format", None)
            if pf is not None:
                for attr in ("space_before", "space_after"):
                    v = getattr(pf, attr)
                    if v is not None:
                        setattr(pf, attr, Emu(int(v * f)))
        except Exception:
            continue
    # Many Word files take their font size and paragraph gaps from the document DEFAULTS
    # (w:docDefaults), not from any style or run — scale those too, or such a file can't shrink.
    try:
        from docx.oxml.ns import qn
        dd = doc.styles.element.find(qn("w:docDefaults"))
        if dd is not None:
            for sz in list(dd.iter(qn("w:sz"), qn("w:szCs"))):
                v = sz.get(qn("w:val"))
                if v and v.isdigit():
                    sz.set(qn("w:val"), str(max(11, int(round(int(v) * f)))))   # half-points, floor 5.5pt
            for sp in list(dd.iter(qn("w:spacing"))):
                for a in ("w:before", "w:after"):
                    v = sp.get(qn(a))
                    if v and v.isdigit():
                        sp.set(qn(a), str(int(int(v) * f)))
    except Exception:
        pass
    for p in doc.paragraphs:
        scale_para(p)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    scale_para(p)
    m = max(0.72, f)
    for sec in doc.sections:
        for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
            v = getattr(sec, attr)
            if v is not None:
                setattr(sec, attr, Emu(int(v * m)))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# Word-free one-page fit (hosted site / Linux). docx_pagefit.estimate_fill() was calibrated against
# real Microsoft Word (calibrate_pagefit.py): it never under-counted by more than ~1-2%, so we ask
# for a little headroom and shrink only as far as needed.
_EST_LIMIT = 0.985          # estimated fill we accept (1.0 = exactly one page)
_EST_MULTIPAGE = 1.12       # an ORIGINAL estimated above this is a real multi-page CV: leave it alone


def _estimate_fit(original: bytes, tailored: bytes, force: bool) -> bytes:
    """Same policy as the Word path, using the estimator instead of Word."""
    try:
        import docx_pagefit as PF
        e_orig = 0.0
        if not force:
            e_orig = PF.estimate_fill(original) if original else 0.0
            if e_orig > _EST_MULTIPAGE:                    # multi-page CV: never crush it
                return tailored
        limit = _EST_LIMIT if force else max(e_orig, _EST_LIMIT)   # never tighter than the original
        if PF.estimate_fill(tailored) <= limit:
            return tailored
        cand = tailored
        for f in (0.98, 0.96, 0.94, 0.92, 0.90, 0.88, 0.86, 0.84, 0.82, 0.80, 0.78, 0.76):
            cand = shrink_docx(tailored, f)
            if PF.estimate_fill(cand) <= limit:
                return cand
        return cand
    except Exception:
        return tailored


def fit_docx_one_page(original: bytes, tailored: bytes, force: bool = False) -> bytes:
    """Keep a tailored resume on ONE page. If the user's original was one page and the
    tailoring (added keywords/skills) pushed it onto a second, shrink type/spacing/margins a
    little at a time, verifying the page count with Word. A multi-page original is left alone
    (we never crush a 2-page CV). Without Word (the hosted Vercel site) the page count is
    ESTIMATED instead (docx_pagefit, calibrated against real Word)."""
    import hashlib
    if _WORD_OK is None:
        _word_pdf(tailored)                    # one-time probe: remembers whether Word exists
    if _WORD_OK is False:
        return _estimate_fit(original, tailored, force)
    if not force:                      # force=True: a document WE rebuilt from a PDF must be 1 page
        key = hashlib.sha1(original).hexdigest()
        if key not in _ORIG_PAGES:
            pdf = _word_pdf(original)
            _ORIG_PAGES[key] = _pdf_page_count(pdf) if pdf else None
        if _ORIG_PAGES[key] != 1:
            return tailored
    last = tailored
    for f in (1.0, 0.96, 0.92, 0.88, 0.84, 0.80, 0.76):
        cand = tailored if f == 1.0 else shrink_docx(tailored, f)
        pdf = _word_pdf(cand)
        if pdf is None:
            return tailored
        last = cand
        if _pdf_page_count(pdf) <= 1:
            return cand
    return last


# --------------------------------------------------------------------------- #
# TOP-LEVEL ENTRY
# --------------------------------------------------------------------------- #
def tailor_upload(filename: str, data: bytes, jd_text: str = "",
                  extra_skills: str = "", want_pdf: bool = True,
                  want_docx: bool = True, ats: bool = True) -> dict:
    """Tailor an uploaded resume.

    ats=True (default): also add spelled-out / acronym forms of skills the resume ALREADY
    shows (e.g. "Amazon Web Services (AWS)"). Never adds skills the resume lacks.

    Returns dict with:
      analysis, layout_preserved (bool), docx (bytes|None), pdf (bytes|None),
      pdf_note (str|None), ats_added (int)  -- keywords added for ATS coverage.
    """
    if not data:
        raise ValueError("Empty file.")
    ext = os.path.splitext(filename or "")[1].lower()

    resume_text = extract_text(filename, data)
    if not resume_text.strip():
        raise ValueError(
            "No readable text found. If this is a scanned/image PDF, upload a "
            "text-based PDF or a .docx instead."
        )

    if ext == ".pdf":
        resume_text = restore_link_text(resume_text, _pdf_link_uris(data))
    info = analyze(resume_text, jd_text, extra_skills)

    layout_preserved = ext == ".docx"
    if layout_preserved:
        tailored_docx = fit_docx_one_page(data, tailor_docx(data, info, ats=ats))
    else:
        tailored_docx = fit_docx_one_page(b"", rebuild_docx_from_text(resume_text, info, ats=ats), force=True)

    result = {
        "analysis": info,
        "layout_preserved": layout_preserved,
        "docx": tailored_docx if want_docx else None,
        "pdf": None,
        "pdf_note": None,
        "ats_added": len(info.get("expanded", [])) if ats else 0,
    }

    if want_pdf:
        try:
            result["pdf"] = docx_to_pdf(tailored_docx)
        except Exception as e:
            result["pdf_note"] = str(e)

    return result
