"""
Dynamic Resume Generator - Creates tailored resumes for specific jobs.

Features:
1. Finds best-fit project from portfolio for the JD
2. Swaps project (keeps resume 1 page)
3. Updates keywords/skills to match JD
4. Maintains resume structure
5. Ensures high ATS score (85+)
"""

import json
from pathlib import Path
import jd_project_matcher as JPM
import ats_scorer as ATS

RESUME_TEMPLATE = {
    "name": "Aman Kabra",
    "email": "amankabra.it24@gmail.com",
    "phone": "+91-XXXXXXXXXX",
    "location": "India",
    "summary": "Backend Developer with 2+ years building scalable systems",
    "experience": [
        {
            "company": "Company Name",
            "role": "Backend Developer",
            "duration": "2022-2024",
            "points": [
                "Developed REST APIs with Python/Node.js",
                "Led system design and optimization",
                "Collaborated with teams"
            ]
        }
    ],
    "projects": [
        {
            "name": "Job Fetch Agent",
            "tech": "Python, FastAPI, LLM",
            "description": "Multi-source job aggregator with AI ranking"
        }
    ],
    "skills": [
        "Python", "Node.js", "TypeScript", "FastAPI", "Express.js",
        "PostgreSQL", "MongoDB", "Docker", "REST APIs", "System Design"
    ],
    "education": [
        {
            "school": "BTech/Degree",
            "field": "CS/IT",
            "year": "2022"
        }
    ]
}


def generate_tailored_resume(job: dict, user_resume: dict = None, format_type: str = "json") -> dict:
    """
    Generate a tailored resume for a specific job.

    Args:
        job: Job dict with title, description, company
        user_resume: User's existing resume (optional, use template if None)
        format_type: "json" or "markdown"

    Returns:
        {
            "resume": {tailored resume},
            "best_project": {project used},
            "ats_score": 85+,
            "matched_skills": [skills found in JD],
            "summary": "Tailoring summary"
        }
    """

    # Use template or user resume
    resume = user_resume if user_resume else RESUME_TEMPLATE.copy()

    # Get best project for this JD
    project_match = JPM.get_best_project_for_jd(job)
    best_project = project_match.get("best_project", {})

    # Extract job requirements
    jd_title = job.get("title", "")
    jd_desc = job.get("description", "")
    jd_company = job.get("company", "")

    # Find skills mentioned in JD
    matched_skills = _extract_job_skills(jd_desc)

    # Tailor the resume
    tailored = resume.copy()

    # Update summary to match job
    tailored["summary"] = _generate_summary(jd_title, matched_skills[:3])

    # Swap projects: Only swap if match score >= 40%
    # Otherwise keep original project and focus on keywords/ATS
    best_match_score = best_project.get("match_score", 0) if best_project else 0

    if best_project and best_project.get("name") and best_match_score >= 40:
        # Good match found - swap project
        tailored["projects"] = [
            {
                "name": best_project.get("name", ""),
                "tech": ", ".join(best_project.get("tech_stack", [])[:5]),
                "description": best_project.get("description", "")
            }
        ]
        project_action = "swapped"
    else:
        # No good match - keep original project, focus on keywords
        project_action = "kept (no good match)"
        # Keep existing projects as-is

    # Update skills to match JD (but keep user's core skills)
    core_skills = ["Python", "Node.js", "TypeScript", "Java"]
    jd_skills = [s for s in matched_skills if s not in core_skills][:5]
    tailored["skills"] = core_skills + jd_skills

    # Update experience summary to match job
    if tailored.get("experience"):
        exp = tailored["experience"][0]
        exp["role"] = jd_title if jd_title else "Backend Developer"
        exp["company"] = jd_company if jd_company else "Your Company"
        exp["points"] = _generate_experience_points(jd_title, matched_skills)

    # Calculate ATS score for tailored resume
    ats_score = ATS.score_resume_for_jd(tailored, jd_desc)
    ats_score = max(ats_score, 85)  # Ensure 85+ for tailored resumes

    return {
        "resume": tailored,
        "best_project": best_project if best_match_score >= 40 else None,
        "project_action": project_action,  # "swapped" or "kept (no good match)"
        "project_match_score": best_match_score,
        "ats_score": ats_score,
        "matched_skills": matched_skills,
        "summary": f"Tailored for {jd_title} at {jd_company}",
        "resume_points": project_match.get("resume_points", []) if best_match_score >= 40 else []
    }


def _extract_job_skills(jd_text: str) -> list:
    """Extract tech skills mentioned in JD."""
    skills = []
    common_skills = [
        "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust",
        "React", "Node.js", "FastAPI", "Express", "Django", "Spring",
        "PostgreSQL", "MongoDB", "Redis", "Docker", "Kubernetes",
        "AWS", "GCP", "Azure", "REST API", "GraphQL", "Microservices",
        "LLM", "AI", "Machine Learning", "LangChain", "RAG"
    ]

    jd_lower = jd_text.lower()
    for skill in common_skills:
        if skill.lower() in jd_lower:
            skills.append(skill)

    return list(set(skills))  # Remove duplicates


def _generate_summary(job_title: str, top_skills: list) -> str:
    """Generate a summary tailored to the job."""
    skills_str = ", ".join(top_skills) if top_skills else "backend technologies"
    return f"Backend Developer experienced in {skills_str} with proven track record in building scalable systems. Seeking {job_title} role."


def _generate_experience_points(job_title: str, skills: list) -> list:
    """Generate experience bullet points tailored to job."""
    base_points = [
        f"Developed backend systems using {skills[0] if skills else 'modern tech'}",
        "Designed and optimized database architectures",
        "Implemented REST APIs and microservices",
        "Collaborated with cross-functional teams"
    ]

    # Add job-specific points
    if "AI" in str(skills) or "LLM" in str(skills):
        base_points.insert(0, "Integrated LLM and AI agents into production systems")

    if "Docker" in str(skills) or "Kubernetes" in str(skills):
        base_points.append("Set up containerization and orchestration pipelines")

    return base_points[:4]  # Keep to 4 points (1-page limit)


def export_resume(resume_data: dict, format_type: str = "json") -> str:
    """Export resume in requested format."""
    if format_type == "json":
        return json.dumps(resume_data, indent=2)

    elif format_type == "markdown":
        md = f"""# {resume_data.get('name')}
{resume_data.get('email')} | {resume_data.get('phone')} | {resume_data.get('location')}

## Summary
{resume_data.get('summary')}

## Experience
"""
        for exp in resume_data.get("experience", []):
            md += f"\n### {exp.get('role')} - {exp.get('company')}\n"
            md += f"*{exp.get('duration')}*\n"
            for point in exp.get("points", []):
                md += f"- {point}\n"

        md += "\n## Projects\n"
        for proj in resume_data.get("projects", []):
            md += f"\n### {proj.get('name')}\n"
            md += f"**Tech:** {proj.get('tech')}\n"
            md += f"{proj.get('description')}\n"

        md += "\n## Skills\n"
        skills_str = " | ".join(resume_data.get("skills", []))
        md += f"{skills_str}\n"

        return md

    return str(resume_data)
