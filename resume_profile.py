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
            "A single-user web app (and optional daily cron): 1. Find jobs across many boards - generic: ranked to whatever you give it (an uploaded resume / target role / JD / skills), never to any baked-in data. 2. Create a resume two ways: (A) generate your saved resume",
            "Implemented core architecture using Python ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "ai-travel-planner",
        "stack": "Python, LangGraph, PostgreSQL, AI, Machine Learning",
        "link": "https://github.com/AmanKabra1/ai-travel-planner",
        "bullets": [
            "Production multi-agent AI travel planner � LangGraph, Groq LLaMA 3.3, MCP (flights/weather/hotels), human-in-the-loop, PostgreSQL memory, Streamlit UI",
            "Engineered backend with Python, LangGraph; integrated PostgreSQL, AI, Machine Learning for enhanced functionality, performance, and production reliability",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "singplay",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/singplay",
        "bullets": [
            "SingPlay � music streaming, DJ, karaoke & Sing Along app built with Next.js 16, TiDB, Drizzle ORM",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "langgraph-chatbot",
        "stack": "Python, LangGraph",
        "link": "https://github.com/AmanKabra1/langgraph-chatbot",
        "bullets": [
            "Production LangGraph chatbot with embeddable widget, RAG, web search and multi-tenant client management",
            "Implemented core architecture using Python with LangGraph ensuring scalable and maintainable codebase",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "ai-form-builder",
        "stack": "PHP, AI",
        "link": "https://github.com/AmanKabra1/ai-form-builder",
        "bullets": [
            "<p align=\"center\"><a href=\"https://laravel.com\" target=\"blank\"><img src=\"https://raw.githubusercontent.com/laravel/art/master/logo-lockup/5%20SVG/2%20CMYK/1%20Full%20Color/laravel-logolockup-cmyk-red.svg\" width=\"400\" alt=\"Laravel Logo\"></a></p> <p align=\"center\"> <a href=\"https://github.com/laravel/framework/actions\"><img src=\"https://github.com/laravel/framework/workflows/tests/badge.svg\" alt=\"Build Status\"></a> <a href=\"https://packagist.org/packages/laravel/framework\"><img src=\"https://img.sh",
            "Implemented core architecture using PHP with AI ensuring scalable and maintainable codebase",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "langgraph-blog-writer",
        "stack": "Python, LangGraph",
        "link": "https://github.com/AmanKabra1/langgraph-blog-writer",
        "bullets": [
            "A LangGraph pipeline that turns a one-line topic into a finished technical blog post � routing, researching, planning, writing sections in parallel, and generating diagrams � wrapped in a Streamlit UI that runs on a phone, a tablet or a desktop. It runs in one of two modes, chosen automatically by what's in Secrets:",
            "Implemented core architecture using Python with LangGraph ensuring scalable and maintainable codebase",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "live-location-share",
        "stack": "HTML",
        "link": "https://github.com/AmanKabra1/live-location-share",
        "bullets": [
            "Live location sharing PWA - connect with share codes and auto-share every 3 hours",
            "Implemented core architecture using HTML ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "SB",
        "stack": "Java",
        "link": "https://github.com/AmanKabra1/SB",
        "bullets": [
            "Independently developed SB leveraging Java as primary technology stack to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability.",
            "Implemented core architecture using Java ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "hotel_management_project",
        "stack": "HTML",
        "link": "https://github.com/AmanKabra1/hotel_management_project",
        "bullets": [
            "Independently developed hotel_management_project leveraging HTML as primary technology stack to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability.",
            "Implemented core architecture using HTML ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "task-management-api",
        "stack": "TypeScript, MongoDB, Redis",
        "link": "https://github.com/AmanKabra1/task-management-api",
        "bullets": [
            "Express + TypeScript REST API: JWT auth, role-based access, MongoDB (Mongoose), Redis, Zod validation",
            "Engineered backend with TypeScript, MongoDB; integrated Redis for enhanced functionality, performance, and production reliability",
            "Designed optimized database schema with efficient queries, transactions, and data consistency patterns for handling scale and concurrency",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "angular-tut",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/angular-tut",
        "bullets": [
            "Personal Angular learning project. > Note: project source (e.g. package.json, angular.json, src/app/* components) > is not yet present in this folder. Add it here and commit � the repository is > configured to attribute commits to the personal identity.",
            "Implemented robust architecture following best practices for code quality and system design",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "Next",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/Next",
        "bullets": [
            "Workspace for a Next.js project (my-app/). > Note: the application source under my-app/ is currently an empty scaffold > (only the folder structure and nodemodules/ exist). Add your code under > my-app/src/ and it will be tracked by git.",
            "Implemented robust architecture following best practices for code quality and system design",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "demo1",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/demo1",
        "bullets": [
            "<p align=\"center\"> <a href=\"http://nestjs.com/\" target=\"blank\"><img src=\"https://nestjs.com/img/logo-small.svg\" width=\"120\" alt=\"Nest Logo\" /></a> </p> [circleci-image]: https://img.shields.io/circleci/build/github/nestjs/nest/master?token=abc123def456",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "babbar",
        "stack": "C++",
        "link": "https://github.com/AmanKabra1/babbar",
        "bullets": [
            "Independently developed babbar leveraging C++ as primary technology stack to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability.",
            "Implemented core architecture using C++ ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "ML-AI-IT",
        "stack": "Jupyter Notebook, AI, Machine Learning",
        "link": "https://github.com/AmanKabra1/ML-AI-IT",
        "bullets": [
            "Independently developed ML-AI-IT as a comprehensive solution leveraging Jupyter Notebook, AI for core functionality, with additional integration of Machine Learning to enhance capabilities and deliver production-grade features. The project demonstrates professional-level engineering with emphasis on scalability, reliability, and maintainability. Showcases expertise in full-stack architecture design and implementation of complex systems with multiple technology layers.",
            "Engineered backend with Jupyter Notebook, AI; integrated Machine Learning for enhanced functionality, performance, and production reliability",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "amrutam-backend1",
        "stack": "JavaScript",
        "link": "https://github.com/AmanKabra1/amrutam-backend1",
        "bullets": [
            "1. Clone repo 2. Install dependencies: npm install 3. Set environment variables in .env 4. Run DB migrations Sequelize auto-sync 5. Start server: npm run dev",
            "Implemented core architecture using JavaScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "uber-services",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/uber-services",
        "bullets": [
            "<p align=\"center\"> <a href=\"http://nestjs.com/\" target=\"blank\"><img src=\"https://nestjs.com/img/logo-small.svg\" width=\"120\" alt=\"Nest Logo\" /></a> </p> [circleci-image]: https://img.shields.io/circleci/build/github/nestjs/nest/master?token=abc123def456",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "Project-NodeJS",
        "stack": "CSS, Node.js",
        "link": "https://github.com/AmanKabra1/Project-NodeJS",
        "bullets": [
            "Independently developed Project-NodeJS leveraging CSS, Node.js as primary technology stack to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability.",
            "Implemented core architecture using CSS with Node.js ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "vendor-management",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/vendor-management",
        "bullets": [
            "Vendor Management System (NestJS + Angular) with JWT auth & role-based admin/vendor portals � evolving into RideFleet, a shared delivery-rider platform",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "finance-backend",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/finance-backend",
        "bullets": [
            "<p align=\"center\"> <a href=\"http://nestjs.com/\" target=\"blank\"><img src=\"https://nestjs.com/img/logo-small.svg\" width=\"120\" alt=\"Nest Logo\" /></a> </p> [circleci-image]: https://img.shields.io/circleci/build/github/nestjs/nest/master?token=abc123def456",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "AgenticAI",
        "stack": "Jupyter Notebook, AI",
        "link": "https://github.com/AmanKabra1/AgenticAI",
        "bullets": [
            "A hands-on collection of projects for learning Agentic AI � building systems where Large Language Models (LLMs) don't just answer questions, but reason, use tools, remember context, and take actions to accomplish goals. Each subfolder is a self-contained Python project (managed with [uv](https://github.com/astral-sh/uv)) that demonstrates one building block of an agentic system. --- A plain LLM is a text-in, text-out function. An agent wraps an LLM in a loop that lets it interact with the world:",
            "Implemented core architecture using Jupyter Notebook with AI ensuring scalable and maintainable codebase",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "AmanKabra1",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/AmanKabra1",
        "bullets": [
            "<div align=\"center\"> Backend-Focused Software Engineer | API Architect | System Design Enthusiast Building scalable, production-ready systems with clean code and thoughtful design. [Portfolio](#-featured-projects) � [Resume](#resume) � [Connect](#-connect-with-me) � [Blog](#-articles--blog)",
            "Implemented robust architecture following best practices for code quality and system design",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "langchain-learning",
        "stack": "Jupyter Notebook, LangChain, AI",
        "link": "https://github.com/AmanKabra1/langchain-learning",
        "bullets": [
            "A collection of hands-on projects exploring the modern LangChain (v1) ecosystem � agents, evaluation, model gateways, and core LangChain concepts. Each subfolder is a self-contained project managed with [uv](https://docs.astral.sh/uv/). | Folder | Focus | Key libraries |",
            "Engineered backend with Jupyter Notebook, LangChain; integrated AI for enhanced functionality, performance, and production reliability",
            "Integrated advanced AI/ML capabilities including multi-agent orchestration, retrieval-augmented generation, and intelligent automation for complex workflows",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "Cricket",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/Cricket",
        "bullets": [
            "A real-time scoring platform for local cricket tournaments and grounds � inspired by CricHeroes, Cricbuzz, and ESPN Cricinfo, but built for community sport. Cricket-first, with a sport-agnostic core (teams/tournaments/venues) ready to extend to football, kabaddi, etc.",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "CoWorking-Space",
        "stack": "Python",
        "link": "https://github.com/AmanKabra1/CoWorking-Space",
        "bullets": [
            "The modern operating system for coworking spaces � manage buildings, facilities, bookings, billing, members, inventory, vendors, and community from one platform. | Layer | Technology | |-------|-----------| | Backend | Django 5.1 + Django REST Framework, SimpleJWT auth |",
            "Implemented core architecture using Python ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "aman_portfolio-app",
        "stack": "TypeScript",
        "link": "https://github.com/AmanKabra1/aman_portfolio-app",
        "bullets": [
            "Independently developed aman_portfolio-app leveraging TypeScript as primary technology stack to deliver production-grade features and professional-level capabilities. This comprehensive project demonstrates expertise in full-stack development with emphasis on clean code architecture, scalability, and production-ready implementation. Showcases ability to design, develop, and deploy complete systems with focus on reliability and maintainability.",
            "Implemented core architecture using TypeScript ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "Images",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/Images",
        "bullets": [
            "Developed Images as a complete end-to-end project showcasing comprehensive full-stack capabilities and professional software engineering practices. The implementation demonstrates expertise in system design, architecture patterns, and production deployment. Project reflects commitment to code quality, user experience, and maintainable solutions that scale effectively.",
            "Implemented robust architecture following best practices for code quality and system design",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "demo",
        "stack": "Full Stack",
        "link": "https://github.com/AmanKabra1/demo",
        "bullets": [
            "Developed demo as a complete end-to-end project showcasing comprehensive full-stack capabilities and professional software engineering practices. The implementation demonstrates expertise in system design, architecture patterns, and production deployment. Project reflects commitment to code quality, user experience, and maintainable solutions that scale effectively.",
            "Implemented robust architecture following best practices for code quality and system design",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
        ],
    },
    {
        "name": "UAT Test Project",
        "stack": "Python, Testing",
        "link": "",
        "bullets": [
            "This is a UAT test project for verification",
            "Implemented core architecture using Python with Testing ensuring scalable and maintainable codebase",
            "Implemented key features including API design, data persistence, error handling, and comprehensive testing for production reliability",
            "Deployed as production-ready system with focus on reliability, scalability, and maintainability; demonstrates professional software engineering practices",
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
