"""
Job Fit Analyzer - Deep analysis of each job to predict interview callback likelihood.

For each of the TOP 50 jobs, this agent uses Groq (free) to:
1. Analyze company, role, requirements
2. Compare against candidate profile
3. Score: "Interview Likelihood" (0-100%)
4. Recommend: "APPLY NOW", "Good Fit", "Maybe"
5. Provide insights: What to emphasize, red flags, growth potential

Uses Groq free API (mixtral-8x7b-32768) for cron compatibility.
"""

import os
import json

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

groq_client = None
if GROQ_AVAILABLE:
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        groq_client = Groq(api_key=groq_key)

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
    Analyze a single job to predict interview likelihood using Groq (free API).

    Returns analysis dict with interview_likelihood (0-100), fit_level, highlights, etc.
    """
    if not groq_client:
        return {
            "interview_likelihood": 50,
            "fit_level": "MAYBE",
            "why_call": "Groq API not available",
        }

    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    description = job.get("description", "")
    salary_min = job.get("min_amount", "")
    salary_max = job.get("max_amount", "")

    if not description or len(description) < 100:
        return {
            "interview_likelihood": 30,
            "fit_level": "MAYBE",
            "key_matches": [],
            "skill_gaps": [],
            "resume_highlights": [],
            "red_flags": ["Incomplete job description"],
            "growth_potential": "MEDIUM",
            "why_call": "Not enough data",
            "company_type": "unknown",
            "salary_bracket": "unknown",
        }

    prompt = f"""Analyze this job for a 2-year backend developer (Python/Node.js/Java):

ROLE: {title}
COMPANY: {company}
LOCATION: {location}
SALARY: {salary_min}-{salary_max}

JOB DESCRIPTION:
{description[:1500]}

Respond with ONLY JSON (no markdown):
{{
  "interview_likelihood": 0-100,
  "fit_level": "APPLY_NOW" | "GOOD_FIT" | "MAYBE" | "SKIP",
  "key_matches": ["skill1"],
  "skill_gaps": ["skill1"],
  "resume_highlights": ["point1"],
  "red_flags": ["flag1"],
  "growth_potential": "HIGH" | "MEDIUM" | "LOW",
  "why_call": "reason",
  "company_type": "startup" | "scaleup" | "enterprise" | "other",
  "salary_bracket": "3-5L" | "5-7L" | "7-9L" | "9-12L" | "12L+"
}}"""

    try:
        message = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )

        response_text = message.choices[0].message.content.strip()

        # Extract JSON
        if response_text.startswith("{"):
            analysis = json.loads(response_text)
        else:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                analysis = json.loads(response_text[start:end])
            else:
                return {"interview_likelihood": 50, "fit_level": "MAYBE"}

        return analysis

    except Exception as e:
        return {
            "interview_likelihood": 50,
            "fit_level": "MAYBE",
            "why_call": f"Analysis error (will retry): {str(e)[:50]}",
        }


def analyze_top_jobs(jobs: list, top_n: int = 50) -> list:
    """
    Analyze top N jobs and add fit analysis to each.
    Returns ALL jobs (analyzed top N first, then rest unannotated).

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

    # Return ALL jobs: top N analyzed + rest unannotated
    analyzed.extend(jobs[top_n:])
    return analyzed
