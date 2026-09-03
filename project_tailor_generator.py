"""
Generate tailored project descriptions and bullet points for specific job descriptions.

When a project matches a job, this module creates:
- Tailored description (2-3 lines mentioning JD requirements)
- Tailored bullet points (4-5 bullets showing how project fits JD)
- Tech stack (preserved from original project)

This ensures NO GAPS when swapping project into resume.
"""

import re
from typing import Dict, List

def extract_jd_requirements(jd_text: str) -> Dict[str, List[str]]:
    """Extract key requirements, tools, and languages from job description."""
    if not jd_text:
        return {"tools": [], "languages": [], "roles": [], "patterns": []}

    jd_lower = jd_text.lower()

    # Key technologies
    tools = []
    tool_patterns = {
        "Python": ["python"],
        "Node.js": ["node.js", "nodejs"],
        "TypeScript": ["typescript", "ts"],
        "React": ["react"],
        "Angular": ["angular"],
        "FastAPI": ["fastapi"],
        "Express": ["express.js", "expressjs"],
        "NestJS": ["nestjs"],
        "PostgreSQL": ["postgresql", "postgres"],
        "MongoDB": ["mongodb"],
        "Docker": ["docker"],
        "Kubernetes": ["kubernetes", "k8s"],
        "AWS": ["aws", "amazon web services"],
        "GCP": ["gcp", "google cloud"],
        "Azure": ["azure"],
        "REST": ["rest api", "restful"],
        "GraphQL": ["graphql"],
        "LLM": ["llm", "large language model"],
        "AI": ["artificial intelligence"],
    }

    for tool, keywords in tool_patterns.items():
        if any(kw in jd_lower for kw in keywords):
            tools.append(tool)

    # Extract responsibilities/patterns
    patterns = []
    responsibility_keywords = [
        "design", "build", "develop", "implement", "create", "optimize",
        "manage", "scale", "maintain", "integrate", "deploy"
    ]
    for keyword in responsibility_keywords:
        if keyword in jd_lower:
            # Extract sentence with keyword
            for sentence in re.split(r'[.!?]', jd_text):
                if keyword in sentence.lower():
                    patterns.append(sentence.strip()[:80])
                    break

    return {
        "tools": list(set(tools)),
        "patterns": patterns[:3],  # Top 3 patterns
        "text": jd_text[:500]  # First 500 chars for context
    }


def generate_tailored_description(project_name: str, project_tech: List[str],
                                   jd_reqs: Dict) -> str:
    """Generate a 2-3 line description showing how project fits JD."""
    jd_tools = jd_reqs.get("tools", [])
    jd_patterns = jd_reqs.get("patterns", [])

    # Find overlapping tools
    overlap = [t for t in project_tech if t in jd_tools]

    if overlap:
        tools_str = ", ".join(overlap[:3])
        desc = f"{project_name} demonstrates expertise in {tools_str} with production-ready code."
    else:
        desc = f"{project_name} showcases full-stack development with scalable architecture and best practices."

    # Add pattern match if available
    if jd_patterns:
        pattern_keywords = " ".join(jd_patterns[:1]).lower()
        if "design" in pattern_keywords or "architect" in pattern_keywords:
            desc += " Experience in system design and optimization."
        elif "scale" in pattern_keywords:
            desc += " Proven ability to handle scalability and performance."
        elif "api" in pattern_keywords:
            desc += " RESTful API design and implementation expertise."

    return desc


def generate_tailored_bullets(project_name: str, project_desc: str, project_tech: List[str],
                              jd_reqs: Dict) -> List[str]:
    """Generate 4-5 tailored bullet points for project matching JD."""
    bullets = []
    jd_tools = jd_reqs.get("tools", [])
    jd_patterns = jd_reqs.get("patterns", [])

    # Bullet 1: Tech stack match
    overlap = [t for t in project_tech if t in jd_tools]
    if overlap:
        bullets.append(f"Built with {', '.join(overlap[:3])} — directly aligned with your stack requirements")
    else:
        bullets.append(f"Developed using {', '.join(project_tech[:3])} — full-stack implementation")

    # Bullet 2: Architecture/scalability
    if any(kw in jd_tools for kw in ["Docker", "Kubernetes", "AWS", "GCP"]):
        bullets.append("Containerized and deployed on cloud infrastructure for production reliability")
    else:
        bullets.append("Production-grade code with modular architecture and clean code principles")

    # Bullet 3: Feature/functionality
    if "API" in jd_tools or "REST" in jd_tools or "GraphQL" in jd_tools:
        bullets.append("Designed RESTful/GraphQL APIs with proper authentication, validation, and error handling")
    elif "React" in jd_tools or "Angular" in jd_tools:
        bullets.append("Built responsive frontend with modern UI/UX patterns and performance optimization")
    elif "Database" in str(jd_tools) or "PostgreSQL" in jd_tools or "MongoDB" in jd_tools:
        bullets.append("Engineered robust database schemas with optimizations and query performance tuning")
    elif "LLM" in jd_tools or "AI" in jd_tools:
        bullets.append("Integrated AI/LLM capabilities with prompt engineering and vector search optimization")
    else:
        bullets.append("Implemented core features with comprehensive testing and documentation")

    # Bullet 4: Quality/DevOps
    if "CI/CD" in jd_tools or "GitHub Actions" in jd_tools or "Jenkins" in jd_tools:
        bullets.append("Set up CI/CD pipelines with automated testing and deployment workflows")
    elif "Docker" in jd_tools:
        bullets.append("Configured Docker containerization and orchestration for consistent deployments")
    else:
        bullets.append("Maintained code quality through testing, code reviews, and performance monitoring")

    # Bullet 5: Impact/metrics (only if space)
    if len(jd_patterns) > 1 or "scale" in str(jd_patterns).lower():
        bullets.append("Achieved 30%+ performance improvement through optimization and efficient algorithms")
    else:
        bullets.append("Delivered production-ready features with 99.9% uptime and minimal technical debt")

    return bullets[:5]  # Ensure 5 max


def tailor_project_for_jd(project: Dict, jd_text: str) -> Dict:
    """
    Main function: tailor project for specific job description.

    Input project dict should have: name, tech_stack (list), description
    Returns enhanced project with: tailored_description, tailored_bullets
    """
    jd_reqs = extract_jd_requirements(jd_text)

    tech_list = project.get("tech_stack", [])
    if isinstance(tech_list, str):
        tech_list = [t.strip() for t in tech_list.split(",")]

    tailored = project.copy()
    tailored["tailored_description"] = generate_tailored_description(
        project.get("name", "Project"),
        tech_list,
        jd_reqs
    )
    tailored["tailored_bullets"] = generate_tailored_bullets(
        project.get("name", "Project"),
        project.get("description", ""),
        tech_list,
        jd_reqs
    )

    return tailored
