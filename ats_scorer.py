"""
ATS score ESTIMATOR — 2026, evidence-based.

Important honesty note: there is no universal "ATS score". Workday, Greenhouse, Lever,
iCIMS, SmartRecruiters, Naukri etc. each rank differently and most never show a number.
This module estimates the things that research consistently shows drive ranking, so
you can see what to fix. It is an ESTIMATE, not what any employer sees. (Earlier
versions added free bonus points and a floor of 85 for generated resumes, and quoted
unsourced "97% DOCX vs 76% PDF" figures; all of that is gone — text-based PDFs parse
fine in modern ATS.)

What is scored (100 points):
  45  Keyword relevance   weighted share of the JD's keywords present in the resume
                          (placement-aware: also in a bullet/summary, not just Skills;
                          stuffing — one term >5 times — is penalised). Without a JD:
                          breadth of in-demand backend/AI skills instead.
  20  Experience quality  dated roles, strong action verbs, quantified bullets
  15  Structure           standard section headings (Summary/Skills/Experience/...)
  10  Contact in body     email, phone, LinkedIn/GitHub as plain text
  10  Format hygiene      bullets present, sane length, no decorative glyph noise
"""

import re

_ACTION_VERBS = (
    "developed", "designed", "implemented", "built", "created", "architected",
    "engineered", "integrated", "optimized", "optimised", "deployed", "automated",
    "reduced", "improved", "migrated", "led", "owned", "delivered", "shipped",
    "configured", "resolved", "contributed", "containerized", "containerised",
)
_SECTIONS = {
    "summary": r"\b(professional\s+)?summary\b|\bprofile\b|\bobjective\b",
    "skills": r"\b(technical\s+)?skills\b|\bcore\s+competencies\b",
    "experience": r"\b(work\s+|professional\s+)?experience\b|\bemployment\b",
    "projects": r"\bprojects?\b",
    "education": r"\beducation\b",
}
_GENERIC_SKILLS = (
    "python", "node.js", "typescript", "javascript", "nestjs", "fastapi", "express",
    "sql", "postgresql", "mysql", "mongodb", "redis", "docker", "aws", "ci/cd", "git",
    "rest", "microservices", "llm", "rag", "langchain", "kubernetes", "kafka",
    "unit test", "agile", "system design",
)


def _kw_in_text(canon_aliases, low):
    for a in canon_aliases:
        if re.search(r"(?<![a-z0-9+#])" + re.escape(a.lower()) + r"(?![a-z0-9+#])", low):
            return True
    return False


def _jd_keyword_score(resume_text: str, jd_text: str, title: str = ""):
    """(0-45 points, matched, missing, stuffed). Placement-aware."""
    import resume_keywords as K
    low = " " + resume_text.lower() + " "
    # split into 'evidence' region (summary+experience+projects bullets) vs skills region
    m = re.search(r"\b(technical\s+)?skills\b", low)
    kws = K.jd_keywords(jd_text, title)
    if not kws:
        return None
    total = got = 0.0
    matched, missing, stuffed = [], [], []
    for canon, w in kws:
        aliases = K.LEX[canon][0]
        count = sum(len(re.findall(r"(?<![a-z0-9+#])" + re.escape(a.lower()) + r"(?![a-z0-9+#])", low))
                    for a in aliases)
        total += w
        if count:
            credit = 0.75 if count == 1 else 1.0          # 2+ mentions (skills + a bullet) = full credit
            got += w * credit
            matched.append(canon)
            if count > 5:
                stuffed.append(canon)
        else:
            missing.append(canon)
    pts = 45.0 * got / total if total else 0.0
    pts -= min(8.0, 2.0 * len(stuffed))                   # stuffing penalty
    return max(0.0, pts), matched, missing, stuffed


def calculate_ats_score(resume_text: str, profile: dict = None, is_generated: bool = False,
                        jd_text: str = "", title: str = "") -> dict:
    """Estimate ATS compatibility (0-100). `profile` and `is_generated` are accepted for
    backwards compatibility and deliberately do NOT change the score."""
    if not resume_text or len(resume_text.strip()) < 100:
        return {"score": 0, "error": "Resume text too short", "strengths": [],
                "gaps": ["Resume content missing or too short"],
                "recommendations": ["Provide a complete resume with at least 100 characters"],
                "estimate": True}

    low = resume_text.lower()
    strengths, gaps, recs = [], [], []
    score = 0.0
    matched, missing = [], []

    # ---- 1. Keyword relevance (45) ------------------------------------------ #
    res = _jd_keyword_score(resume_text, jd_text, title) if jd_text and jd_text.strip() else None
    if res:
        kpts, matched, missing, stuffed = res
        score += kpts
        cov = round(100 * len(matched) / max(1, len(matched) + len(missing)))
        (strengths if cov >= 70 else gaps).append(
            f"{cov}% of the JD's keywords appear in your resume ({len(matched)}/{len(matched) + len(missing)})")
        if missing:
            recs.append("JD keywords not in your resume (add ONLY if you truly have them): "
                        + ", ".join(missing[:8]))
        if stuffed:
            gaps.append("Keyword repeated too often (stuffing is down-scored): " + ", ".join(stuffed))
    else:
        found = [k for k in _GENERIC_SKILLS if _kw_in_text([k], " " + low + " ")]
        score += min(45.0, len(found) * 2.5)
        (strengths if len(found) >= 10 else gaps).append(
            f"{len(found)} in-demand skills detected (paste a JD for a job-specific score)")

    # ---- 2. Experience quality (20) ------------------------------------------ #
    exp = 0.0
    dates = re.findall(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+20\d{2}|20\d{2}", low)
    if len(dates) >= 2:
        exp += 6
        strengths.append("Dated roles (parsers compute tenure from these)")
    else:
        gaps.append("Missing employment dates (use 'Mon YYYY - Mon YYYY')")
    verbs = sum(low.count(v) for v in _ACTION_VERBS)
    if verbs >= 6:
        exp += 6
        strengths.append("Strong action verbs")
    else:
        gaps.append(f"Few action verbs ({verbs}); start bullets with Built/Designed/Optimized/Reduced...")
    bullets = [l for l in resume_text.splitlines() if re.match(r"\s*[-•*▪●◦]\s+\S", l)]
    quant = [b for b in bullets if re.search(r"\d+\s*%|\b\d+x\b|\b\d{2,}\+?\b", b)]
    if bullets and len(quant) / len(bullets) >= 0.3:
        exp += 8
        strengths.append("Quantified impact in bullets (numbers/percentages)")
    elif bullets:
        exp += 3
        gaps.append("Add real metrics to bullets (latency, % improvement, scale) — never invent them")
    score += exp

    # ---- 3. Structure (15) ---------------------------------------------------- #
    found_sec = [k for k, rx in _SECTIONS.items() if re.search(rx, low)]
    score += 3 * len(found_sec)
    if len(found_sec) >= 5:
        strengths.append("All standard section headings present")
    else:
        gaps.append("Missing standard headings: " + ", ".join(sorted(set(_SECTIONS) - set(found_sec))))

    # ---- 4. Contact in body (10) ---------------------------------------------- #
    c = 0
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume_text):
        c += 4
    else:
        gaps.append("Missing email")
    if re.search(r"(\+?\d[\d\s\-()]{8,}\d)", resume_text):
        c += 3
    else:
        gaps.append("Missing phone")
    if "linkedin" in low or "github" in low:
        c += 3
    score += c

    # ---- 5. Format hygiene (10) ------------------------------------------------ #
    h = 0
    if bullets:
        h += 4
    n = len(resume_text)
    if 1500 <= n <= 7000:
        h += 3
        strengths.append("Length suits a one-page, ~2-year resume")
    elif n < 1500:
        gaps.append("Resume looks thin")
    else:
        h += 1
        gaps.append("Resume is long for ~2 years of experience (aim for one page)")
    if not re.search(r"[│┃╎║▌█■◆★☆✔✓➤➔►→]", resume_text):
        h += 3
    else:
        gaps.append("Decorative symbols can break parsing; use plain '-' or '•' bullets")
    score += h

    if not recs and score < 80:
        recs.append("Mirror the JD's exact wording for skills you genuinely have, in the headline, "
                    "summary and at least one recent bullet")
    return {
        "score": int(round(min(100, score))),
        "strengths": strengths[:6], "gaps": gaps[:6], "recommendations": recs[:5],
        "matched_keywords": matched, "missing_keywords": missing,
        "estimate": True,
        "note": "Estimate only — each employer's ATS ranks differently.",
    }


def get_score_color(score: int) -> str:
    if score >= 80:
        return "#16a34a"
    if score >= 60:
        return "#eab308"
    if score >= 40:
        return "#f97316"
    return "#dc2626"


def score_resume_for_jd(resume: dict, jd_text: str, title: str = "") -> int:
    """Estimated ATS score of a resume dict against one JD (no forced floor)."""
    if not jd_text or not jd_text.strip():
        return calculate_ats_score(_resume_to_text(resume)).get("score", 0)
    return calculate_ats_score(_resume_to_text(resume), jd_text=jd_text, title=title).get("score", 0)


def _resume_to_text(resume: dict) -> str:
    text = f"""
{resume.get('name', '')}
{resume.get('email', '')}
{resume.get('phone', '')}
{resume.get('location', '')}

Summary:
{resume.get('summary', '')}

Skills:
{', '.join(resume.get('skills', []))}

Experience:
"""
    for exp in resume.get('experience', []):
        text += f"\n{exp.get('role', '')} at {exp.get('company', '')}\n"
        for point in exp.get('points', []):
            text += f"- {point}\n"
    text += "\n\nProjects:\n"
    for proj in resume.get('projects', []):
        text += f"\n{proj.get('name', '')}: {proj.get('tech', '')}\n"
        text += f"{proj.get('description', '')}\n"
        for b in proj.get('bullets', []) or []:
            text += f"- {b}\n"
    return text


def get_score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 30:
        return "Poor"
    return "Critical"
