"""
Job Fit Analyzer - Deep analysis of each job to predict interview callback likelihood.

For each of the TOP 50 jobs, this agent:
1. Analyzes company, role, requirements
2. Compares against candidate profile
3. Scores: "Interview Likelihood" (0-100%)
4. Recommends: "APPLY NOW", "Good Fit", "Maybe"
5. Provides insights: What to emphasize, red flags, growth potential
"""

import json
from anthropic import Anthropic

client = Anthropic()

SYSTEM_PROMPT = """You are a career advisor analyzing job postings for a backend developer.

For each job, provide a JSON analysis with:
{
  "interview_likelihood": 0-100,  // Probability of getting interview call (0=no chance, 100=highly likely)
  "fit_level": "APPLY_NOW" | "GOOD_FIT" | "MAYBE" | "SKIP",
  "key_matches": ["skill1", "skill2"],  // What aligns with candidate
  "skill_gaps": ["skill1"],  // What's missing
  "resume_highlights": ["point1", "point2"],  // What to emphasize in resume
  "red_flags": ["flag1"],  // Any concerns
  "growth_potential": "HIGH" | "MEDIUM" | "LOW",  // Career growth at this company
  "why_call": "reason why they'd likely callback",  // 1-2 sentences
  "company_type": "startup" | "scaleup" | "enterprise" | "other",
  "salary_bracket": "3-5L" | "5-7L" | "7-9L" | "9-12L" | "12L+"  // Expected range for India
}

Base your analysis on:
- Candidate: 2-year backend developer, Python/Node.js/Java, India
- Skills: Python, Node.js, TypeScript, Java, FastAPI, Express, NestJS, Spring Boot, Docker, AWS, PostgreSQL
- Growing: LLM, AI Agents, LangChain, RAG systems
- Target: Remote jobs in India, 7-9 LPA salary range

Be HONEST: If it's not a good fit, score low. If it's perfect, score high.
"""


def analyze_job(job: dict) -> dict:
    """
    Analyze a single job to predict interview likelihood.

    Returns analysis dict with interview_likelihood (0-100), fit_level, highlights, etc.
    """
    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    description = job.get("description", "")
    salary_min = job.get("min_amount", "")
    salary_max = job.get("max_amount", "")

    if not description:
        return {
            "interview_likelihood": 30,
            "fit_level": "MAYBE",
            "key_matches": [],
            "skill_gaps": [],
            "resume_highlights": [],
            "red_flags": ["No job description provided"],
            "growth_potential": "MEDIUM",
            "why_call": "No description to analyze",
            "company_type": "unknown",
            "salary_bracket": "unknown",
        }

    prompt = f"""Analyze this job posting for fit with the candidate profile:

ROLE: {title}
COMPANY: {company}
LOCATION: {location}
SALARY: {salary_min}-{salary_max}

JOB DESCRIPTION:
{description[:2000]}

Provide JSON analysis only (no markdown, no explanation)."""

    try:
        message = client.messages.create(
            model="claude-opus-5",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()

        # Extract JSON
        if response_text.startswith("{"):
            analysis = json.loads(response_text)
        else:
            # Try to find JSON in response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                analysis = json.loads(response_text[start:end])
            else:
                return {"error": "Could not parse response"}

        return analysis

    except Exception as e:
        return {
            "interview_likelihood": 50,
            "fit_level": "MAYBE",
            "why_call": f"Analysis failed: {str(e)[:100]}",
        }


def analyze_top_jobs(jobs: list, top_n: int = 50) -> list:
    """
    Analyze top N jobs and add fit analysis to each.

    Returns jobs with added fields: interview_likelihood, fit_level, resume_highlights, etc.
    """
    analyzed = []

    for i, job in enumerate(jobs[:top_n]):
        print(f"  Analyzing job {i+1}/{min(top_n, len(jobs))}: {job.get('title', 'Unknown')}", flush=True)

        analysis = analyze_job(job)

        # Add analysis to job
        job["_fit_analysis"] = analysis
        job["interview_likelihood"] = analysis.get("interview_likelihood", 50)
        job["fit_level"] = analysis.get("fit_level", "MAYBE")

        analyzed.append(job)

    return analyzed
