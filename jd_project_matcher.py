"""
JD Project Matcher - Finds the BEST project from portfolio for a specific job.

Uses Groq to intelligently match job description against user's projects.
Returns: Best project + match score (0-100)
"""

import os
import json
import projects_manager as PM

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

groq_client = None
if GROQ_AVAILABLE:
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        groq_client = Groq(api_key=groq_key)


def get_best_project_for_jd(job: dict, top_n: int = 3) -> dict:
    """
    Find the BEST project from Aman's portfolio that matches this JD.

    Args:
        job: Job dict with title, description, company, etc.
        top_n: Return top N matching projects

    Returns:
        {
            "best_project": {name, description, tech_stack, match_score, reason},
            "alternatives": [project1, project2],
            "recommendation": "Why this project fits"
        }
    """
    # Load user's projects
    portfolio = PM.load_projects()
    projects = portfolio.get("projects", [])

    if not projects:
        return {
            "error": "No projects in portfolio",
            "best_project": None,
            "alternatives": []
        }

    title = job.get("title", "")
    description = job.get("description", "")
    company = job.get("company", "")

    if not description or len(description) < 100:
        # Fallback: return most recent project
        best = max(projects, key=lambda p: p.get("added_date", ""), default={})
        return {
            "best_project": {**best, "match_score": 50},
            "alternatives": [],
            "recommendation": "Limited job data; returning most recent project"
        }

    prompt = f"""Analyze this job and find the BEST project from Aman's portfolio to highlight.

JOB:
Title: {title}
Company: {company}
Description (first 1500 chars):
{description[:1500]}

PROJECTS:
{json.dumps(projects[:10], indent=2)}  # Top 10 projects

For EACH project, score how well it matches this JD (0-100):
- Does project use skills they need? (40%)
- Is project relevant to role type? (30%)
- Does it showcase required experience? (30%)

Return ONLY JSON:
{{
  "best_project_name": "name of best project",
  "match_score": 0-100,
  "why": "1-2 sentences why this project is perfect for this job",
  "recommendations": [
    "What to emphasize from this project in resume",
    "How to connect it to this role"
  ]
}}"""

    try:
        if not groq_client:
            # Fallback: simple heuristic matching
            scored = _score_projects_heuristic(projects, description)
        else:
            message = groq_client.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
            )

            response_text = message.choices[0].message.content.strip()

            # Extract JSON
            if response_text.startswith("{"):
                result = json.loads(response_text)
            else:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(response_text[start:end])
                else:
                    scored = _score_projects_heuristic(projects, description)
                    result = None

            if result:
                # Find the project in portfolio
                best_name = result.get("best_project_name", "")
                best_project = next((p for p in projects if p.get("name") == best_name), None)

                if best_project:
                    best_project["match_score"] = result.get("match_score", 70)

                    # Get alternatives
                    scored = _score_projects_heuristic(projects, description)
                    alternatives = [p for p in scored[:top_n-1] if p.get("name") != best_name]

                    return {
                        "best_project": best_project,
                        "alternatives": alternatives,
                        "recommendation": result.get("why", "Good fit for this role"),
                        "resume_points": result.get("recommendations", [])
                    }

        # Fallback: heuristic scoring
        if not groq_client or not result:
            scored = _score_projects_heuristic(projects, description)
            best = scored[0] if scored else {}

            return {
                "best_project": best,
                "alternatives": scored[1:top_n],
                "recommendation": f"Project '{best.get('name')}' matches {best.get('score', 0)}% of job requirements",
                "resume_points": []
            }

    except Exception as e:
        # Fallback to heuristic
        scored = _score_projects_heuristic(projects, description)
        best = scored[0] if scored else {}

        return {
            "best_project": best,
            "alternatives": scored[1:top_n],
            "recommendation": f"Analysis error (heuristic match): {str(e)[:50]}",
            "resume_points": []
        }


def _score_projects_heuristic(projects: list, jd_text: str) -> list:
    """
    Score projects based on skill/tech overlap with JD (no API needed).

    Returns: Projects sorted by score (highest first)
    """
    jd_lower = jd_text.lower()
    scored = []

    for project in projects:
        score = 0
        tech_stack = project.get("tech_stack", [])

        # Score based on tech overlap
        for skill in tech_stack:
            if skill.lower() in jd_lower:
                score += 20

        # Bonus for relevant project names
        name = project.get("name", "").lower()
        if any(keyword in name for keyword in ["api", "backend", "fullstack", "agent", "ai"]):
            if any(keyword in jd_lower for keyword in ["api", "backend", "fullstack", "agent", "ai"]):
                score += 15

        # Bonus for description match
        desc = project.get("description", "").lower()
        if any(keyword in desc for keyword in ["api", "backend", "agent", "database", "auth"]):
            score += 10

        scored.append({
            **project,
            "match_score": min(score, 100)
        })

    # Sort by score
    scored.sort(key=lambda p: p.get("match_score", 0), reverse=True)
    return scored
