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

    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    company = str(job.get("company", ""))

    if not description or description == "None" or len(description) < 100:
        # Fallback: return most recent project
        best = max(projects, key=lambda p: p.get("added_date", ""), default={})
        return {
            "best_project": {**best, "match_score": 50},
            "alternatives": [],
            "recommendation": "Limited job data; returning most recent project"
        }

    prompt = f"""Analyze this job and find the ABSOLUTE BEST project from ALL {len(projects)} projects in Aman's portfolio.

JOB:
Title: {title}
Company: {company}
Description (first 1500 chars):
{description[:1500]}

ALL PROJECTS IN PORTFOLIO ({len(projects)} total):
{json.dumps(projects, indent=2)}

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
            # Fallback: comprehensive heuristic matching
            print(f"  📊 Project matcher: Using HEURISTIC (Groq not available)", flush=True)
            scored = _score_projects_heuristic(projects, description)
        else:
            print(f"  🤖 Project matcher: Using GROQ AI (analyzing {len(projects)} projects)", flush=True)
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
    Score projects comprehensively based on tech/skill/description overlap with JD.
    Ranks by: tech match (40%), role relevance (30%), description match (20%), recency (10%)

    Returns: Projects sorted by score (highest first)
    """
    if not jd_text or jd_text == "None":
        return projects  # No JD, return as-is

    jd_lower = str(jd_text).lower()
    scored = []

    # Extract key tech terms from JD
    tech_keywords = ["python", "javascript", "typescript", "java", "node.js", "fastapi",
                     "django", "nestjs", "react", "angular", "postgresql", "mongodb",
                     "docker", "kubernetes", "aws", "backend", "frontend", "fullstack",
                     "api", "rest", "graphql", "microservices", "ai", "llm", "ml"]

    jd_tech_terms = [kw for kw in tech_keywords if kw in jd_lower]

    for idx, project in enumerate(projects):
        score = 0
        tech_stack = project.get("tech_stack", [])
        name = project.get("name", "").lower()
        desc = project.get("description", "").lower() if project.get("description") else ""

        # 1. TECH STACK MATCH (40 points max) - CRITICAL
        tech_matches = 0
        for skill in tech_stack:
            skill_lower = skill.lower()
            for tech in jd_tech_terms:
                if tech.lower() in skill_lower:
                    tech_matches += 1
                    break
        tech_score = min(tech_matches * 10, 40)  # Max 40 points

        # 2. ROLE RELEVANCE (30 points max) - IMPORTANT
        # Match role keywords ONLY if they appear in description
        role_keywords = ["backend", "fullstack", "frontend", "api", "microservice", "database", "agent", "ai", "rest"]
        role_score = 0
        for keyword in role_keywords:
            if keyword in jd_lower and keyword in desc:
                role_score += 10
        role_score = min(role_score, 30)

        # 3. DESCRIPTION QUALITY (20 points max) - HELPS DIFFERENTIATE
        desc_quality = 0
        if len(desc) > 100:
            desc_quality += 5  # Has substantial description
        desc_tech_matches = sum(1 for kw in jd_tech_terms if kw.lower() in desc)
        desc_quality += min(desc_tech_matches * 3, 10)  # Points for tech match in desc
        if any(kw in desc for kw in ["production", "scalable", "optimize", "integrate", "enterprise", "framework"]):
            desc_quality += 5
        desc_score = min(desc_quality, 20)

        # 4. RECENCY BONUS (10 points max)
        updated = project.get("updated", "")
        recency_score = 10 if updated else 0

        total_score = tech_score + role_score + desc_score + recency_score

        scored.append({
            **project,
            "match_score": min(total_score, 100),
            "_debug": f"name:{name} tech:{tech_score} role:{role_score} desc:{desc_score} rec:{recency_score} total:{min(total_score,100)}"
        })

    # Sort by score, then by recency for ties
    scored.sort(key=lambda p: (p.get("match_score", 0), p.get("updated", "")), reverse=True)
    return scored
