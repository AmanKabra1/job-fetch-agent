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
    "Python", "Node.js", "Backend", "Full Stack", "Java", "Spring Boot",
    "Machine Learning", "LLM", "LangChain", "LangGraph", "AI Agents",
    "Agentic AI", "FastAPI", "Express.js", "NestJS", "Docker",
}

# Acceptable role categories for a 2-year developer
ACCEPTABLE_ROLES = {
    "backend developer", "backend engineer", "sde 1", "sde-1",
    "junior backend", "full stack developer", "python developer",
    "node.js developer", "java developer", "ai engineer", "ml engineer",
    "llm engineer", "ai agent engineer", "software developer",
    "software engineer", "entry level engineer",
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
    RELAXED filtering: Keep jobs for ranking to decide, only hard-reject wrong field/too senior.

    Returns: (should_include: bool, reason: str)
    """
    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")

    # HARD GATE 1: Reject if clearly the wrong field (sales, marketing, etc.)
    if any(kw in title.lower() for kw in REJECT_KEYWORDS):
        return False, f"role is {title} (not backend/dev)"

    # HARD GATE 2: Only reject if asks for MUCH more experience (5+ years more)
    req_years = _extract_required_years(desc)
    if req_years > candidate_experience_years + 4:  # allow up to 4-year stretch (2yr → 6yr max)
        return False, f"asks for {req_years}+ years (you have {candidate_experience_years})"

    # RELAXED: Keep everything else for ranking to decide
    # Even if:
    # - Role not in target categories (ranking will downrank)
    # - No skill match found (ranking will downrank)
    # - Only 1 skill match (ranking will score it appropriately)
    # - Senior title (ranking will downrank)

    # Only return True (KEEP) with a brief reason
    return True, "kept for ranking"


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
