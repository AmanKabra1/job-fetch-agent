"""
Aman Kabra - structured resume profile.

This is the single source of truth used to render both the PDF (reportlab)
and the Word (.docx) resume. Edit your details here once and both formats
stay in sync.

The `SKILL_KEYWORDS` map at the bottom drives auto-tailoring: when you pass a
job description, any skill whose alias appears in the JD gets pushed to the
front of its category and bold-highlighted, and the summary line is rewritten
to lead with your top matching stack.
"""

# --------------------------------------------------------------------------- #
# CONTACT
# --------------------------------------------------------------------------- #
NAME = "Aman Kabra"
LOCATION = "Noida"
PHONE = "6378781547"
EMAIL = "amankabra.it24@gmail.com"
LINKEDIN = "https://www.linkedin.com/in/aman-kabra-55a9541ba/"
GITHUB = "https://github.com/AmanKabra1"

# --------------------------------------------------------------------------- #
# SUMMARY
#   {stack} is replaced at render time with your top matching skills for the
#   target job (or the DEFAULT_STACK below when no JD is supplied).
# --------------------------------------------------------------------------- #
DEFAULT_STACK = ["NestJS", "Node.js", "TypeScript", "Python", "FastAPI"]

SUMMARY_TEMPLATE = (
    "Backend-focused Software Development Engineer (SDE-1) with 2 years of experience "
    "building scalable microservices and RESTful APIs using {stack}. Optimized MySQL and "
    "PostgreSQL databases and integrated AWS services for 99.9% uptime. Works in an "
    "AI-native engineering setup: LLM integration, RAG and agentic AI (LangChain, "
    "LangGraph) in Python, shipping with AI coding tools (Claude, Codex); foundation in "
    "Go and Java (Spring Boot)."
)

# --------------------------------------------------------------------------- #
# EXPERIENCE
# --------------------------------------------------------------------------- #
EXPERIENCE = [
    {
        "company": "Sanchi Connect Pvt Ltd",
        "title": "Software Development Engineer I (SDE-1)",
        "dates": "Aug 2024 - Present",
        "location": "Noida, Uttar Pradesh, India",
        "bullets": [
            "Part of the company's move to an AI-native engineering setup: use AI coding "
            "tools (Claude, Codex) and LLM-powered workflows in day-to-day development, and "
            "build AI/LLM features in Python (LLM integration, RAG, agentic workflows).",
            "Architected scalable RESTful APIs and microservices using NestJS, "
            "Node.js, Express.js, and TypeScript, enabling seamless inter-service "
            "communication across distributed systems.",
            "Engineered MySQL and PostgreSQL schema design, query optimizations, "
            "and stored procedures, improving efficiency by 30% and reducing "
            "average response latency.",
            "Integrated AWS S3 for cloud storage and AWS SES for transactional "
            "emails; implemented JWT-based authentication with RBAC for secure "
            "access control.",
            "Designed backend services using Docker, configured CI/CD pipelines "
            "(GitHub Actions, Jenkins), ensuring 99.9% uptime; resolved "
            "bottlenecks through profiling and monitoring.",
            "Wrote Python scripts for data processing and ETL automation; building "
            "Java (Spring Boot) and Go (Golang) microservice skills.",
            "Active in Agile/Scrum ceremonies and peer code reviews, improving team "
            "velocity by 20%.",
        ],
    },
    {
        "company": "Talent Serve",
        "title": "Full Stack Engineer",
        "dates": "Apr 2024 - Jul 2024",
        "location": "Jaipur, Rajasthan, India",
        "bullets": [
            "Built full-stack features end-to-end, rapidly acquiring Python, "
            "Node.js, and RESTful API development skills to solve daily "
            "engineering challenges.",
            "Developed backend modules with Express.js and Python (Flask/FastAPI), "
            "integrated third-party APIs and implemented authentication flows "
            "(JWT, OAuth 2.0).",
        ],
    },
    {
        "company": "Persistent Systems",
        "title": "Software Engineer Intern",
        "dates": "Jan 2024 - Apr 2024",
        "location": "Jaipur, Rajasthan, India",
        "bullets": [
            "Developed and tested backend modules using Java, Spring Framework and MySQL on "
            "enterprise systems; strengthened OOP and design-pattern fundamentals (JUnit, TDD).",
        ],
    },
]

# --------------------------------------------------------------------------- #
# TECHNICAL SKILLS  (category -> ordered list of skills)
#   The order here is your default order; tailoring reorders matched skills to
#   the front within each category.
# --------------------------------------------------------------------------- #
SKILLS = {
    "Languages": [
        "TypeScript", "JavaScript (ES6+)", "Python", "Java (Spring Boot)",
        "Go (Golang)", "SQL", "HTML", "CSS",
    ],
    "Backend Frameworks": [
        "NestJS", "Node.js", "Express.js", "Spring Boot", "FastAPI", "Flask",
        "Django",
    ],
    "Frontend": ["Angular 17 (Signals, standalone components, RxJS)"],
    "Databases": [
        "MySQL (schema design, query optimization, stored procedures)",
        "PostgreSQL",
    ],
    "Cloud & DevOps": [
        "AWS S3", "AWS SES", "Docker", "CI/CD Pipelines", "Git", "GitHub Actions",
        "Jenkins",
    ],
    "AI/ML": [
        "Python", "Machine Learning", "LLM Integration", "AI Coding Assistants (Claude, Codex)",
        "RAG", "LangChain", "LangGraph",
        "AI Agents (Agentic AI)",
    ],
    "Architecture & Patterns": [
        "Microservices", "RESTful APIs", "JWT Authentication", "OAuth 2.0", "MVC",
        "Agile/Scrum",
    ],
    "Tools": [
        "Postman", "VS Code", "Linux/Unix", "Swagger/OpenAPI", "n8n",
        "Power BI",
    ],
}

# --------------------------------------------------------------------------- #
# PROJECTS
# --------------------------------------------------------------------------- #
PROJECTS = [
    {
        "name": "AI Job Search & Resume Agent",
        "stack": "Python, FastAPI, LLM (Groq), Tavily, GitHub Actions, Vercel",
        "github": "https://github.com/AmanKabra1/job-fetch-agent",
        "live": "https://job-fetch-agent.vercel.app",
        "bullets": [
            "Built a Python/FastAPI agent that pulls jobs from LinkedIn, Indeed, Naukri and ATS career pages, reads each full job description, and ranks roles by skills, experience and salary.",
            "Integrated an LLM (Groq) and Tavily web research to write interview answers grounded in the candidate's own data, flagging any invented figures.",
            "Generates ATS-tailored PDF/Word resumes per job (keyword mirroring, ATS score) with ReportLab and python-docx; scheduled on GitHub Actions, deployed on Vercel.",
        ],
    },
    {
        "name": "Shaadi Vidhaan",
        "stack": "NestJS, Angular 17, TypeScript, MySQL, Docker, Render, Vercel",
        "live": "https://wedding-planner-wine-six.vercel.app/",
        "bullets": [
            "Independently built a production full-stack platform for Indian wedding & cultural event planning (28+ states, 7 event types, 50+ seeded rituals).",
            "Engineered a NestJS REST API with TypeORM + MySQL, role-based JWT auth (user vs. organizer), Swagger/OpenAPI docs and validation pipes.",
            "Built the Angular 17 frontend with Signals, standalone components, lazy-loaded routes and RxJS response caching.",
            "Containerized the backend with Docker; CI/CD via GitHub Actions auto-redeploys to Render and Vercel on every push.",
        ],
    },
    {
        "name": "Personal Portfolio",
        "stack": "HTML, CSS, JavaScript",
        "live": "https://dark-mode-portfolio--amankabrait24.replit.app",
        "bullets": [
            "Dark-mode portfolio site showcasing projects, skills and experience, built with vanilla HTML, CSS and JavaScript.",
            "Mobile-first responsive layout with SEO optimization and smooth animations; deployed live on Replit.",
        ],
    },
]

# --------------------------------------------------------------------------- #
# REMOVED: Kept only Shaadi Vidhaan (main, swappable on score >= 75%)
# and Personal Portfolio (secondary). All 20+ other GitHub projects removed
# per user request for cleaner, curated project list.

# --------------------------------------------------------------------------- #
# EDUCATION & CERTIFICATIONS
# --------------------------------------------------------------------------- #
EDUCATION = {
    "school": "Jaipur Engineering College and Research Centre (JECRC)",
    "degree": "Bachelor of Technology, Information Technology",
    "dates": "Aug 2020 - Jun 2024",
    "location": "Jaipur, Rajasthan, India",
}

# --------------------------------------------------------------------------- #
# CERTIFICATIONS
# --------------------------------------------------------------------------- #
CERTIFICATIONS = [
    "Google Digital Garage - Digital Marketing",
    "The Complete Python Developer - Advanced Programming",
    "HTML, CSS & JavaScript - Certification Course",
    "Google Cloud Infrastructure - Core Services, Scaling, Automation",
]

SKILL_KEYWORDS = {
    "NestJS": ["nestjs", "nest.js"],
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Express.js": ["express.js", "expressjs"],
    "TypeScript": ["typescript"],
    "JavaScript (ES6+)": ["javascript", "es6", "ecmascript"],
    "Python": ["python"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Java (Spring Boot)": ["java"],
    "Spring Boot": ["spring boot", "springboot"],
    "Go (Golang)": ["golang", "go lang"],
    "SQL": ["sql"],
    "MySQL (schema design, query optimization, stored procedures)": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "AWS S3": ["aws", "s3", "amazon web services"],
    "AWS SES": ["aws ses", "amazon ses"],
    "Docker": ["docker", "container", "containeri"],
    "CI/CD Pipelines": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "GitHub Actions": ["github actions"],
    "Jenkins": ["jenkins"],
    "Git": ["git"],
    "Microservices": ["microservice", "micro service", "distributed system"],
    "RESTful APIs": ["rest api", "rest apis", "restful"],
    "JWT Authentication": ["jwt"],
    "OAuth 2.0": ["oauth"],
    "Angular 17 (Signals, standalone components, RxJS)": ["angular", "rxjs"],
    "LLM Integration": ["llm", "large language model", "gpt", "openai", "claude", "gemini"],
    "RAG": ["rag", "retrieval-augmented", "retrieval augmented", "vector"],
    "Machine Learning": ["machine learning", "ml ", "deep learning", "pytorch", "tensorflow"],
    "LangChain": ["langchain", "lang chain"],
    "LangGraph": ["langgraph", "lang graph"],
    "AI Coding Assistants (Claude, Codex)": ["claude", "codex", "copilot", "cursor", "ai coding",
                                            "ai-assisted", "ai assisted", "ai tools", "ai-native"],
    "AI Agents (Agentic AI)": ["agentic ai", "agentic", "ai agent", "ai agents",
                              "autonomous agent", "multi-agent", "multi agent"],
    "n8n": ["n8n", "workflow automation"],
    "Power BI": ["power bi", "powerbi", "tableau", "data visualization"],
    "Agile/Scrum": ["agile", "scrum", "kanban"],
    "Swagger/OpenAPI": ["swagger", "openapi"],
    "Postman": ["postman"],
}
