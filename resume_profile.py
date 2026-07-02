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
DEFAULT_STACK = ["NestJS", "Node.js", "TypeScript", "Python", "Java"]

SUMMARY_TEMPLATE = (
    "Backend-focused Software Developer with 2 years of experience building "
    "scalable microservices and RESTful APIs using {stack}. Proven expertise in "
    "optimizing relational databases (MySQL, PostgreSQL) and integrating "
    "cloud-native AWS services to achieve 99.9% uptime. Strong foundation in Go "
    "(Golang) for performance-critical services. Passionate about distributed "
    "systems, clean architecture, and leveraging Spring Boot for high-throughput "
    "applications."
)

# --------------------------------------------------------------------------- #
# EXPERIENCE
# --------------------------------------------------------------------------- #
EXPERIENCE = [
    {
        "company": "Sanchi Connect Pvt Ltd",
        "title": "Software Developer",
        "dates": "Aug 2024 - Present",
        "location": "Noida, Uttar Pradesh, India",
        "bullets": [
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
            "Actively learning Java (Spring Boot) and Go (Golang) for "
            "high-performance microservices; implemented Python scripts for data "
            "processing and ETL automation.",
            "Participated in Agile/Scrum ceremonies, daily standups, sprint "
            "planning, and peer code reviews, improving team velocity by 20%.",
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
            "Contributed to enterprise software development, gaining exposure to "
            "large-scale Java-based system design and production engineering "
            "practices.",
            "Developed and tested backend modules using Java, Spring Framework, "
            "and MySQL, strengthened fundamentals in OOP and design patterns "
            "(JUnit, TDD).",
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
        "Python", "Machine Learning", "LLM Integration",
        "RAG (Retrieval-Augmented Generation)", "LangChain", "LangGraph",
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
        "name": "Shaadi Vidhaan",
        "stack": "NestJS, Angular 17, TypeScript, MySQL, Docker, Render, Vercel",
        "link": "https://wedding-planner-wine-six.vercel.app/",
        "bullets": [
            "Independently built a production full-stack platform for Indian "
            "wedding & cultural event planning, covering 28+ states, 7 event "
            "types, and 50+ seeded rituals with ceremony details.",
            "Engineered a NestJS REST API with TypeORM + MySQL, JWT auth with role "
            "separation (user vs. organizer), Swagger/OpenAPI docs, validation "
            "pipes, and CORS configuration.",
            "Developed Angular 17 frontend using Signals, standalone components, "
            "lazy-loaded routes, and RxJS Map-based response caching for improved "
            "load performance.",
            "Containerized backend with Docker and configured CI/CD via GitHub "
            "Actions, enabling auto-redeploy on Render (backend) and Vercel "
            "(frontend) on every push.",
        ],
    },
    {
        "name": "Personal Portfolio",
        "stack": "Node.js, TypeScript, Replit",
        "link": "https://dark-mode-portfolio--amankabrait24.replit.app",
        "bullets": [
            "Built an automated ETL pipeline for CSV-to-MySQL data transformation; "
            "utilized Pandas for cleaning, integrated AWS S3 for storage, reducing "
            "manual processing time by 70%.",
        ],
    },
]

# --------------------------------------------------------------------------- #
# EDUCATION & CERTIFICATIONS
# --------------------------------------------------------------------------- #
EDUCATION = {
    "school": "Jaipur Engineering College and Research Centre (JECRC)",
    "degree": "Bachelor of Technology, Information Technology",
    "dates": "Aug 2020 - Jun 2024",
    "location": "Jaipur, Rajasthan, India",
}

CERTIFICATIONS = [
    "Google Digital Garage - Digital Marketing",
    "The Complete Python Developer - Advanced Programming",
    "HTML, CSS & JavaScript - Certification Course",
    "Google Cloud Infrastructure - Core Services, Scaling, Automation",
]

# --------------------------------------------------------------------------- #
# TAILORING KEYWORDS
#   Maps a *skill label* (as it appears in SKILLS above) to the list of aliases
#   that, if found in a job description, mark that skill as relevant. Matching
#   is case-insensitive and word-boundary aware (so "go" won't match "google").
# --------------------------------------------------------------------------- #
SKILL_KEYWORDS = {
    "NestJS": ["nestjs", "nest.js"],
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Express.js": ["express.js", "express", "expressjs"],
    "TypeScript": ["typescript", "ts"],
    "JavaScript (ES6+)": ["javascript", "js", "es6", "ecmascript"],
    "Python": ["python"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Java (Spring Boot)": ["java"],
    "Spring Boot": ["spring boot", "spring", "springboot"],
    "Go (Golang)": ["golang", "go lang", " go "],
    "SQL": ["sql"],
    "MySQL (schema design, query optimization, stored procedures)": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "AWS S3": ["aws", "s3", "amazon web services"],
    "AWS SES": ["ses"],
    "Docker": ["docker", "container", "containeri"],
    "CI/CD Pipelines": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "GitHub Actions": ["github actions"],
    "Jenkins": ["jenkins"],
    "Git": ["git"],
    "Microservices": ["microservice", "micro service", "distributed system"],
    "RESTful APIs": ["rest api", "restful", "rest"],
    "JWT Authentication": ["jwt"],
    "OAuth 2.0": ["oauth"],
    "Angular 17 (Signals, standalone components, RxJS)": ["angular", "rxjs"],
    "LLM Integration": ["llm", "large language model", "gpt", "openai", "claude", "gemini"],
    "RAG (Retrieval-Augmented Generation)": ["rag", "retrieval-augmented", "retrieval augmented", "vector"],
    "Machine Learning": ["machine learning", "ml ", "deep learning", "pytorch", "tensorflow"],
    "LangChain": ["langchain", "lang chain"],
    "LangGraph": ["langgraph", "lang graph"],
    "AI Agents (Agentic AI)": ["agentic ai", "agentic", "ai agent", "ai agents",
                              "autonomous agent", "multi-agent", "multi agent"],
    "n8n": ["n8n", "workflow automation"],
    "Power BI": ["power bi", "powerbi", "tableau", "data visualization"],
    "Agile/Scrum": ["agile", "scrum", "kanban"],
    "Swagger/OpenAPI": ["swagger", "openapi"],
    "Postman": ["postman"],
}
