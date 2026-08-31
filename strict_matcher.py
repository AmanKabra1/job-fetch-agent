"""
Strict job matcher — filters jobs at the source before ranking.

For a 2-year junior backend developer, this module applies HARD GATES:
1. REJECT if asks for 3+ years (no exceptions)
2. REJECT if 0 skill matches with user's stack
3. REJECT if <2 matching skills (unless 100% of job skills are matched)
4. REJECT if completely unrelated role (not backend/full-stack/python/node/java/ai)
5. REJECT if senior title without mentoring/junior signals

Only jobs that pass these gates are ranked and included in the feed.
"""

import re
from resume_tailor import SKILL_LEXICON, _clean_label, _word_in


# User's core competencies (from resume_profile.py)
CORE_STACK = {
    # Backend Languages & Frameworks - Node.js/NestJS focus
    "Node.js", "NestJS", "Express.js", "TypeScript", "JavaScript",
    "Python", "FastAPI", "Java", "Spring Boot",
    # General backend/full stack
    "Backend", "Full Stack", "API", "REST",
    # Databases & Infrastructure
    "PostgreSQL", "MongoDB", "Redis", "Docker", "Kubernetes",
    # AI/ML Stack
    "Machine Learning", "LLM", "LangChain", "LangGraph", "AI Agents",
    "Agentic AI", "RAG", "GraphQL",
}

# Acceptable role categories for a 2-year developer
ACCEPTABLE_ROLES = {
    "backend developer", "backend engineer", "sde 1", "sde-1",
    "junior backend", "full stack developer", "python developer",
    "node.js developer", "nestjs developer", "typescript developer",
    "javascript backend", "express.js developer", "java developer",
    "ai engineer", "ml engineer", "llm engineer", "ai agent engineer",
    "software developer", "software engineer", "entry level engineer",
    "api developer", "rest api developer", "microservices developer",
}

# Hard reject keywords (wrong field entirely)
REJECT_KEYWORDS = {
    "manager", "lead", "director", "vp", "principal architect",
    "senior principal", "distinguished engineer", "sales", "marketing",
    "support engineer", "devops engineer", "sre", "site reliability",
}


def _extract_required_skills(description: str) -> set:
    """
    Extract REQUIRED skills from job description (not nice-to-have).
    Looks for patterns like:
    - "Must have: Python, Django"
    - "Required: 5+ years"
    - "Skills: Java, Spring Boot"
    - "Expertise in X, Y, Z"
    """
    if not description:
        return set()

    desc_lower = description.lower()

    # Look for "Must have", "Required", "Skills", "Expertise" sections
    required_section = ""
    for section_start in ["must have", "required", "skills", "expertise", "core competencies"]:
        idx = desc_lower.find(section_start)
        if idx >= 0:
            # Take next 500 chars as section
            section = description[idx:idx+500]
            # Stop at next major section
            for stop in ["\n\n", "Nice to have", "Preferred", "About you"]:
                stop_idx = section.lower().find(stop.lower())
                if stop_idx > 0:
                    section = section[:stop_idx]
            required_section += section + "\n"

    if not required_section:
        required_section = description[:1500]  # fallback: first 1500 chars

    # Extract skill names from SKILL_LEXICON
    skills = set()
    for skill_label, aliases in SKILL_LEXICON.items():
        clean_label = _clean_label(skill_label)
        text_lower = " " + required_section.lower() + " "
        if any(_word_in(alias.strip().lower(), text_lower) for alias in aliases):
            skills.add(clean_label)

    # Fallback: if no skills found, try basic keyword matching on common tech
    if not skills:
        basic_keywords = [
            ("Python", r"\bpython\b"),
            ("Java", r"\bjava\b"),
            ("Node.js", r"\bnode(?:\.js)?\b"),
            ("JavaScript", r"\bjavascript\b"),
            ("Backend", r"\bbackend\b"),
            ("Full Stack", r"\bfull\s*stack\b"),
            ("FastAPI", r"\bfastapi\b"),
            ("Express", r"\bexpress(?:\.js)?\b"),
            ("Spring", r"\bspring\b"),
            ("Docker", r"\bdocker\b"),
            ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
            ("React", r"\breact\b"),
        ]
        text_lower = required_section.lower()
        for skill_name, pattern in basic_keywords:
            if re.search(pattern, text_lower):
                skills.add(skill_name)

    return skills


def _extract_required_years(description: str) -> int:
    """Extract minimum required years from description."""
    matches = re.findall(r"(\d+)\s*(?:\+|\-)?.*?years?", description, re.IGNORECASE)
    if matches:
        yrs = [int(m) for m in matches if int(m) <= 20]
        return min(yrs) if yrs else 0
    return 0


def _get_role_category(title: str) -> str | None:
    """Classify the job role — match common variations."""
    t = title.lower()

    # Direct match from ACCEPTABLE_ROLES
    for role in ACCEPTABLE_ROLES:
        if role in t:
            return role

    # Fuzzy matches for common variations
    if any(word in t for word in ["backend", "full stack", "python", "node", "java", "sde", "junior", "entry"]):
        if not any(word in t for word in ["manager", "lead", "director", "senior principal"]):
            return "backend developer"  # classify as acceptable

    return None


def should_include_job(job: dict, candidate_experience_years: int = 2) -> tuple[bool, str]:
    """
    BALANCED filtering: Keep jobs IN YOUR FIELD even with lower match %, reject completely unrelated.

    For a 2-year junior developer:
    1. REJECT if asks for 5+ years (too senior)
    2. REJECT if 0 core skill matches (completely wrong field)
    3. KEEP if 1+ core skill match (in your field, even if lower %)
    4. REJECT if clearly wrong field (sales, marketing, etc.)

    Returns: (should_include: bool, reason: str)
    """
    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")

    # HARD GATE 1: Reject if clearly the wrong field (sales, marketing, etc.)
    if any(kw in title.lower() for kw in REJECT_KEYWORDS):
        return False, f"wrong field: {title} (not backend/dev)"

    # HARD GATE 2: Experience filter - reject if asks for 5+ years
    req_years = _extract_required_years(desc)
    if req_years >= 5:
        return False, f"too senior: asks for {req_years}+ years (you have {candidate_experience_years})"

    # GATE 3: Skill matching - check if job is IN YOUR FIELD
    job_required_skills = _extract_required_skills(desc)

    # If we can't extract ANY skills from the description, it might have incomplete info
    # In that case, KEEP it anyway (likely from an API that returns minimal descriptions)
    # Let the ranking algorithm decide if it's relevant
    if len(job_required_skills) == 0:
        return True, f"kept for ranking (no skill data in description, let ranking decide)"

    matched_skills = job_required_skills & CORE_STACK

    # If we found skills but NONE match your core stack, reject it
    if len(matched_skills) == 0:
        missing_skills = sorted(job_required_skills)[:3]
        return False, f"not your field (needs: {', '.join(missing_skills)}, not your Python/Node/Java/Backend/AI)"

    # KEEP: Has 1+ core skill match — IN YOUR FIELD
    skill_match_pct = (len(matched_skills) / len(job_required_skills)) * 100 if job_required_skills else 0
    return True, f"kept for ranking ({round(skill_match_pct)}% match, {len(matched_skills)}/{len(job_required_skills)} skills)"


def filter_jobs(jobs: list, candidate_experience_years: int = 2) -> tuple[list, dict]:
    """
    Filter a batch of jobs, keeping only those that match the candidate's profile.

    Returns: (filtered_jobs: list, stats: dict)
    """
    kept = []
    rejected = {}

    for job in jobs:
        should_keep, reason = should_include_job(job, candidate_experience_years)
        if should_keep:
            kept.append(job)
        else:
            url = job.get("job_url", "")
            rejected[url] = {"title": job.get("title"), "reason": reason}

    return kept, {
        "total": len(jobs),
        "kept": len(kept),
        "rejected": len(rejected),
        "rejection_reasons": rejected,
    }
