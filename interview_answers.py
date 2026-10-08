"""
Interview / application-question answer writer.

You paste a question from a job application or an HR screen ("Why do you want to
join us?", "What is your biggest challenge?", "Expected CTC?") and get an answer
written in first person from YOUR real history — resume, jobs, projects, education
— plus, when a company name is given, a quick web research pass (Tavily) so the
answer can mention what that company actually does.

Two profiles feed the same writer:
  * "profile" mode — your saved resume (resume_profile.py) + projects + any extra
    notes you stored in the page + your screening answers from .env.
  * "visitor" mode — only the resume the visitor uploads. Nothing of yours is used.

The LLM is Groq (free tier) over its OpenAI-compatible REST API, called with plain
`requests` so it also works on Vercel where the groq SDK isn't installed.
"""
import os
import re
import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
_TIMEOUT = 40
MAX_CONTEXT_CHARS = 12000

# One-click questions HR / application forms ask over and over.
COMMON_QUESTIONS = [
    "Tell me about yourself.",
    "Why are you looking for a job change?",
    "Why do you want to join our company?",
    "What was the biggest challenge you faced in your previous work, and how did you handle it?",
    "What are your expectations from this role?",
    "When can you join? What is your notice period?",
    "What is your expected CTC?",
    "What are your strengths and weaknesses?",
    "Describe a project you are proud of.",
    "Where do you see yourself in 3-5 years?",
    "Why should we hire you?",
    "Are you willing to relocate?",
]


# --------------------------------------------------------------------------- #
# Candidate context
# --------------------------------------------------------------------------- #
def saved_profile_text(extra_notes: str = "", screening: dict = None) -> str:
    """Everything known about the owner as plain text for the LLM. Phone / email /
    links are deliberately left out — they're never needed to answer a question."""
    import resume_profile as P
    out = [f"Name: {P.NAME}", f"Based in: {P.LOCATION}"]
    out.append("Summary: " + P.SUMMARY_TEMPLATE.replace("{stack}", ", ".join(P.DEFAULT_STACK)))
    out.append("\nWORK EXPERIENCE (most recent first):")
    for e in P.EXPERIENCE:
        out.append(f"- {e['title']} at {e['company']} ({e['dates']}, {e['location']})")
        out += [f"    * {b}" for b in e["bullets"]]
    out.append("\nSKILLS:")
    out += [f"- {cat}: {', '.join(items)}" for cat, items in P.SKILLS.items()]
    out.append("\nPROJECTS:")
    for p in P.PROJECTS:
        out.append(f"- {p['name']} ({p['stack']})")
        out += [f"    * {b}" for b in p["bullets"]]
    try:                                               # GitHub / manually-added projects
        import projects_manager as PM
        for p in (PM.load_projects().get("projects") or [])[:12]:
            line = f"- {p.get('name', '')}: {str(p.get('description') or '')[:220]}"
            if p.get("tech_stack"):
                line += f" [tech: {', '.join(p['tech_stack'][:8])}]"
            out.append(line)
    except Exception:
        pass
    ed = P.EDUCATION
    out.append(f"\nEDUCATION: {ed['degree']}, {ed['school']} ({ed['dates']})")
    out.append("CERTIFICATIONS: " + "; ".join(P.CERTIFICATIONS))
    s = {k: v for k, v in (screening or {}).items() if v}
    if s:
        out.append("\nSTANDARD ANSWERS (use these exact facts when asked):")
        out += [f"- {k.replace('_', ' ')}: {v}" for k, v in s.items()]
    notes = (extra_notes or "").strip()
    if notes:
        out.append("\nEXTRA NOTES FROM THE CANDIDATE (their own words — highest priority, "
                   "covers why they switch, challenges faced, expectations, etc.):\n" + notes)
    return "\n".join(out)[:MAX_CONTEXT_CHARS]


# --------------------------------------------------------------------------- #
# Company research (Tavily)
# --------------------------------------------------------------------------- #
def research_company(company: str, role: str = "") -> dict:
    """Short web research on `company`. Returns {summary, sources[], available}.
    Needs TAVILY_API_KEY; without it returns available=False and the answer is
    written without company-specific facts (the writer is told not to invent any)."""
    company = (company or "").strip()
    key = os.environ.get("TAVILY_API_KEY")
    if not company:
        return {"summary": "", "sources": [], "available": False, "note": ""}
    if not key:
        return {"summary": "", "sources": [], "available": False,
                "note": "Set TAVILY_API_KEY to research the company."}
    q = f"{company} company what they do products culture values recent news"
    if role:
        q += f" {role} team engineering"
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": key, "query": q, "max_results": 5,
            "search_depth": "basic", "include_answer": True,
        }, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"summary": "", "sources": [], "available": False,
                "note": f"Company research failed: {e}"}
    parts = []
    if data.get("answer"):
        parts.append(str(data["answer"]).strip())
    sources = []
    for res in (data.get("results") or [])[:5]:
        snippet = re.sub(r"\s+", " ", str(res.get("content") or "")).strip()[:350]
        if snippet:
            parts.append(snippet)
        if res.get("url"):
            sources.append({"title": str(res.get("title") or res["url"])[:90], "url": res["url"]})
    return {"summary": "\n".join(parts)[:2500], "sources": sources,
            "available": bool(parts), "note": ""}


# --------------------------------------------------------------------------- #
# Answer writer
# --------------------------------------------------------------------------- #
_SYSTEM = """You write job-application and HR-interview answers for a real candidate.
Rules:
1. First person, as the candidate. Sound like a thoughtful person talking, not a template:
   plain words, varied sentence length, no buzzword stacks, none of "passionate about",
   "leverage", "synergy", "dynamic", "I am writing to", "esteemed organization".
2. Use ONLY facts from CANDIDATE DATA (and COMPANY RESEARCH for company facts). Never invent
   employers, numbers, tools, dates, salary, or achievements. If the question needs a fact that
   is not in the data (e.g. notice period, CTC) write it as a [bracketed placeholder] to fill in.
3. Be specific: name the actual project, tool or result that proves the point. For
   challenge / strength questions build a short situation -> action -> result story ONLY from
   facts and numbers literally present in CANDIDATE DATA (e.g. the 30% query improvement, the
   99.9% uptime, the named project). Do NOT invent incidents, latencies, user counts, causes or
   timelines. If the data holds no real incident, tell the true part briefly and end with
   "[add the specific incident you handled]" so the candidate can fill it in.
4. Length: 60-110 words for normal questions, up to 150 for "tell me about yourself" or story
   questions. For CTC / notice / relocation give 1-3 direct sentences. State only the stored facts; add no extra claims about past experience.
5. When the company is known and research is provided, weave in ONE or TWO concrete, accurate
   company details (what they build, a product, a value) so it clearly isn't generic. Don't flatter.
6. "Why switch" must be positive — growth, scope, learning — never criticise a current employer.
Return only the answer text, no preamble, no quotes, no markdown headings."""


def generate_answer(question: str, context: str, company: str = "", role: str = "",
                    research: dict = None, job_description: str = "") -> dict:
    """Write one answer. Returns {answer} or {error}."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return {"error": "GROQ_API_KEY is not set — add it to .env (free key at console.groq.com)."}
    question = (question or "").strip()
    if not question:
        return {"error": "Paste the question first."}
    if len(re.sub(r"\s", "", context or "")) < 80:
        return {"error": "No candidate details available — upload your resume first."}
    research = research or {}
    user = [f"QUESTION:\n{question}"]
    if company or role:
        user.append(f"TARGET: {role or 'the role'} at {company or 'the company'}")
    if research.get("summary"):
        user.append("COMPANY RESEARCH (web):\n" + research["summary"])
    elif company:
        user.append("COMPANY RESEARCH: none available — do not state specific facts about the company.")
    if (job_description or "").strip():
        user.append("JOB DESCRIPTION:\n" + job_description.strip()[:3000])
    user.append("CANDIDATE DATA:\n" + context)
    try:
        r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json={
            "model": GROQ_MODEL,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": "\n\n".join(user)}],
            "temperature": 0.4,
            "max_tokens": 700,
        }, timeout=_TIMEOUT)
        r.raise_for_status()
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        return {"error": f"Answer generation failed: {e}"}
    text = text.strip().strip('"').strip()
    # Scrub typographic tells that make pasted text look machine-written / break forms.
    for bad, good in (("\u202f", " "), ("\u00a0", " "), ("\u2009", " "), ("\u2011", "-"),
                      ("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"),
                      ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(bad, good)
    text = re.sub(r"(?<=\d)\s+%", "%", text)
    if not text:
        return {"error": "The model returned an empty answer — try again."}
    # Guard against invented specifics: any figure in the answer that appears nowhere in
    # the sources we gave the model is surfaced so the candidate can verify or remove it.
    source_blob = " ".join([question, context, job_description or "", research.get("summary", "")])
    known = set(re.findall(r"\d+(?:\.\d+)?", source_blob))
    unverified = []
    for m in re.finditer(r"\d+(?:\.\d+)?\s?(?:%|ms|seconds?|users?|x|k|lpa|lakhs?|months?|years?|yrs?)?", text, re.I):
        num = re.match(r"\d+(?:\.\d+)?", m.group()).group()
        if num not in known and m.group().strip() not in unverified:
            unverified.append(m.group().strip())
    return {"answer": text, "unverified": unverified[:6]}
