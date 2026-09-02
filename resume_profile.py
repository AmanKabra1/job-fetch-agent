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
        "name": "job-fetch-agent",
        "stack": "Python",
        "link": "https://github.com/AmanKabra1/job-fetch-agent",
        "bullets": [
            "Production job-fetch-agent project built with Python",
            "Implemented using Python for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "ai-travel-planner",
        "stack": "Python, LangGraph, PostgreSQL, AI, Machine Learning",
        "link": "https://github.com/AmanKabra1/ai-travel-planner",
        "bullets": [
            "Production multi-agent AI travel planner — LangGraph, Groq LLaMA 3.3, MCP (flights/weather/hotels), human-in-the-loop, PostgreSQL memory, Streamlit UI",
            "Built with Python, LangGraph, PostgreSQL; leveraged AI, Machine Learning for enhanced functionality and scalability",
            "Deployed as production-ready system with focus on reliability, performance, and maintainability",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "singplay",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/singplay",
        "bullets": [
            "SingPlay — music streaming, DJ, karaoke & Sing Along app built with Next.js 16, TiDB, Drizzle ORM",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Delivered production-grade solution demonstrating full-stack capabilities and professional software engineering practices",
        ],
    },
    {
        "name": "langgraph-chatbot",
        "stack": "Python, LangGraph",
        "link": "https://github.com/AmanKabra1/langgraph-chatbot",
        "bullets": [
            "Production LangGraph chatbot with embeddable widget, RAG, web search and multi-tenant client management",
            "Implemented using Python and LangGraph for robust architecture",
            "Deployed as production-ready system with focus on reliability, performance, and maintainability",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "ai-form-builder",
        "stack": "PHP, AI",
        "link": "https://github.com/AmanKabra1/ai-form-builder",
        "bullets": [
            "Production ai-form-builder project built with PHP, AI",
            "Implemented using PHP and AI for robust architecture",
            "Integrated advanced AI/ML capabilities for intelligent automation and data-driven decision making",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "langgraph-blog-writer",
        "stack": "Python, LangGraph",
        "link": "https://github.com/AmanKabra1/langgraph-blog-writer",
        "bullets": [
            "Production langgraph-blog-writer project built with Python, LangGraph",
            "Implemented using Python and LangGraph for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "live-location-share",
        "stack": "HTML",
        "link": "https://github.com/AmanKabra1/live-location-share",
        "bullets": [
            "Live location sharing PWA - connect with share codes and auto-share every 3 hours",
            "Implemented using HTML for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "SB",
        "stack": "Java",
        "link": "https://github.com/AmanKabra1/SB",
        "bullets": [
            "Production SB project built with Java",
            "Implemented using Java for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "hotel_management_project",
        "stack": "HTML",
        "link": "https://github.com/AmanKabra1/hotel_management_project",
        "bullets": [
            "Production hotel_management_project project built with HTML",
            "Implemented using HTML for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "task-management-api",
        "stack": "TypeScript, MongoDB, Redis",
        "link": "https://github.com/AmanKabra1/task-management-api",
        "bullets": [
            "Express + TypeScript REST API: JWT auth, role-based access, MongoDB (Mongoose), Redis, Zod validation",
            "Implemented using TypeScript and MongoDB and Redis for robust architecture",
            "Designed database architecture with optimization for query performance and data consistency at scale",
            "Delivered production-grade solution demonstrating full-stack capabilities and professional software engineering practices",
        ],
    },
    {
        "name": "angular-tut",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/angular-tut",
        "bullets": [
            "Full-stack angular-tut project",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "Next",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/Next",
        "bullets": [
            "Full-stack Next project",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "demo1",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/demo1",
        "bullets": [
            "Production demo1 project built with TypeScript",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "babbar",
        "stack": "C++",
        "link": "https://github.com/AmanKabra1/babbar",
        "bullets": [
            "Production babbar project built with C++",
            "Implemented using C++ for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "ML-AI-IT",
        "stack": "Jupyter Notebook, AI, Machine Learning",
        "link": "https://github.com/AmanKabra1/ML-AI-IT",
        "bullets": [
            "Production ML-AI-IT project built with Jupyter Notebook, AI, Machine Learning",
            "Implemented using Jupyter Notebook and AI and Machine Learning for robust architecture",
            "Integrated advanced AI/ML capabilities for intelligent automation and data-driven decision making",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "amrutam-backend1",
        "stack": "JavaScript",
        "link": "https://github.com/AmanKabra1/amrutam-backend1",
        "bullets": [
            "Production amrutam-backend1 project built with JavaScript",
            "Implemented using JavaScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "uber-services",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/uber-services",
        "bullets": [
            "Production uber-services project built with TypeScript",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "Project-NodeJS",
        "stack": "CSS, Node.js",
        "link": "https://github.com/AmanKabra1/Project-NodeJS",
        "bullets": [
            "Production Project-NodeJS project built with CSS, Node.js",
            "Implemented using CSS and Node.js for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "vendor-management",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/vendor-management",
        "bullets": [
            "Vendor Management System (NestJS + Angular) with JWT auth & role-based admin/vendor portals — evolving into RideFleet, a shared delivery-rider platform",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Delivered production-grade solution demonstrating full-stack capabilities and professional software engineering practices",
        ],
    },
    {
        "name": "finance-backend",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/finance-backend",
        "bullets": [
            "Production finance-backend project built with TypeScript",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "AgenticAI",
        "stack": "Jupyter Notebook, AI",
        "link": "https://github.com/AmanKabra1/AgenticAI",
        "bullets": [
            "Production AgenticAI project built with Jupyter Notebook, AI",
            "Implemented using Jupyter Notebook and AI for robust architecture",
            "Integrated advanced AI/ML capabilities for intelligent automation and data-driven decision making",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "AmanKabra1",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/AmanKabra1",
        "bullets": [
            "Full-stack AmanKabra1 project",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "langchain-learning",
        "stack": "Jupyter Notebook, LangChain, AI",
        "link": "https://github.com/AmanKabra1/langchain-learning",
        "bullets": [
            "Production langchain-learning project built with Jupyter Notebook, LangChain, AI",
            "Implemented using Jupyter Notebook and LangChain and AI for robust architecture",
            "Integrated advanced AI/ML capabilities for intelligent automation and data-driven decision making",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "Cricket",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/Cricket",
        "bullets": [
            "Production Cricket project built with TypeScript",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "CoWorking-Space",
        "stack": "Python",
        "link": "https://github.com/AmanKabra1/CoWorking-Space",
        "bullets": [
            "Production CoWorking-Space project built with Python",
            "Implemented using Python for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "aman_portfolio-app",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/aman_portfolio-app",
        "bullets": [
            "Production aman_portfolio-app project built with TypeScript",
            "Implemented using TypeScript for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "Images",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/Images",
        "bullets": [
            "Full-stack Images project",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "demo",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/demo",
        "bullets": [
            "Full-stack demo project",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
        ],
    },
    {
        "name": "UAT Test Project",
        "stack": "Python, Testing",
        "link": "",
        "bullets": [
            "This is a UAT test project for verification",
            "Implemented using Python and Testing for robust architecture",
            "Implemented best practices for code quality, testing, and continuous deployment",
            "Showcases expertise in full-stack development with clean architecture and production deployment experience",
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
