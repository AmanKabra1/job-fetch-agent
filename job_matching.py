"""
Resume-aware job matching.
==========================

Shared scoring used by both the local app (live scrape) and the Vercel
dashboard (reads the Google Sheet). Scores a job 0-100 against Aman's resume
using the same SKILL_KEYWORDS map that drives the resume builder, so "what
ranks high" and "what gets emphasized on the resume" stay consistent.
"""

import resume_profile as P
from resume_builder import find_matched_skills

# Search terms derived from Aman's "most suitable job titles".
SEARCH_TERMS = [
    "Node.js Developer",
    "NestJS Developer",
    "Backend Developer",
    "SDE 1 Software Engineer",
    "Full Stack Developer Node React",
    "Java Spring Boot Developer",
    "Python Developer FastAPI",
]

# How strongly each skill counts toward a match. Anything not listed = 3.
SKILL_WEIGHTS = {
    "NestJS": 10, "Node.js": 10, "TypeScript": 9, "Express.js": 7,
    "Microservices": 8, "RESTful APIs": 7, "Spring Boot": 7,
    "MySQL (schema design, query optimization, stored procedures)": 7,
    "PostgreSQL": 7, "JavaScript (ES6+)": 6, "Python": 6, "FastAPI": 6,
    "Java (Spring Boot)": 6, "AWS S3": 6, "Docker": 6,
    "Django": 5, "Flask": 5, "SQL": 5, "CI/CD Pipelines": 5,
    "Angular 17 (Signals, standalone components, RxJS)": 5,
    "Go (Golang)": 4, "JWT Authentication": 4, "OAuth 2.0": 4,
    "GitHub Actions": 4, "Jenkins": 4,
}

# Title keywords that signal a strong fit (extra points if in the title).
_TITLE_SIGNALS = (
    "nestjs", "node", "backend", "back end", "back-end", "full stack",
    "fullstack", "sde", "software engineer", "software developer", "java",
    "python", "api", "microservice",
)
# Titles that are almost certainly NOT for Aman (penalised).
_TITLE_NEGATIVE = (
    "senior", "sr.", "sr ", "lead", "principal", "staff", "architect",
    "manager", "head of", "director", "10+ year", "8+ year", "7+ year",
)


def score_job(title: str, description: str):
    """Return (score 0-100, sorted list of matched skill labels)."""
    title = title or ""
    description = description or ""
    matched = find_matched_skills(f"{title} {description}")
    if not matched:
        return 0, []

    weight = sum(SKILL_WEIGHTS.get(s, 3) for s in matched)
    score = round(weight * 1.4)

    tl = title.lower()
    title_bonus = min(12, sum(3 for kw in _TITLE_SIGNALS if kw in tl))
    score += title_bonus

    if any(neg in tl for neg in _TITLE_NEGATIVE):
        score -= 18  # likely too senior for a ~2-yr profile

    score = max(0, min(100, score))
    return score, sorted(matched)


def experience_fit(title: str, description: str) -> str:
    """Rough seniority heuristic for display."""
    text = f"{title or ''} {description or ''}".lower()
    senior = ["senior", "sr.", "lead", "principal", "staff", "architect",
              "5+ year", "6+ year", "7+ year", "8+ year", "10+ year"]
    if any(m in text for m in senior):
        return "Likely Senior - review"
    junior = ["sde-1", "sde 1", "sde1", "associate", "1-2 year", "1 to 2 year",
              "0-2 year", "0-3 year", "entry level", "graduate", "fresher", "junior"]
    if any(m in text for m in junior):
        return "Entry / 1-2 yrs"
    return "Unspecified"
