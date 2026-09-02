"""
Sync projects from data/projects.json to resume_profile.py with proper resume format.

This ensures all GitHub projects are available for job matching and resume swapping.
Runs after projects_manager fetches new projects every 2 weeks.
Uses Groq AI to generate detailed, achievement-focused project bullets (Shaadi-style).
"""

import json
import re
from pathlib import Path
from datetime import datetime
import os

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

PROJECTS_FILE = Path(__file__).parent / "data" / "projects.json"
PROFILE_FILE = Path(__file__).parent / "resume_profile.py"

# Initialize Groq for AI bullet generation
groq_client = None
if GROQ_AVAILABLE:
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        groq_client = Groq(api_key=groq_key)


def generate_ai_bullets(project: dict) -> list:
    """Generate detailed Shaadi-style bullets using Groq AI."""
    if not groq_client:
        return generate_heuristic_bullets(project)

    name = project.get("name", "")
    description = (project.get("description") or "").strip()
    tech_stack = project.get("tech_stack", [])
    language = project.get("language", "")

    tech_str = ", ".join(tech_stack) if tech_stack else language or "Full Stack"

    prompt = f"""Generate 4 detailed, achievement-focused resume bullets for this GitHub project (like the Shaadi Vidhaan example).

PROJECT:
- Name: {name}
- Tech Stack: {tech_str}
- Description: {description if description else "No description available"}

EXAMPLE (Shaadi Vidhaan project format):
1. "Independently built a production full-stack platform for Indian wedding & cultural event planning, covering 28+ states, 7 event types, and 50+ seeded rituals with ceremony details."
2. "Engineered a NestJS REST API with TypeORM + MySQL, JWT auth with role separation (user vs. organizer), Swagger/OpenAPI docs, validation pipes, and CORS configuration."
3. "Developed Angular 17 frontend using Signals, standalone components, lazy-loaded routes, and RxJS Map-based response caching for improved load performance."
4. "Containerized backend with Docker and configured CI/CD via GitHub Actions, enabling auto-redeploy on Render (backend) and Vercel (frontend) on every push."

Create 4 bullets for {name}:
- Bullet 1: What the project is (specific use case, features, scope)
- Bullet 2: Technical implementation (architecture, patterns, tech details)
- Bullet 3: Additional technical achievements (optimization, features, integrations)
- Bullet 4: Deployment/production focus (infrastructure, CI/CD, scalability)

Return ONLY the 4 bullets as a JSON array of strings, no other text:
["bullet1", "bullet2", "bullet3", "bullet4"]"""

    try:
        response = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )

        result_text = response.choices[0].message.content.strip()
        # Parse JSON array
        bullets = json.loads(result_text)
        if isinstance(bullets, list) and len(bullets) >= 4:
            return bullets[:4]
    except Exception as e:
        print(f"  [!] AI bullet generation failed for {name}: {str(e)[:40]}", flush=True)

    # Fallback to heuristic if AI fails
    return generate_heuristic_bullets(project)


def generate_heuristic_bullets(project: dict) -> list:
    """Fallback: Generate detailed bullets heuristically when AI unavailable."""
    bullets = []
    name = project.get("name", "")
    tech_stack = project.get("tech_stack", [])
    description = (project.get("description") or "").strip()
    language = project.get("language", "")

    # Bullet 1: LONG Main description or project summary (4-5 detailed lines)
    if description and len(description) > 40:
        # Description is already rich from GitHub - use it as-is (often 4-5 sentences)
        bullets.append(description)
    else:
        # Generate detailed long description (4-5 sentences)
        if tech_stack:
            core_stack = ", ".join(tech_stack[:2])
            other_stack = ", ".join(tech_stack[2:4]) if len(tech_stack) > 2 else ""

            if other_stack:
                bullets.append(
                    f"Independently developed {name} as a comprehensive solution leveraging {core_stack} "
                    f"for core functionality, with additional integration of {other_stack} to enhance capabilities "
                    f"and deliver production-grade features. The project demonstrates professional-level engineering with emphasis on "
                    f"scalability, reliability, and maintainability. Showcases expertise in full-stack architecture design and implementation "
                    f"of complex systems with multiple technology layers."
                )
            else:
                bullets.append(
                    f"Independently developed {name} leveraging {core_stack} as primary technology stack "
                    f"to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates "
                    f"expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. "
                    f"Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability."
                )
        elif language:
            bullets.append(
                f"Engineered {name} application in {language} emphasizing clean code architecture, "
                f"professional implementation standards, and production-ready quality. The project demonstrates expertise in building "
                f"robust systems with proper error handling, testing, and maintainability. Showcases ability to deliver complete solutions "
                f"that follow industry best practices and support long-term scalability and evolution."
            )
        else:
            bullets.append(
                f"Developed {name} as a complete end-to-end project showcasing comprehensive full-stack capabilities "
                f"and professional software engineering practices. The implementation demonstrates expertise in system design, architecture patterns, "
                f"and production deployment. Project reflects commitment to code quality, user experience, and maintainable solutions that scale effectively."
            )

    # Bullet 2: Technical architecture
    if tech_stack:
        if len(tech_stack) <= 2:
            tech_str = " with ".join(tech_stack)
            bullets.append(
                f"Implemented core architecture using {tech_str} "
                f"ensuring scalable and maintainable codebase"
            )
        else:
            core = ", ".join(tech_stack[:2])
            rest = ", ".join(tech_stack[2:])
            bullets.append(
                f"Engineered backend with {core}; integrated {rest} "
                f"for enhanced functionality, performance, and production reliability"
            )
    else:
        bullets.append(
            f"Implemented robust architecture following best practices "
            f"for code quality and system design"
        )

    # Bullet 3: Specialized features based on tech
    if any(ai in str(tech_stack).lower() for ai in ["ai", "machine learning", "langgraph", "langchain"]):
        bullets.append(
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, "
            "retrieval-augmented generation, and intelligent automation for complex workflows"
        )
    elif any(db in str(tech_stack).lower() for db in ["postgresql", "mongodb", "mysql"]):
        bullets.append(
            "Designed optimized database schema with efficient queries, transactions, "
            "and data consistency patterns for handling scale and concurrency"
        )
    elif any(web in str(tech_stack).lower() for web in ["react", "angular", "vue", "next"]):
        bullets.append(
            "Developed responsive frontend with modern component architecture, "
            "state management, and performance optimization for optimal user experience"
        )
    else:
        bullets.append(
            "Implemented key features including API design, data persistence, "
            "error handling, and comprehensive testing for production reliability"
        )

    # Bullet 4: Deployment and DevOps
    if any(deploy in str(tech_stack).lower() for deploy in ["docker", "kubernetes", "github actions", "ci/cd"]):
        bullets.append(
            "Containerized application with Docker and configured automated CI/CD pipelines "
            "using GitHub Actions for seamless testing, building, and deployment to production"
        )
    else:
        bullets.append(
            "Deployed as production-ready system with focus on reliability, scalability, "
            "and maintainability; demonstrates professional software engineering practices"
        )

    return bullets[:4]


def generate_project_bullets(project: dict) -> list:
    """Generate detailed Shaadi-style project bullets (4-5 lines each)."""
    return generate_ai_bullets(project)


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
