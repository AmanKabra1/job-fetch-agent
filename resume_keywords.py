"""
Resume keyword engine — evidence-based ATS keyword optimisation (2026).

What 2026 research says actually moves a resume up in recruiter/ATS ranking
(Workday, Greenhouse, Lever, iCIMS, SmartRecruiters, Naukri RESDEX, LinkedIn
Recruiter):

  1. MIRROR the JD's exact wording for skills you really have (exact string match is
     still the safest signal; modern systems add synonym/semantic matching on top).
  2. Title / headline + summary + recent-role bullets carry more weight than a
     bare skills list; a keyword used inside a bullet beats one only in Skills.
  3. 2-3 natural mentions per key term. Stuffing (>5) is down-scored.
  4. Put BOTH the acronym and the expanded form once (CI/CD, RAG, LLM ...).
  5. Standard section headings, single column, plain text, contact in the body.
  6. NEVER add skills you don't have — recruiters test them and ATS knock-out
     questions ask for years of each. Missing skills are reported as GAPS instead.

This module implements 1-4 and 6: it reads a JD, finds which of the JD's keywords the
candidate has REAL EVIDENCE for (in resume_profile.py + the matched project), and
returns what to mirror, what to put in the headline, and what is a genuine gap.
"""

import re

import resume_profile as P

# --------------------------------------------------------------------------- #
# Lexicon: canonical term -> (JD aliases, evidence regex over the candidate's own
# profile text or None to reuse the aliases). `kind` groups terms for ordering.
# Evidence regexes are what make mirroring HONEST: a derived keyword ("Database
# Design") is only claimed when the profile text actually shows it ("schema design").
# --------------------------------------------------------------------------- #
_L = []


def _t(canon, aliases, evidence=None, kind="tool"):
    _L.append((canon, aliases, evidence, kind))


# languages
_t("Python", ["python"], kind="lang")
_t("TypeScript", ["typescript"], kind="lang")
_t("JavaScript", ["javascript", "es6", "ecmascript"], kind="lang")
_t("Java", ["java", "core java"], kind="lang")
_t("Go", ["golang", "go lang"], kind="lang")
_t("SQL", ["sql"], kind="lang")
# frameworks
_t("Node.js", ["node.js", "nodejs", "node js"], kind="fw")
_t("NestJS", ["nestjs", "nest.js"], kind="fw")
_t("Express.js", ["express.js", "expressjs", "express"], kind="fw")
_t("FastAPI", ["fastapi", "fast api"], kind="fw")
_t("Flask", ["flask"], kind="fw")
_t("Django", ["django"], kind="fw")
_t("Spring Boot", ["spring boot", "springboot", "spring"], kind="fw")
_t("Angular", ["angular"], kind="fw")
_t("React", ["react", "react.js", "reactjs"], kind="fw")
_t("Next.js", ["next.js", "nextjs"], kind="fw")
# data
_t("PostgreSQL", ["postgresql", "postgres"], kind="data")
_t("MySQL", ["mysql"], kind="data")
_t("MongoDB", ["mongodb", "mongo db"], kind="data")
_t("Redis", ["redis"], kind="data")
_t("Kafka", ["kafka"], kind="data")
_t("RabbitMQ", ["rabbitmq"], kind="data")
_t("Elasticsearch", ["elasticsearch", "opensearch"], kind="data")
_t("Database Design", ["database design", "schema design", "data modeling", "data modelling"],
   r"schema design|database design", kind="concept")
_t("Query Optimization", ["query optimization", "query optimisation", "query tuning", "sql optimization"],
   r"query optimi[sz]ation", kind="concept")
# cloud / devops
_t("AWS", ["aws", "amazon web services", "ec2", "s3", "lambda"], r"\baws\b|amazon web services", kind="cloud")
_t("GCP", ["gcp", "google cloud"], r"google cloud|\bgcp\b", kind="cloud")
_t("Azure", ["azure"], kind="cloud")
_t("Docker", ["docker", "containerization", "containerisation", "containers"], r"docker|container", kind="cloud")
_t("Kubernetes", ["kubernetes", "k8s"], kind="cloud")
_t("Terraform", ["terraform"], kind="cloud")
_t("CI/CD", ["ci/cd", "cicd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
   r"ci/cd|github actions|jenkins", kind="cloud")
_t("GitHub Actions", ["github actions"], kind="cloud")
_t("Jenkins", ["jenkins"], kind="cloud")
_t("Linux", ["linux", "unix"], kind="cloud")
_t("Git", ["git", "github", "version control"], r"\bgit\b|github", kind="cloud")
# api / architecture
_t("REST APIs", ["rest api", "rest apis", "restful", "restful apis", "restful api"],
   r"rest(?:ful)?\s+api", kind="arch")
_t("GraphQL", ["graphql"], kind="arch")
_t("gRPC", ["grpc"], kind="arch")
_t("WebSockets", ["websocket", "websockets", "socket.io"], kind="arch")
_t("Microservices", ["microservice", "microservices", "micro service", "micro-services"], kind="arch")
_t("Authentication & Authorization", ["authentication", "authorization", "authorisation", "jwt", "oauth", "oauth2", "rbac"],
   r"\bjwt\b|oauth|rbac", kind="arch")
_t("Swagger/OpenAPI", ["swagger", "openapi"], kind="arch")
_t("API Design", ["api design", "api development", "api integration", "apis"],
   r"rest(?:ful)?\s+api|\bapis?\b", kind="arch")
_t("Event-Driven Architecture", ["event-driven", "event driven"], kind="arch")
# CS fundamentals / practices
_t("Data Structures & Algorithms", ["data structures", "algorithms", "dsa"], kind="cs")
_t("Object-Oriented Programming", ["object-oriented", "object oriented", "oop", "oops"], r"\boop\b|object[- ]oriented",
   kind="cs")
_t("Design Patterns", ["design patterns", "design pattern"], r"design patterns?", kind="cs")
_t("System Design", ["system design", "distributed systems", "scalable systems", "high-level design", "low-level design"],
   r"distributed systems|clean architecture|scalable microservices", kind="cs")
_t("Scalability", ["scalable", "scalability", "high availability"], r"scalab|99\.9%", kind="cs")
_t("Performance Optimization", ["performance optimization", "performance optimisation", "performance tuning", "optimization"],
   r"optimi[sz]", kind="cs")
_t("Unit Testing", ["unit testing", "unit test", "unit tests", "tdd", "junit", "jest", "pytest", "test-driven"],
   r"junit|\btdd\b|unit test|test-driven", kind="cs")
_t("Agile/Scrum", ["agile", "scrum", "kanban", "sdlc"], r"agile|scrum", kind="cs")
_t("Code Review", ["code review", "code reviews", "peer review"], r"code reviews?", kind="cs")
# AI
_t("LLM", ["llm", "llms", "large language model", "large language models", "gpt", "openai", "claude", "gemini"],
   r"\bllm\b|large language model", kind="ai")
_t("Generative AI", ["generative ai", "genai", "gen ai", "gen-ai"], r"\bllm\b|\brag\b|langchain|langgraph", kind="ai")
_t("RAG", ["rag", "retrieval-augmented generation", "retrieval augmented generation"], r"\brag\b|retrieval", kind="ai")
_t("AI-Assisted Development", ["ai-assisted development", "ai assisted development", "ai coding",
                               "ai-native", "ai native", "ai tools", "copilot", "cursor", "codex", "claude code"],
   r"claude|codex|ai[- ]native|ai coding", kind="ai")
_t("LangChain", ["langchain", "lang chain"], kind="ai")
_t("LangGraph", ["langgraph", "lang graph"], kind="ai")
_t("AI Agents", ["ai agent", "ai agents", "agentic", "agentic ai", "multi-agent", "multi agent", "autonomous agents"],
   r"agentic|ai agents?|multi-agent", kind="ai")
_t("Prompt Engineering", ["prompt engineering", "prompting", "prompt design"],
   r"langchain|langgraph|llm integration", kind="ai")
_t("Machine Learning", ["machine learning", "ml"], r"machine learning", kind="ai")
_t("NLP", ["nlp", "natural language processing"], kind="ai")
_t("Vector Databases", ["vector database", "vector databases", "vector db", "pinecone", "chroma", "faiss", "pgvector",
                        "qdrant", "weaviate", "embeddings"], kind="ai")
_t("Hugging Face", ["hugging face", "huggingface", "transformers"], kind="ai")
_t("MCP", ["mcp", "model context protocol"], kind="ai")
_t("n8n", ["n8n", "workflow automation"], kind="tool")
_t("Postman", ["postman"], kind="tool")

LEX = {c: (a, e, k) for c, a, e, k in _L}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _word_in(alias: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9+#])" + re.escape(alias.lower()) + r"(?![a-z0-9+#])", text) is not None


def _profile_blob(extra: str = "") -> str:
    parts = [P.SUMMARY_TEMPLATE]
    parts += [s for items in P.SKILLS.values() for s in items]
    for j in P.EXPERIENCE:
        parts += [j["title"]] + list(j["bullets"])
    for p in P.PROJECTS:
        parts += [p.get("name", ""), p.get("stack", "")] + list(p.get("bullets", []))
    parts += list(P.CERTIFICATIONS)
    parts.append(extra or "")
    return " ".join(parts).lower()


def _evidenced(canon: str, blob: str) -> bool:
    aliases, evidence, _ = LEX[canon]
    if evidence:
        return re.search(evidence, blob, re.I) is not None
    return any(_word_in(a, blob) for a in aliases)


_REQ_HEAD = re.compile(r"(requirements?|must[- ]have|qualifications?|what you(?:'|’)ll need|you have|"
                       r"skills? required|key skills|tech(?:nical)? skills|who you are)", re.I)
_NICE_HEAD = re.compile(r"(nice[- ]to[- ]have|good to have|bonus|preferred|added advantage|plus\b)", re.I)


def jd_keywords(jd_text: str, title: str = ""):
    """[(canon, weight)] for every lexicon term the JD mentions, heaviest first.
    Weight = 1 + title hit + must-have-block hit + (repeats, capped), halved when the
    only mention is inside a nice-to-have block."""
    text = (jd_text or "").replace("\\", "")
    low = " " + text.lower() + " "
    tlow = " " + (title or "").lower() + " "
    req_start = None
    m = _REQ_HEAD.search(low)
    if m:
        req_start = m.start()
    nice = _NICE_HEAD.search(low)
    out = []
    for canon, (aliases, _e, _k) in LEX.items():
        count, first, in_title = 0, None, False
        for a in aliases:
            pat = re.compile(r"(?<![a-z0-9+#])" + re.escape(a.lower()) + r"(?![a-z0-9+#])")
            hits = [h.start() for h in pat.finditer(low)]
            count += len(hits)
            if hits:
                first = hits[0] if first is None else min(first, hits[0])
            if pat.search(tlow):
                in_title = True
        if not count:
            continue
        w = 1.0 + (1.0 if in_title else 0.0) + min(2, count - 1) * 0.5
        if req_start is not None and first is not None and first >= req_start:
            w += 0.5
        if nice and first is not None and first >= nice.start() and not in_title:
            w *= 0.6
        out.append((canon, round(w, 2)))
    out.sort(key=lambda x: -x[1])
    return out


# --------------------------------------------------------------------------- #
# Role family + headline
# --------------------------------------------------------------------------- #
def role_family(title: str, jd_text: str = "") -> str:
    t = (title or "").lower()
    j = (jd_text or "")[:600].lower()
    if re.search(r"\b(ai|ml|llm|genai|gen ai|generative|agent(?:ic)?|machine learning|prompt)\b", t):
        return "ai"
    if re.search(r"\bpython\b", t):
        return "python"
    if re.search(r"\b(node|nest|typescript|express)", t):
        return "node"
    if re.search(r"full[- ]?stack", t):
        return "fullstack"
    if re.search(r"\bsde\b|software development engineer", t):
        return "sde"
    if re.search(r"software (engineer|developer)", t):
        return "software"
    if re.search(r"back[- ]?end|server[- ]side|api", t):
        return "backend"
    if re.search(r"\b(llm|genai|rag|langchain)\b", j) and not re.search(r"\b(node|python|java)\b", t):
        return "ai"
    return "backend"


_FAMILY_TITLE = {
    "ai": "SDE-1 (AI / LLM Applications)",
    "python": "Python Backend Developer",
    "node": "Node.js Backend Developer",
    "fullstack": "Full Stack Engineer",
    "sde": "Software Development Engineer I (SDE-1)",
    "software": "Software Engineer",
    "backend": "Backend Software Engineer",
}
# Stack order shown in the headline per family (only items with evidence are used).
_HEADLINE_PRIORITY = {
    "ai": ["Python", "LLM", "RAG", "LangChain", "AI Agents", "FastAPI"],
    "python": ["Python", "FastAPI", "Django", "Flask", "PostgreSQL", "Docker"],
    "node": ["Node.js", "NestJS", "TypeScript", "Express.js", "PostgreSQL", "Docker"],
    "fullstack": ["Node.js", "TypeScript", "Angular", "NestJS", "PostgreSQL", "Docker"],
    "sde": ["Python", "Node.js", "TypeScript", "REST APIs", "Microservices", "PostgreSQL"],
    "software": ["Node.js", "Python", "TypeScript", "REST APIs", "Microservices", "AWS"],
    "backend": ["Node.js", "NestJS", "Python", "TypeScript", "Microservices", "PostgreSQL"],
}


def build_headline(family: str, matched_terms) -> str:
    """'Backend Software Engineer | Node.js · NestJS · Python · Microservices' — role
    title mirrors the JD family; stack = JD-matched, evidenced skills first."""
    pri = _HEADLINE_PRIORITY.get(family, _HEADLINE_PRIORITY["backend"])
    mt = list(matched_terms or [])
    stack = [s for s in pri if s in mt] + [s for s in pri if s not in mt]
    return f"{_FAMILY_TITLE.get(family, _FAMILY_TITLE['backend'])} | " + " · ".join(stack[:4])


# --------------------------------------------------------------------------- #
# Main API
# --------------------------------------------------------------------------- #
def analyze(jd_text: str, title: str = "", extra_evidence: str = "", listed_in_resume: str = "") -> dict:
    """Return everything the renderers need.

    mirror       evidence-backed JD terms NOT yet visible in the resume's skill list —
                 appended to 'Core Competencies' (acronym + expansion where useful).
    matched      JD terms the candidate has, in JD-weight order (drives ordering,
                 headline, summary).
    gaps         JD terms with NO evidence — reported to you, never put in the resume.
    coverage     0-100 weighted share of the JD's keywords the final resume contains.
    """
    blob = _profile_blob(extra_evidence)
    kws = jd_keywords(jd_text, title)
    visible = (listed_in_resume or _skills_text()).lower()

    matched, mirror, gaps = [], [], []
    tot = got = 0.0
    for canon, w in kws:
        ok = _evidenced(canon, blob)
        tot += w
        if ok:
            got += w
            matched.append(canon)
            aliases, _e, kind = LEX[canon]
            shown = canon.lower() in visible or any(_word_in(a, visible) for a in aliases)
            if not shown:
                mirror.append(canon)
        else:
            gaps.append(canon)

    family = role_family(title, jd_text)
    return {
        "family": family,
        "headline": build_headline(family, matched),
        "matched": matched,
        "mirror": mirror[:10],
        "gaps": gaps[:12],
        "coverage": round(100 * got / tot) if tot else 0,
        "keywords": kws,
    }


def _skills_text() -> str:
    return " ".join(s for items in P.SKILLS.values() for s in items)


def order_bullets(bullets, matched_terms):
    """Stable re-order so the bullet that hits the most JD terms comes FIRST (top
    bullets of the recent role carry the most ATS/recruiter weight). Never edits text."""
    if not matched_terms:
        return list(bullets)
    scored = []
    for i, b in enumerate(bullets):
        low = " " + b.lower() + " "
        s = 0
        for c in matched_terms:
            aliases, _e, _k = LEX.get(c, ([c.lower()], None, ""))
            if any(_word_in(a, low) for a in aliases):
                s += 1
        if re.search(r"\b(actively learning|currently learning|learning)\b", low):
            s -= 2            # "learning X" is a weak lead bullet; keep it last
        scored.append((-s, i, b))
    scored.sort()
    return [b for _s, _i, b in scored]


def ordered_experience(matched_terms):
    """P.EXPERIENCE with each role's bullets re-ordered by JD relevance (deep copy)."""
    out = []
    for j in P.EXPERIENCE:
        j2 = dict(j)
        j2["bullets"] = order_bullets(j["bullets"], matched_terms)
        out.append(j2)
    return out
