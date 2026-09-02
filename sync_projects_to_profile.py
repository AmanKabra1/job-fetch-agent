"""
Sync projects from data/projects.json to resume_profile.py with proper resume format.

This ensures all GitHub projects are available for job matching and resume swapping.
Runs after projects_manager fetches new projects every 2 weeks.
"""

import json
import re
from pathlib import Path
from datetime import datetime

PROJECTS_FILE = Path(__file__).parent / "data" / "projects.json"
PROFILE_FILE = Path(__file__).parent / "resume_profile.py"


def generate_project_bullets(project: dict) -> list:
    """Generate detailed resume bullets from project data (Shaadi-style)."""
    bullets = []
    name = project.get("name", "")
    tech_stack = project.get("tech_stack", [])
    description = (project.get("description") or "").strip()
    language = project.get("language", "")

    # Bullet 1: Main description or project summary
    if description and len(description) > 15:
        bullets.append(description)
    else:
        # Generate from tech stack if no description
        if tech_stack:
            tech_summary = ", ".join(tech_stack[:4])
            bullets.append(f"Production {name} project built with {tech_summary}")
        elif language:
            bullets.append(f"{name} project implemented in {language}")
        else:
            bullets.append(f"Full-stack {name} project")

    # Bullet 2: Technical architecture/implementation details
    if tech_stack and len(tech_stack) > 0:
        if len(tech_stack) <= 3:
            tech_str = " and ".join(tech_stack)
            bullets.append(f"Implemented using {tech_str} for robust architecture")
        else:
            core_tech = ", ".join(tech_stack[:3])
            other_tech = ", ".join(tech_stack[3:])
            bullets.append(
                f"Built with {core_tech}; leveraged {other_tech} "
                "for enhanced functionality and scalability"
            )

    # Bullet 3: Performance/Production focus
    if description and "production" in description.lower():
        bullets.append(
            "Deployed as production-ready system with focus on reliability, "
            "performance, and maintainability"
        )
    elif "ai" in str(tech_stack).lower() or "machine learning" in str(tech_stack).lower():
        bullets.append(
            "Integrated advanced AI/ML capabilities for intelligent automation "
            "and data-driven decision making"
        )
    elif any(db in str(tech_stack).lower() for db in ["postgresql", "mongodb", "mysql", "redis"]):
        bullets.append(
            "Designed database architecture with optimization for query performance "
            "and data consistency at scale"
        )
    else:
        bullets.append(
            "Implemented best practices for code quality, testing, and continuous deployment"
        )

    # Bullet 4: Achievement/Impact statement
    if description and any(word in description.lower() for word in
                           ["api", "microservice", "service", "platform", "app"]):
        bullets.append(
            "Delivered production-grade solution demonstrating full-stack capabilities "
            "and professional software engineering practices"
        )
    else:
        bullets.append(
            "Showcases expertise in full-stack development with clean architecture "
            "and production deployment experience"
        )

    return bullets[:4]  # Max 4 bullets per project (like Shaadi)


def portfolio_to_resume_format(project: dict) -> dict:
    """Convert portfolio project to resume profile format."""
    tech_stack = project.get("tech_stack", [])
    tech_str = ", ".join(tech_stack) if tech_stack else project.get("language", "")

    return {
        "name": project.get("name", ""),
        "stack": tech_str if tech_str else "Full Stack",
        "link": project.get("github_url", ""),
        "bullets": generate_project_bullets(project)
    }


def load_portfolio_projects() -> list:
    """Load projects from data/projects.json."""
    if not PROJECTS_FILE.exists():
        print("! No projects.json found")
        return []

    try:
        with open(PROJECTS_FILE, "r") as f:
            data = json.load(f)
        return data.get("projects", [])
    except Exception as e:
        print(f"! Error loading projects: {e}")
        return []


def extract_current_projects(profile_content: str) -> dict:
    """Extract PROJECTS dict from resume_profile.py."""
    # Find PROJECTS = [ ... ]
    match = re.search(r'PROJECTS = \[(.*?)\n\]', profile_content, re.DOTALL)
    if not match:
        return {}
    return match.group(1)


def generate_projects_dict(projects: list) -> str:
    """Generate Python dict for PROJECTS variable."""
    lines = ["PROJECTS = ["]

    for proj in projects:
        if not proj.get("name"):
            continue

        stack = proj.get("stack", "")
        link = proj.get("link", "")
        bullets = proj.get("bullets", [])

        # Project entry
        lines.append("    {")
        lines.append(f'        "name": "{proj["name"]}",')
        lines.append(f'        "stack": "{stack}",')
        lines.append(f'        "link": "{link}",')
        lines.append('        "bullets": [')

        # Bullets
        for bullet in bullets:
            # Escape quotes
            bullet_clean = bullet.replace('"', '\\"')
            lines.append(f'            "{bullet_clean}",')

        lines.append("        ],")
        lines.append("    },")

    lines.append("]")
    return "\n".join(lines)


def update_profile_projects(new_projects_dict: str) -> bool:
    """Update PROJECTS in resume_profile.py."""
    if not PROFILE_FILE.exists():
        print("! resume_profile.py not found")
        return False

    try:
        with open(PROFILE_FILE, "r") as f:
            content = f.read()

        # Replace PROJECTS section
        new_content = re.sub(
            r'PROJECTS = \[.*?\n\]',
            new_projects_dict,
            content,
            flags=re.DOTALL
        )

        with open(PROFILE_FILE, "w") as f:
            f.write(new_content)

        return True
    except Exception as e:
        print(f"! Error updating profile: {e}")
        return False


def sync_projects():
    """Main sync function."""
    print("\n[*] Syncing projects to resume_profile.py...")

    # Load portfolio projects
    portfolio_projects = load_portfolio_projects()
    if not portfolio_projects:
        print("! No projects found in data/projects.json")
        return False

    print(f"  Loaded {len(portfolio_projects)} projects from portfolio")

    # Convert to resume format
    resume_projects = [portfolio_to_resume_format(p) for p in portfolio_projects]
    resume_projects = [p for p in resume_projects if p.get("name")]

    print(f"  Converted {len(resume_projects)} projects to resume format")

    # Generate new PROJECTS dict
    new_projects_dict = generate_projects_dict(resume_projects)

    # Update profile
    if update_profile_projects(new_projects_dict):
        print(f"[+] Updated {len(resume_projects)} projects in resume_profile.py")
        return True
    else:
        print("[-] Failed to update resume_profile.py")
        return False


if __name__ == "__main__":
    import sys
    success = sync_projects()
    sys.exit(0 if success else 1)
