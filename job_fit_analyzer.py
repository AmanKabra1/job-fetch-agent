"""
Job Fit Analyzer — the STRICT agent that reads each job description and decides whether the
job is genuinely good for Aman, then GATES the feed on it.

Two layers (the LLM alone is not trusted):

  1. Groq LLM (free) reads the JD with a skeptical rubric and must quote evidence from the JD
     for every claim (no guessing, no keyword-stuffing credit, must-haves only).
  2. Deterministic guardrails (jd_screener + resume_keywords) CAP the LLM's score using hard
     facts — years required, India-eligibility, Java-primary, scam/ghost, real skill coverage,
     thin JD — so a flattering answer can never rescue a job that fails a hard rule.

fit_level is derived from the final score, never taken from the LLM:
    >= 75 APPLY_NOW | >= 60 GOOD_FIT | >= 40 MAYBE | < 40 SKIP
The cron drops SKIP jobs (gate_feed). If Groq is down / rate-limited the same rules still score
every job (source = "rules") instead of the old flat "50 / MAYBE".
"""

import os
import re
import json
import time

import jd_screener as JDS

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

groq_client = None
if GROQ_AVAILABLE and os.environ.get("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

MODEL = os.environ.get("FIT_MODEL", "openai/gpt-oss-20b")
CANDIDATE_YEARS = 2
APPLY_NOW, GOOD_FIT, MAYBE = 75, 60, 40
LLM_PAUSE_S = float(os.environ.get("FIT_LLM_PAUSE", "2.2"))     # stay under Groq's free per-minute limits
_BREAKER = {"fails": 0, "open": False}                         # stop calling Groq after repeated failures


# --------------------------------------------------------------------------- #
# Candidate profile (read from resume_profile.py, never hard-coded / stale)
# --------------------------------------------------------------------------- #
def _profile_text() -> str:
    try:
        import resume_profile as P
        core, learning = [], []
        for cat, items in P.SKILLS.items():
            clean = [re.sub(r"\s*\(.*?\)\s*", "", s).strip() for s in items]
            (learning if cat in ("Tools",) else core).extend(clean)
        core = list(dict.fromkeys(core))
        roles = list(dict.fromkeys(j["title"] for j in P.EXPERIENCE))
        return (f"- {CANDIDATE_YEARS} years of professional experience (roles: {', '.join(roles)}); "
                f"B.Tech IT 2024.\n- Skills (the ONLY skills he has): {', '.join(core)}.\n"
                "- Strongest: Node.js / NestJS / TypeScript backends, Python (FastAPI), PostgreSQL/MySQL, Docker, "
                "AWS S3/SES, JWT/RBAC, REST APIs, microservices; also LLM/RAG/LangChain/LangGraph AI agents.\n"
                "- Java/Spring Boot and Go: learning only — he does NOT want Java-centred roles.")
    except Exception:
        return "- 2 years backend (Node.js/NestJS/TypeScript, Python/FastAPI), PostgreSQL, Docker, AWS, LLM/RAG agents."


SYSTEM_PROMPT = """You are a SKEPTICAL technical recruiter screening job postings for ONE candidate. Your job is to REJECT \
jobs that are not a strong fit — most postings should NOT be recommended. Never be generous.

CANDIDATE
{profile}
- Target: India-based or India-eligible remote, SDE-1 / Backend / Software Engineer / Python / Node.js / AI developer, \
2-year level, pay 7-9 LPA (stated pay below 6 LPA is a reject).

RULES — apply in order, quote the JD as evidence:
1. HARD REJECT (hard_reject=true, likelihood<=15) if ANY: the JD requires more than 3 years of experience; senior/lead/\
staff/manager role; internship/fresher-only; Java/.NET/PHP/C++/Salesforce/SAP/DevOps/QA/data-analyst/frontend-only \
centred role; not open to someone in India (US-only, work authorization, on-site abroad); stated pay BELOW 6 LPA (6.0 or more is fine, 6-7 is only a minor negative); \
scam/ghost signals (fees, WhatsApp, talent pool, evergreen).
2. MUST-HAVES = skills in "requirements / must have / responsibilities / looking for". Ignore "nice to have", \
"bonus" and tech merely listed as company stack. A keyword appearing once does NOT make a match.
3. For every MUST-HAVE the candidate lacks, add it to missing_must_haves. Missing 2+ core must-haves => likelihood<=45; \
missing the PRIMARY language/framework => likelihood<=30.
4. Do not assume. If the JD is vague, generic or has no stack/years, set jd_quality="thin" and likelihood<=40.
5. Score bands: 75-100 = nearly every must-have matched AND experience range fits AND role is his target; 60-74 = \
strong but 1 gap; 40-59 = partial, real gaps; below 40 = reject.
6. Be consistent: the same JD must always get the same verdict.

Return ONLY compact JSON, no markdown, no extra text."""

USER_PROMPT = """JOB
Title: {title}
Company: {company}
Location: {location}
Stated pay: {pay}

JOB DESCRIPTION
{jd}

JSON schema (keep every string under 120 chars):
{{"hard_reject": false, "reject_reason": "", "years_required": "e.g. 1-3 or unknown", "role_fit": "target|adjacent|off-target", \
"must_haves": ["..."], "candidate_has": ["..."], "missing_must_haves": ["..."], \
"evidence": ["short quote from the JD supporting your verdict"], "red_flags": ["..."], \
"jd_quality": "good|thin", "interview_likelihood": 0-100, "why": "one sentence", \
"resume_highlights": ["what to emphasise"], "company_type": "startup|scaleup|enterprise|agency|unknown"}}"""


def _jd_window(desc: str, n: int = 6000) -> str:
    """Head + tail: pay and years-of-experience often sit at the END of a JD."""
    d = JDS._clean(desc)
    return d if len(d) <= n else d[: int(n * 0.65)] + " [...] " + d[-int(n * 0.35):]


def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except Exception:
            return None
    return None


def _call_llm(job: dict, desc: str):
    """One strict Groq call with retry/backoff. Returns parsed dict or None."""
    if not groq_client or _BREAKER["open"]:
        return None
    lpa = JDS.salary_lpa(desc, job)          # parsed + currency/period-aware (raw jobspy numbers are ambiguous)
    pay = f"about {lpa} LPA" if lpa else "not stated"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(profile=_profile_text())},
        {"role": "user", "content": USER_PROMPT.format(
            title=job.get("title", ""), company=job.get("company", ""), location=job.get("location", ""),
            pay=pay, jd=_jd_window(desc))},
    ]
    kwargs = dict(model=MODEL, messages=messages, temperature=0.1, max_tokens=3500)
    extras = [{"reasoning_effort": "low", "response_format": {"type": "json_object"}},
              {"reasoning_effort": "low"}, {}]              # drop unsupported options progressively
    for attempt in range(3):
        try:
            resp, last = None, None
            for ex in extras:
                try:
                    resp = groq_client.chat.completions.create(**kwargs, **ex)
                    break
                except TypeError as e:                      # SDK too old for this option
                    last = e
                    continue
                except Exception as e:
                    low = str(e).lower()
                    if ex and any(k in low for k in ("reasoning_effort", "response_format", "json", "unsupported")):
                        last = e                            # model rejects the option: retry without it
                        continue
                    raise
            if resp is None:
                raise last or RuntimeError("no response")
            data = _extract_json(resp.choices[0].message.content)
            if data and "interview_likelihood" in data:
                _BREAKER["fails"] = 0
                return data
            raise ValueError("unparseable / truncated JSON")
        except Exception as e:
            msg = str(e)
            if "tokens per day" in msg.lower() or "TPD" in msg:
                _BREAKER["open"] = True                      # daily quota gone: rules-only for the rest of the run
                print("    ! Groq daily token quota reached — rules-only for the remaining jobs", flush=True)
                return None
            if "429" in msg or "rate" in msg.lower():
                m = re.search(r"try again in ([\d.]+)s", msg)
                time.sleep(min(30, float(m.group(1)) + 1 if m else 4 * (attempt + 1)))
            else:
                time.sleep(1.5)
    _BREAKER["fails"] += 1
    if _BREAKER["fails"] >= 4:
        _BREAKER["open"] = True
        print("    ! Groq failed 4 jobs in a row — rules-only for the remaining jobs", flush=True)
    return None


# --------------------------------------------------------------------------- #
# Deterministic guardrails — facts that cap whatever the LLM says
# --------------------------------------------------------------------------- #
def _rules(job: dict) -> dict:
    """Score a job from hard facts alone. Returns {cap, base, reasons, hard_reject}."""
    desc = JDS._clean(job.get("description"))
    title = JDS._clean(job.get("title"))
    reasons, cap, hard = [], 100, ""
    skills = None
    try:
        import resume_profile as P
        skills = [re.sub(r"\s*\(.*?\)\s*", "", s).strip() for items in P.SKILLS.values() for s in items]
    except Exception:
        pass
    v = JDS.screen_job(job, candidate_years=CANDIDATE_YEARS, skills=skills)
    if not v["keep"]:
        return {"cap": 10, "base": 10, "hard": v["reason"], "reasons": [v["reason"]], "coverage": None}
    thin = len(desc) < 300
    base = v["fit"]
    coverage = None
    if thin:
        cap = min(cap, 40)
        reasons.append("JD missing/too short — cannot verify must-haves")
    else:
        try:
            import resume_keywords as K
            a = K.analyze(desc, title)
            coverage = a["coverage"]
            if coverage < 45:
                cap = min(cap, 35); reasons.append(f"only {coverage}% of the JD's skills are yours")
            elif coverage < 60:
                cap = min(cap, 55); reasons.append(f"{coverage}% skill coverage (gaps: {', '.join(a['gaps'][:3])})")
            elif coverage < 72:
                cap = min(cap, 72); reasons.append(f"{coverage}% skill coverage (gaps: {', '.join(a['gaps'][:3])})")
            base = round(0.55 * coverage + 0.45 * v["fit"])
        except Exception:
            pass
    lo, hi = v["req_years"]
    if lo and lo == CANDIDATE_YEARS + 1:
        cap = min(cap, 62); reasons.append(f"asks {lo}+ yrs (you have {CANDIDATE_YEARS})")
    if v["salary_lpa"] and v["salary_lpa"] < 7:
        cap = min(cap, 70); reasons.append(f"pays ~{v['salary_lpa']} LPA (< your 7 target)")
    return {"cap": cap, "base": min(base, cap), "hard": hard, "reasons": reasons, "coverage": coverage}


def _level(score: int) -> str:
    return "APPLY_NOW" if score >= APPLY_NOW else "GOOD_FIT" if score >= GOOD_FIT else "MAYBE" if score >= MAYBE else "SKIP"


def analyze_job(job: dict, use_llm: bool = True) -> dict:
    """Strict verdict for one job: {interview_likelihood, fit_level, source, why, ...}."""
    desc = str(job.get("description") or "")
    rules = _rules(job)

    if rules["hard"]:                                           # a hard rule failed: no LLM needed
        return {"interview_likelihood": 10, "fit_level": "SKIP", "source": "rules", "hard_reject": True,
                "why": rules["hard"], "red_flags": rules["reasons"], "skill_gaps": [], "key_matches": []}

    llm = _call_llm(job, desc) if (use_llm and len(desc) >= 300) else None
    if llm:
        try:
            likelihood = int(float(llm.get("interview_likelihood", 0)))
        except (TypeError, ValueError):
            likelihood = 0
        if llm.get("hard_reject"):
            likelihood = min(likelihood, 15)
        if llm.get("jd_quality") == "thin":
            likelihood = min(likelihood, 40)
        if str(llm.get("role_fit", "")).lower() == "off-target":
            likelihood = min(likelihood, 35)
        missing = llm.get("missing_must_haves") or []
        if len(missing) >= 2:
            likelihood = min(likelihood, 45)
        final = max(0, min(likelihood, rules["cap"]))
        why = llm.get("why") or llm.get("reject_reason") or ""
        out = {"interview_likelihood": final, "fit_level": _level(final), "source": "ai+rules",
               "hard_reject": bool(llm.get("hard_reject")), "why": why,
               "key_matches": llm.get("candidate_has") or [], "skill_gaps": missing,
               "must_haves": llm.get("must_haves") or [], "years_required": llm.get("years_required", ""),
               "evidence": (llm.get("evidence") or [])[:3], "red_flags": (llm.get("red_flags") or []) + rules["reasons"],
               "resume_highlights": llm.get("resume_highlights") or [], "company_type": llm.get("company_type", "unknown"),
               "jd_quality": llm.get("jd_quality", "good"), "llm_score": likelihood, "rule_cap": rules["cap"]}
        return out

    # Rules can check skills / years / pay / location but NOT whether the role itself fits (an
    # "Embedded Security" job scored 100% on skills). So a rules-only verdict can never reach
    # APPLY_NOW — that needs the AI to have actually read the JD.
    final = min(rules["base"], APPLY_NOW - 3)
    return {"interview_likelihood": final, "fit_level": _level(final), "source": "rules", "hard_reject": False,
            "why": "; ".join(rules["reasons"]) or "rule-based screen (AI unavailable)",
            "red_flags": rules["reasons"], "skill_gaps": [], "key_matches": [], "rule_cap": rules["cap"]}


def analyze_top_jobs(jobs: list, top_n: int = 60, previous: dict = None) -> list:
    """Attach a strict verdict to EVERY job. The LLM is used for at most `top_n` jobs per run
    (and never for a job that already has a verdict from an earlier run — `previous` maps
    job_url -> earlier analysis); the rest get the deterministic rule verdict."""
    previous = previous or {}
    llm_used = reused = 0
    for i, job in enumerate(jobs):
        url = str(job.get("job_url", ""))
        prev = previous.get(url)
        if prev and prev.get("source") == "ai+rules":
            analysis, reused = prev, reused + 1
        else:
            use_llm = llm_used < top_n and not _BREAKER["open"]
            analysis = analyze_job(job, use_llm=use_llm)
            if analysis.get("source") == "ai+rules":
                llm_used += 1
                time.sleep(LLM_PAUSE_S)
        job["_fit_analysis"] = analysis
        job["interview_likelihood"] = analysis["interview_likelihood"]
        job["fit_level"] = analysis["fit_level"]
    print(f"    fit agent: {llm_used} read by AI, {reused} reused from earlier runs, "
          f"{len(jobs) - llm_used - reused} rule-based", flush=True)
    return jobs


def gate_feed(jobs: list) -> tuple:
    """Drop SKIP jobs and nudge the ranking by the verdict. Returns (kept, dropped_count)."""
    kept, dropped = [], 0
    for j in jobs:
        a = j.get("_fit_analysis") or {}
        if a.get("fit_level") == "SKIP":
            dropped += 1
            continue
        lik = a.get("interview_likelihood")
        if isinstance(lik, (int, float)):
            adj = int(round((lik - 50) * 0.3))                  # strong AI verdict floats up, weak sinks (+-15)
            raw = int(j.get("_score_raw", j.get("_match_score", 0)) or 0) + adj
            j["_score_raw"] = raw
            j["_match_score"] = max(0, min(100, raw))
        kept.append(j)
    return kept, dropped
