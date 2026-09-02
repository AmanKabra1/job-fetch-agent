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
    """Generate resume bullets from project data."""
    bullets = []

    # Use description if available
    if project.get("description"):
        desc = project["description"]
        # Clean up description
        if desc and len(desc) > 10:
            bullets.append(desc)

    # Add tech stack info
    tech_stack = project.get("tech_stack", [])
    if tech_stack:
        tech_str = ", ".join(tech_stack[:5])  # Top 5 tech
        if project.get("description"):
            bullets.append(f"Tech Stack: {tech_str}")
        else:
            bullets.append(f"Built with: {tech_str}")

    # If no bullets yet, generate generic ones from tech/language
    if not bullets:
        language = project.get("language", "")
        if language:
            bullets.append(f"Project built with {language}")
        else:
            bullets.append("Production project")

    # Add GitHub link info
    github_url = project.get("github_url", "")
    if github_url:
        bullets.append(f"Source: {github_url}")

    return bullets[:4]  # Max 4 bullets per project


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
