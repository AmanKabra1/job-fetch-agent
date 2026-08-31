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
    Smart project scoring - heavily favors EXACT JD matches.

    Scoring logic:
    1. Count ALL matching tech terms (primary differentiator)
    2. Bonus for description quality & production keywords
    3. Penalize irrelevant tech stacks
    4. Return clearly ranked projects

    Returns: Projects sorted by score (highest first)
    """
    if not jd_text or jd_text == "None":
        return projects

    jd_lower = str(jd_text).lower()
    scored = []

    # Tech keywords with importance weights
    tech_keywords = [
        "python", "javascript", "typescript", "java", "node.js", "go", "rust", "php",
        "fastapi", "flask", "django", "express", "nestjs", "spring", "rails",
        "react", "angular", "vue", "svelte",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "docker", "kubernetes", "aws", "azure", "gcp",
        "rest", "graphql", "grpc", "websocket",
        "backend", "frontend", "fullstack", "api", "microservice", "database",
        "ai", "llm", "ml", "langchain", "langgraph", "groq",
        "testing", "pytest", "jest", "mocha", "junit"
    ]

    # Extract JD requirements
    jd_tech_terms = [kw for kw in tech_keywords if kw in jd_lower]

    # Identify job type
    job_type = "unknown"
    if any(term in jd_lower for term in ["backend", "api", "microservice", "node", "python", "java"]):
        job_type = "backend"
    elif any(term in jd_lower for term in ["frontend", "react", "angular", "ui", "ux"]):
        job_type = "frontend"
    elif any(term in jd_lower for term in ["fullstack", "full stack", "both"]):
        job_type = "fullstack"

    for project in projects:
        tech_stack = [t.lower() for t in (project.get("tech_stack", []) or [])]
        desc = (project.get("description", "") or "").lower()
        name = project.get("name", "").lower()

        score = 0

        # 1. TECH STACK MATCHING (60 points max) - PRIMARY DIFFERENTIATOR
        # Count how many JD tech terms are in project tech stack
        tech_count = sum(1 for jd_tech in jd_tech_terms if any(jd_tech in tech for tech in tech_stack))
        tech_score = min(tech_count * 15, 60)  # Scale up: each match is worth 15 pts

        # BONUS: More diverse tech stack = better project
        tech_diversity = len([t for t in tech_stack if t in jd_tech_terms])
        diversity_bonus = min(tech_diversity * 5, 15)

        # PENALTY: Irrelevant tech (like "Testing" for non-QA roles)
        irrelevant_techs = ["testing", "test", "jest", "pytest", "qa", "uat"]
        has_irrelevant = sum(1 for tech in tech_stack if any(irr in tech for irr in irrelevant_techs))
        if job_type != "backend" and has_irrelevant:
            tech_score = max(0, tech_score - 20)  # Penalize if not QA role

        # 2. DESCRIPTION QUALITY (25 points max)
        desc_score = 0
        if len(desc) > 100:
            desc_score += 5

        # Description mentions tech from JD
        desc_tech_matches = sum(1 for jd_tech in jd_tech_terms if jd_tech in desc)
        desc_score += min(desc_tech_matches * 3, 10)

        # Description has production quality keywords
        prod_keywords = ["production", "scalable", "optimize", "integrate", "enterprise", "framework", "api", "real-time", "microservices"]
        desc_score += sum(2 for kw in prod_keywords if kw in desc)

        desc_score = min(desc_score, 25)

        # 3. RECENCY (15 points max)
        updated = project.get("updated", "")
        recency_score = 15 if updated else 0

        total_score = tech_score + diversity_bonus + desc_score + recency_score
        final_score = min(total_score, 100)

        scored.append({
            **project,
            "match_score": final_score,
            "_debug": f"tech:{tech_score} div:{diversity_bonus} desc:{desc_score} rec:{recency_score} = {final_score}"
        })

    # Sort by score (highest first), then by tech diversity as tiebreaker
    scored.sort(
        key=lambda p: (
            p.get("match_score", 0),
            len([t for t in (p.get("tech_stack", []) or []) if t.lower() in [kw for kw in jd_tech_terms]])
        ),
        reverse=True
    )

    return scored
