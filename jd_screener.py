"""
JD screener — reads each job's DESCRIPTION (not just its title) and decides whether
it really fits the candidate: skills, experience, salary, role, Java-heaviness,
scam/ghost signals — and how crowded the application pool is likely to be.

It is the single "go inside the job description" gate used by the daily fetcher
(fetch_jobs.py) and, optionally, the live dashboard. Pure heuristics: no API key,
no network, deterministic, fast.

Verdict dict returned by screen_job():
    keep        bool   hard pass/fail
    reason      str    why it was rejected (or a short 'kept' note)
    fit         int    0-100 JD-fit score (skills/experience/salary/role)
    competition str    LOW | MEDIUM | HIGH  (expected applicant crowding)
    boost       int    ranking nudge (-30..+30) to ADD to the job's score
    flags       list   human-readable notes shown with the job
    salary_lpa  float  best-effort stated annual salary in lakh INR (0 = unknown)
    req_years   tuple  (min, max) years the JD asks for, (0, 0) if none stated
"""

import os
import re

# --------------------------------------------------------------------------- #
# CONFIG (override with env vars)
# --------------------------------------------------------------------------- #
USD_TO_INR = float(os.environ.get("USD_TO_INR", "88"))
EUR_TO_INR = float(os.environ.get("EUR_TO_INR", "96"))
GBP_TO_INR = float(os.environ.get("GBP_TO_INR", "112"))
# Reject a job only when its STATED pay is clearly below what you'd accept. Unknown
# salary is never rejected (most Indian postings don't list pay).
MIN_ACCEPT_LPA = float(os.environ.get("MIN_ACCEPT_LPA", "6"))
TARGET_LPA = float(os.environ.get("CURRENT_LPA", "7"))

# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
_MD_ESC = re.compile(r"\\([+\-*_.!()\[\]{}#>~`|\\])")


def _clean(text) -> str:
    """Unescape markdown, drop HTML tags, squash whitespace."""
    t = _MD_ESC.sub(r"\1", str(text or ""))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _has(pattern, text) -> bool:
    return re.search(pattern, text, re.I) is not None


# --------------------------------------------------------------------------- #
# Role gate — titles you actually want
# --------------------------------------------------------------------------- #
# Target roles (user: Backend, SDE-1, Software Engineer, AI Developer, Python Dev,
# Node/NestJS, Full Stack, API). Matched on the TITLE. Bare "engineer"/"developer" is NOT
# enough (that let any "X Engineer" through) — a tech/role qualifier is required.
_ROLE_OK = re.compile(
    r"\b(backend|back[- ]end|server[- ]side|sde[- ]?(?:1|i|2|ii)?\b|swe\b|member\s+of\s+technical\s+staff|mts\b|"
    r"software\s+(?:development\s+)?(?:engineer|developer)|(?:application|web|product|systems?)\s+(?:engineer|developer)|"
    r"python|node(?:\.?js)?|nest(?:\.?js)?|typescript|fastapi|django|flask|"
    r"full[- ]?stack|api\s+(?:engineer|developer)|platform\s+engineer|"
    r"ai\s+(?:engineer|developer|software)|genai|gen[- ]ai|generative\s+ai|llm|"
    r"ml\s+engineer|machine\s+learning\s+engineer|applied\s+(?:ai|ml)|agent(?:ic)?\s+(?:engineer|developer)|"
    r"prompt\s+engineer|rag\s+(?:engineer|developer)|"
    r"(?:associate|junior|jr\.?|graduate)\s+(?:software\s+)?(?:engineer|developer)|"
    r"(?:engineer|developer)\s*(?:-|–)?\s*(?:1|i|ii)\b)", re.I)
# Engineering-core words: when present, functional words like "Network" / "Support" in the
# rest of the title ("Backend Engineer - Network Services") are NOT a reason to reject.
_ROLE_CORE = re.compile(r"\b(backend|back[- ]end|software|sde|swe|full[- ]?stack|python|node|nest|typescript|ai|llm|genai)\b", re.I)
# Wrong function — skipped when an engineering-core word is in the title.
_ROLE_FUNC_BAD = re.compile(
    r"\b(sales|marketing|recruit\w*|hr\b|human\s+resources|accountant|customer\s+(?:support|success)|"
    r"support\s+engineer|technical\s+support|helpdesk|help\s+desk|devops|sre\b|site\s+reliability|network|"
    r"embedded|firmware|hardware|mechanical|electrical|civil|business\s+analyst|"
    r"data\s+analyst|power\s+bi|tableau|content\s+writer|designer|ui/ux)\b", re.I)
# Wrong stack / function — always rejected.
_ROLE_ALWAYS_BAD = re.compile(
    r"\b(qa\b|quality\s+assurance|test\s+engineer|in\s+test\b|sdet|manual\s+test|"
    r"salesforce|sap\b|servicenow|mainframe|cobol|wordpress|pega|shopify|guidewire|mulesoft|etl|snowflake|"
    r"android|ios\b|flutter|react\s+native|blockchain|solidity|field\s+service|"
    r"ruby|rails|scala|rust\b)\b", re.I)
# Seniority — exempted by a junior marker.
_ROLE_LEVEL_BAD = re.compile(
    r"\b(manager|director|head\s+of|vp\b|principal|distinguished|architect|lead\b|"
    r"staff\s+(?:software|engineer|developer|backend)|^staff\b|senior|sr\.?\s|sde[- ]?(?:3|iii|4)|"
    r"intern(?:ship)?\b|trainee|fresher|apprentice)", re.I)
# Symbol-bearing stacks can't sit inside the \b(...)\b groups above.
_ROLE_BAD2 = re.compile(r"(\.net\b|dotnet|\bc#|\bphp\b|\bc\+\+|\bcpp\b)", re.I)
_JUNIOR_OK = re.compile(r"\b(junior|jr\.?|entry[- ]level|associate|sde[- ]?(?:1|i)\b|sde1|"
                        r"software\s+engineer\s*(?:-|–)?\s*(?:1|i)\b|engineer\s*(?:-|–)?\s*i\b|"
                        r"developer\s*(?:-|–)?\s*i\b|level\s*1|l1\b|graduate\s+engineer)\b", re.I)


def role_rejection(title: str):
    """Reason string if the TITLE is not a target role, else None."""
    t = re.sub(r"member\s+of\s+technical\s+staff|\bmts\b", "swe", title, flags=re.I)
    if _ROLE_BAD2.search(t) or _ROLE_ALWAYS_BAD.search(t):
        return f"wrong role/stack: '{title}'"
    if _ROLE_FUNC_BAD.search(t) and not _ROLE_CORE.search(t):
        return f"wrong function: '{title}'"
    if _ROLE_LEVEL_BAD.search(t) and not (_JUNIOR_OK.search(t) and not re.search(
            r"intern|trainee|fresher|apprentice|manager|director|principal|head\s+of", t, re.I)):
        return f"wrong level: '{title}'"
    return None


# --------------------------------------------------------------------------- #
# Java handling — the candidate knows Java but wants LESS of it
# --------------------------------------------------------------------------- #
_JAVA_TITLE = re.compile(r"\bjava\b(?!\s*script)", re.I)
_JAVA_BODY = re.compile(r"\b(?:core\s+)?java\b(?!\s*script)|\bspring\s*boot\b|\bhibernate\b|\bj2ee\b|\bjsp\b|\bmaven\b", re.I)
# NOTE: no bare "go" / "rag" / "express" here — they are ordinary English words and made
# Java-primary JDs look "mixed" ("go beyond", "rag", "express interest").
_NONJAVA_STACK = re.compile(r"\b(node(?:\.?js)?|nest(?:\.?js)?|express\.?js|typescript|python|fastapi|django|flask|"
                            r"golang|llm|langchain|langgraph|retrieval[- ]augmented|genai|generative\s+ai|ai\s+agents?|"
                            r"machine\s+learning)\b", re.I)


def java_profile(title: str, text: str) -> str:
    """'primary' = Java is THE stack (reject), 'mixed' = Java alongside Node/Python
    (small penalty), 'none'."""
    t_java = bool(_JAVA_TITLE.search(title))
    t_other = bool(_NONJAVA_STACK.search(title))
    body_java = len(_JAVA_BODY.findall(text))
    body_other = len(_NONJAVA_STACK.findall(text))
    if t_java and not t_other:
        return "primary"
    if body_java == 0:
        return "none"
    if body_java >= 3 and body_other == 0:
        return "primary"
    if body_java >= 3 and body_java > body_other * 2:
        return "primary"
    return "mixed"


# --------------------------------------------------------------------------- #
# Experience requirement
# --------------------------------------------------------------------------- #
_NUM = r"(\d{1,2}(?:\.\d)?)"
_RANGE = re.compile(_NUM + r"\s*(?:-|–|—|to)\s*" + _NUM + r"\s*\+?\s*(?:years?|yrs?)\b", re.I)
_PLUS = re.compile(_NUM + r"\s*\+\s*(?:years?|yrs?)\b", re.I)
_SINGLE = re.compile(_NUM + r"\s*(?:years?|yrs?)\b", re.I)
_EXP_CTX = re.compile(r"(exp|experience|background|proficien|hands[- ]on|working|worked|developing|building)", re.I)
# Only TEMPORAL company-history phrasing disqualifies a number ("founded 8 years ago",
# "10 years in business"); "5 years in Java" / "3 years of experience with X" are real asks.
_NOT_REQ = re.compile(r"(founded|established|since\b|\bago\b|in business|in\s+the\s+market|years\s+old|cagr|revenue|funding|series\s+[a-d]\b)", re.I)
_SECONDARY = re.compile(r"(preferred|bonus|nice[- ]to[- ]have|good to have|added advantage|\bplus\b)", re.I)
_STRONG = re.compile(r"(total|overall|minimum|\bmin\b\.?|at least|required|experience\s*[:\-–])", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_WORDNUM_RX = re.compile(r"\b(" + "|".join(_WORDNUM) + r")\b(?=\s*(?:\+\s*)?(?:to\s+\w+\s+|-\s*\w+\s*)?(?:years?|yrs?)\b)", re.I)


def _n(x):
    """'2.5' -> 2.5, '3' / '3.0' -> 3 (so labels read 'needs 3+ yrs', not '3.0')."""
    f = float(x)
    return int(f) if f == int(f) else f


def too_senior(lo, hi, candidate_years) -> bool:
    """True when a JD asks for more experience than you should apply for. The cap is your
    years + 1 (2 yrs -> 3). Neither the floor NOR the top of a range may pass it, so
    '1-4' / '2-5' / '3-5' / '4+' are out while '1-2' / '2-3' / '2.5' / '3' / '3+' stay."""
    if not lo and not hi:
        return False
    cap = (candidate_years or 2) + 1
    return (lo or 0) > cap or (hi or 0) > cap


_TITLE_YRS = re.compile(_NUM + r"(?:\s*(?:-|–|—|to)\s*" + _NUM + r")?\s*\+?\s*(?:years?|yrs?)\b", re.I)


def _title_years(title: str):
    """(lo, hi) from an explicit 'N years' / 'N to M years' written in the job TITLE, else (0, 0)."""
    m = _TITLE_YRS.search(title or "")
    if not m:
        return (0, 0)
    a = _n(m.group(1))
    b = _n(m.group(2)) if m.group(2) else a
    return (a, b) if a <= b <= 25 else (0, 0)


def required_years(text: str):
    """(min, max) years of experience the JD asks for for THE ROLE. (0, 0) if none.

    Counts only numbers near experience wording; skips company-history phrasing and
    'preferred / nice to have' mentions; when several figures appear (overall vs per-skill)
    prefers an 'overall / minimum / required / Experience:' one, else the FIRST stated."""
    t = _clean(text)
    t = _WORDNUM_RX.sub(lambda m: str(_WORDNUM[m.group(1).lower()]), t)
    cands = []                                   # (pos, lo, hi)
    taken = []
    for m in _RANGE.finditer(t):
        a, b = _n(m.group(1)), _n(m.group(2))
        if a <= b <= 25:
            cands.append((m.start(), a, b)); taken.append((m.start(), m.end()))
    for rx in (_PLUS, _SINGLE):
        for m in rx.finditer(t):
            if any(s <= m.start() < e for s, e in taken):
                continue
            n = _n(m.group(1))
            if 0 <= n <= 25:
                cands.append((m.start(), n, n)); taken.append((m.start(), m.end()))
    good = []
    for pos, lo, hi in cands:
        seg = t[max(0, pos - 60): pos + 70]
        if not _EXP_CTX.search(seg):
            continue
        if _NOT_REQ.search(t[max(0, pos - 40): pos + 25]):
            continue
        if _SECONDARY.search(t[max(0, pos - 40): pos]):
            continue
        good.append((pos, lo, hi))
    if not good:
        return (0, 0)
    good.sort()
    strong = [g for g in good if _STRONG.search(t[max(0, g[0] - 40): g[0]])]
    _p, lo, hi = (strong or good)[0]
    return (lo, hi)


def fold_experience_range(row: dict) -> dict:
    """Naukri (via jobspy) ships the experience ask in a separate `experience_range`
    field ("5-10 Yrs") and NOT in the description, so every Naukri job read as
    "no req stated" and 5+ yr roles leaked into a 2-yr feed. Prepend it to the
    description as an explicit 'Experience:' line so every screener sees it."""
    rng = str(row.get("experience_range") or "").strip()
    if rng and rng.lower() not in ("nan", "none"):
        if not re.search(r"yr|year", rng, re.I):
            rng += " years"
        desc = str(row.get("description") or "")
        if rng not in desc:
            row["description"] = f"Experience: {rng}. {desc}"
    return row


# --------------------------------------------------------------------------- #
# Salary parsing (best effort → annual lakh INR)
# --------------------------------------------------------------------------- #
# Units must END at a word boundary — otherwise the "m" of "monthly" reads as millions.
# (Million is intentionally NOT a salary unit: "$5 million Series A" is not pay.)
_AMT = r"(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s*(k|l|lpa|lac|lacs|lakh|lakhs|cr|crore)?(?![a-z])"
_INR_SYM = r"(?:₹|(?<![a-z])rs\.?|(?<![a-z])inr)\s*"
_PERIOD_GAP = r"(?:\s*(?:/|per)\s*(?:hr|hour|month|mo|yr|year|annum))?"
_PAT_LPA = re.compile(r"(?:" + _INR_SYM + r")?" + _AMT + r"\s*(?:-|–|—|to)\s*" + _AMT +
                      r"\s*(lpa|lac|lacs|lakh|lakhs|l\.p\.a|ctc|l)(?![a-z])", re.I)
_PAT_LPA_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*(lpa|l\.p\.a|lakhs?|lacs?)(?![a-z])", re.I)
# "Rs 80,000 per month" / "₹ 9 lakh per annum" — single figure with an explicit period
_PAT_INR_SINGLE = re.compile(_INR_SYM + _AMT + r"\s*(?=(?:per|/|a)\s*(?:month|annum|year|yr|mo)|monthly|pm\b|pa\b|p\.a)", re.I)
_PAT_USD_RANGE = re.compile(r"(\$|usd\s*|us\$)\s*" + _AMT + _PERIOD_GAP + r"\s*(?:-|–|—|to)\s*(?:\$|usd\s*)?" + _AMT, re.I)
_PAT_EUR_RANGE = re.compile(r"(€|eur\s*)\s*" + _AMT + _PERIOD_GAP + r"\s*(?:-|–|—|to)\s*(?:€|eur\s*)?" + _AMT, re.I)
_PAT_GBP_RANGE = re.compile(r"(£|gbp\s*)\s*" + _AMT + _PERIOD_GAP + r"\s*(?:-|–|—|to)\s*(?:£|gbp\s*)?" + _AMT, re.I)
_PAT_INR_RANGE = re.compile(_INR_SYM + _AMT + r"\s*(?:-|–|—|to)\s*(?:" + _INR_SYM + r")?" + _AMT, re.I)
# "CTC: 15,00,000 - 20,00,000" (no rupee symbol, but explicit pay wording)
_PAT_PLAIN_RANGE = re.compile(r"(?:salary|ctc|package|compensation|remuneration)\b[^0-9₹$€£]{0,25}" + _AMT +
                              r"\s*(?:-|–|—|to)\s*" + _AMT, re.I)
_SAL_WORD = re.compile(r"(salary|ctc|package|compensation|remuneration|\bpay\b|up\s*to|upto|range|offer|lpa)", re.I)
_NON_SAL = re.compile(r"(insurance|bonus|variable|revenue|funding|raised|stipend|joining|referral|reimburs|allowance|esop|"
                      r"gratuity|relocation|turnover|valuation)", re.I)


def _num(raw: str, unit: str, default_unit: str = "") -> float:
    v = float(str(raw).replace(",", ""))
    u = (unit or default_unit or "").lower()
    if u == "k":
        v *= 1_000
    elif u in ("l", "lpa", "lac", "lacs", "lakh", "lakhs"):
        v *= 100_000
    elif u in ("cr", "crore"):
        v *= 10_000_000
    return v


def _period_factor(ctx: str) -> float:
    """Multiplier to annualise based on wording right after the figure."""
    c = ctx.lower()
    if re.search(r"(?:\bper|/|\ban?)\s*(?:month|mo)\b|\bmonthly\b|/month", c):
        return 12.0
    if re.search(r"(?:\bper|/|\ban?)\s*(?:hour|hr)\b|\bhourly\b", c):
        return 2000.0
    if re.search(r"(?:\bper|/)\s*day\b|\bdaily\b", c):
        return 240.0
    return 1.0


def _salary_context(t: str, m) -> bool:
    """True if a match sits in pay wording and not in perks/funding wording."""
    before = t[max(0, m.start() - 45): m.start()]
    around = t[max(0, m.start() - 60): m.end() + 40]
    if _NON_SAL.search(before):
        return False
    return bool(_SAL_WORD.search(around))


def salary_lpa(text: str, row=None) -> float:
    """Best-effort ANNUAL salary in lakh INR from structured fields or JD text.
    Returns the UPPER end of a stated range. 0.0 when unknown/ambiguous."""
    row = row or {}
    try:
        mx = float(row.get("max_amount") or 0) or float(row.get("min_amount") or 0)
    except (TypeError, ValueError):
        mx = 0.0
    if mx > 0:
        interval = str(row.get("interval") or row.get("salary_interval") or "").lower()
        cur = str(row.get("currency") or "").upper()
        ann = mx * (12 if "month" in interval else 2000 if "hour" in interval else 240 if "day" in interval else 1)
        if cur in ("INR", "") and ann >= 100_000:
            return round(ann / 100_000, 1)
        for c, fx in (("USD", USD_TO_INR), ("EUR", EUR_TO_INR), ("GBP", GBP_TO_INR)):
            if cur == c and ann >= 10_000:
                return round(ann * fx / 100_000, 1)

    t = _clean(text)
    best = 0.0
    lakh_spans = []
    m = _PAT_LPA.search(t)
    if m and not _NON_SAL.search(t[max(0, m.start() - 45): m.start()]):
        a = _num(m.group(1), m.group(2) or m.group(5), "l")
        b = _num(m.group(3), m.group(4) or m.group(5), "l")
        hi = max(a, b)
        best = max(best, hi / 100_000 if hi >= 1000 else hi)
        lakh_spans.append((m.start(), m.end()))
    for m in _PAT_LPA_SINGLE.finditer(t):
        v = float(m.group(1))
        explicit_lpa = m.group(2).lower().replace(".", "") == "lpa"
        if 1 <= v <= 150 and not _NON_SAL.search(t[max(0, m.start() - 45): m.start()]) \
                and (explicit_lpa or _salary_context(t, m)):
            best = max(best, v)
            lakh_spans.append((m.start(), m.end()))
    for pat in (_PAT_INR_RANGE, _PAT_PLAIN_RANGE):
        m = pat.search(t)
        if m and not any(s <= m.start() < e or m.start() <= s < m.end() for s, e in lakh_spans) \
                and (pat is _PAT_PLAIN_RANGE or _salary_context(t, m) or _period_factor(t[m.end(): m.end() + 25]) != 1.0):
            g = m.groups()
            a = _num(g[0], g[1]); b = _num(g[2], g[3])
            hi = max(a, b) * _period_factor(t[m.end(): m.end() + 25])
            if hi >= 100_000:
                best = max(best, hi / 100_000)
    m = _PAT_INR_SINGLE.search(t)
    if m and not _NON_SAL.search(t[max(0, m.start() - 45): m.start()]):
        hi = _num(m.group(1), m.group(2)) * _period_factor(t[m.end(): m.end() + 25])
        if hi >= 100_000:
            best = max(best, hi / 100_000)
    for rx, fx in ((_PAT_USD_RANGE, USD_TO_INR), (_PAT_EUR_RANGE, EUR_TO_INR), (_PAT_GBP_RANGE, GBP_TO_INR)):
        m = rx.search(t)
        if m and not _NON_SAL.search(t[max(0, m.start() - 45): m.start()]):
            a = _num(m.group(2), m.group(3)); b = _num(m.group(4), m.group(5))
            hi = max(a, b)
            f = _period_factor(t[m.start(): m.end() + 25])
            if f == 1.0 and hi < 1000:             # "$60-90k" written as "$60-90"
                hi *= 1000
            hi *= f
            if hi >= 10_000:
                best = max(best, hi * fx / 100_000)
    return round(best, 1)


# --------------------------------------------------------------------------- #
# Scam / ghost-job signals
# --------------------------------------------------------------------------- #
# Scam rules require CANDIDATE-PAYS / off-platform phrasing so ordinary fintech/platform
# JDs ("process payments", "data entry validation", "pay the vendor") are not rejected.
_SCAM = re.compile(
    r"((?:registration|security|refundable|training|processing|documentation|onboarding)\s+(?:fee|deposit|charges?)|"
    r"(?:you|candidate)s?\s+(?:will|must|need\s+to|have\s+to|should)\s+pay|pay\s+(?:a\s+|the\s+)?(?:fee|amount|deposit)\s+(?:to|for)\s+(?:get|secure|confirm|join)|"
    r"buy\s+(?:a\s+)?(?:kit|laptop)\s+(?:from|through)\s+(?:us|the\s+company)|"
    r"earn\s+(?:rs\.?|₹)?\s*\d+[,\d]*\s*(?:per|/)\s*(?:day|week)|"
    r"(?:whatsapp|telegram)\s+(?:us|only|your\s+(?:resume|cv)|id|channel)|wa\.me/|t\.me/|"
    r"work\s+from\s+home\s+typing|typing\s+job|copy\s*paste\s+(?:job|work)|"
    r"no\s+interview|guaranteed\s+(?:job|placement)|100%\s+placement|unlimited\s+earning|\bmlm\b|network\s+marketing|"
    r"crypto\s+trading\s+job|(?:aadhaar|pan\s+card|bank\s+details|otp)\s+(?:required|needed|to\s+apply))", re.I)
_GHOST = re.compile(
    r"(join\s+our\s+talent\s+(?:pool|network|community)|future\s+(?:positions?|roles?)\b|talent\s+(?:pool|community)\s+(?:for|to\s+be\s+considered)|"
    r"future\s+(?:opportunities|openings)|evergreen\s+(?:role|requisition|posting|position|job)|"
    r"pipeline\s+(?:role|requisition)|always\s+hiring|continuous(?:ly)?\s+hiring|"
    r"submit\s+your\s+resume\s+for\s+future|general\s+application)", re.I)
# Consultancies / staffing re-posting the same JD to many boards = very crowded pool.
_STAFFING = re.compile(
    r"(staffing|consultanc|consulting\s+pvt|manpower|recruitment|placement|talent\s+acquisition|"
    r"hiring\s+for\s+(?:our\s+)?client|on\s+behalf\s+of\s+(?:our\s+)?client|"
    r"\bteamlease\b|\brandstad\b|\badecco\b|\bmanpowergroup\b|\bquess\b|\bcrossover\b|"
    r"\bpeople\s*strong\b|walk[- ]?in\s+drive|mega\s+hiring|hiring\s+drive)", re.I)

# --------------------------------------------------------------------------- #
# Competition model
# --------------------------------------------------------------------------- #
# Where the posting was found says a lot about how many people will apply.
#   LOW    – posted directly on the company's own ATS (Greenhouse/Lever/Ashby/...),
#            or in niche feeds few candidates monitor.
#   HIGH   – LinkedIn / Indeed / Naukri / Glassdoor easy-apply boards (hundreds of
#            applicants within hours), or staffing-agency reposts.
_LOW_SITES = ("greenhouse", "lever", "ashby", "workable", "recruitee", "smartrecruiters",
              "breezy", "personio", "teamtailor", "bamboohr", "pinpoint", "rippling", "keka",
              "zoho recruit", "freshteam", "darwinbox", "career page",
              "hacker news", "hn who", "ycombinator", "work at a startup", "wellfound",
              "cutshort", "hirist", "himalayas", "remote rocketship", "working nomads",
              "remoteyeah", "dynamite", "justremote", "jobspresso", "nodesk", "startup.jobs",
              "arc.dev", "wttj", "welcome to the jungle", "otta", "reddit", "github")
_HIGH_SITES = ("linkedin", "indeed", "naukri", "glassdoor", "zip_recruiter", "ziprecruiter",
               "foundit", "monster", "shine", "timesjobs", "bayt", "google")


def competition_level(row: dict, text: str, days_old: float, employees: int, staffing: bool):
    """Returns (level, boost, notes)."""
    site = str(row.get("site") or "").lower()
    notes, pts = [], 0
    if any(s in site for s in _LOW_SITES):
        pts += 2; notes.append("direct/niche source — few applicants")
    elif any(s in site for s in _HIGH_SITES):
        pts -= 1
    if staffing:
        pts -= 2; notes.append("staffing/consultancy repost — crowded")
    if days_old >= 900:
        pass                                   # unknown date: neutral, not "stale"
    elif days_old <= 1:
        pts += 2; notes.append("posted <24h — apply early")
    elif days_old <= 3:
        pts += 1
    elif days_old > 14:
        pts -= 1
    if 0 < employees < 200:
        pts += 1; notes.append("small company")
    # "Be among the first N applicants" style text sometimes survives scraping.
    # Real LinkedIn counts when the fetcher enriched the row: "Be among the first 25
    # applicants" / "Over 200 applicants" / "37 applicants" / "Clicked apply 120 times".
    m = re.search(r"(?:first|under|less\s+than|fewer\s+than)\s+(\d{1,3})\s+applicants", text, re.I)
    if m and int(m.group(1)) <= 50:
        pts += 3; notes.append(f"early-applicant window (<{m.group(1)})")
    else:
        m = re.search(r"(?:over|more\s+than)?\s*(\d{1,4})\+?\s+(?:applicants|people\s+clicked\s+apply)", text, re.I)
        if m:
            n = int(m.group(1))
            if n >= 200:
                pts -= 4; notes.append(f"{n}+ applicants already")
            elif n >= 100:
                pts -= 3; notes.append(f"{n}+ applicants already")
            elif n <= 30:
                pts += 2; notes.append(f"only {n} applicants so far")
    if pts >= 3:
        return "LOW", min(15, 5 + pts * 2), notes
    if pts <= -1:
        return "HIGH", max(-8, pts * 3), notes
    return "MEDIUM", pts * 2, notes


# --------------------------------------------------------------------------- #
# Geography — you apply from India
# --------------------------------------------------------------------------- #
_INDIA_TOK = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|delhi|ncr|noida|gurgaon|gurugram|hyderabad|pune|chennai|"
    r"kolkata|ahmedabad|jaipur|indore|chandigarh|kochi|coimbatore|nagpur|lucknow|thiruvananthapuram|"
    r"vadodara|mysuru|mysore|bhubaneswar|remote\s*\(?\s*india)\b", re.I)
_GLOBAL_TOK = re.compile(r"\b(worldwide|anywhere|global(?:ly)?|apac|asia|any\s+location|work\s+from\s+anywhere)\b", re.I)
_FOREIGN_TOK = re.compile(
    r"(united\s+states|\busa\b|\bu\.s\.a?\b|\bus\b|canada|\buk\b|united\s+kingdom|europe|\beu\b|emea|latam|"
    r"latin\s+america|germany|france|spain|netherlands|poland|ireland|portugal|romania|australia|new\s+zealand|"
    r"singapore|dubai|\buae\b|israel|brazil|mexico|argentina|colombia|new\s+york|san\s+francisco|seattle|austin|"
    r"boston|chicago|los\s+angeles|london|berlin|toronto|vancouver|sydney|nigeria|kenya|south\s+africa|"
    r"philippines|japan|china|korea)", re.I)
# JD text that bars an India-based candidate outright.
_GEO_BLOCK = re.compile(
    r"((?:must|should)\s+(?:be\s+)?(?:located|based|reside|living)\s+in\s+(?:the\s+)?(?:us|usa|united\s+states|uk|eu|canada|europe)|"
    r"authori[sz]ed\s+to\s+work\s+in\s+(?:the\s+)?(?:us|united\s+states|uk|canada|eu)|"
    r"(?:us|usa|u\.s\.|uk|eu|canada)[- ]only|(?:us|u\.s\.)\s+(?:citizens?|residents?)|"
    r"work\s+authori[sz]ation\s+(?:in\s+the\s+(?:us|uk)\s+)?(?:is\s+)?required|green\s+card|"
    r"must\s+work\s+(?:in\s+)?(?:est|pst|cst|pacific|eastern)\s+(?:time|hours))", re.I)


def geo_ok(location: str, text: str = "") -> bool:
    """False when the posting is clearly NOT open to someone in India."""
    loc = str(location or "")
    if not loc.strip() or loc.strip() in ("—", "-", "N/A"):
        return not _GEO_BLOCK.search(text or "") or bool(_INDIA_TOK.search(text or ""))
    if _INDIA_TOK.search(loc) or _GLOBAL_TOK.search(loc):
        return True
    if _FOREIGN_TOK.search(loc):
        # a foreign-looking location field can still be an India-hiring remote role
        return bool(re.search(r"(remote|located|based|hiring|open)[^.]{0,40}india|india[^.]{0,40}(remote|based|hiring)",
                              text or "", re.I))
    return not (_GEO_BLOCK.search(text or "") and not _INDIA_TOK.search(text or ""))


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def _days_old(date_posted) -> float:
    import datetime as dt
    s = str(date_posted or "").strip()[:10]
    try:
        d = dt.datetime.strptime(s, "%Y-%m-%d").date()
        return max(0.0, (dt.date.today() - d).days)
    except ValueError:
        return 999.0


_GENERIC_SKILLS = {"git", "sql", "html", "css", "go", "vs code", "postman", "agile/scrum", "mvc",
                   "linux/unix", "javascript", "ci/cd pipelines", "github actions", "jenkins"}


def screen_job(job: dict, candidate_years: int = 2, skills=None, strict_role: bool = True) -> dict:
    """Judge one job posting from its title + full description."""
    title = _clean(job.get("title"))
    desc = _clean(job.get("description"))
    blob = f"{title}. {desc}"
    company = _clean(job.get("company"))
    flags = []
    jd_read = len(desc) >= 200          # a real description, not just a title/snippet
    out = {"keep": True, "reason": "ok", "fit": 50, "jd_read": jd_read, "competition": "MEDIUM", "boost": 0,
           "flags": flags, "salary_lpa": 0.0, "req_years": (0, 0)}

    def reject(reason):
        out.update(keep=False, reason=reason)
        return out

    # --- scam / ghost ------------------------------------------------------- #
    if _SCAM.search(blob):
        return reject("scam signals (fee/WhatsApp/guaranteed placement)")
    if _GHOST.search(blob):
        return reject("ghost posting (talent pool / evergreen / future openings)")

    # --- geography: must be doable from India ------------------------------- #
    # Rows with no location field (Hacker News one-liners: "Acme | ML Engineer | Boston |
    # REMOTE (US)") carry it in the title / first line instead — check that text too.
    loc_field = job.get("location")
    if not str(loc_field or "").strip() or str(loc_field).strip() in ("—", "-"):
        head = f"{title} {desc[:200]}"
        if (_FOREIGN_TOK.search(head) or re.search(r"\bon-?site\b", head, re.I)) and not (_INDIA_TOK.search(head) or _GLOBAL_TOK.search(head)):
            return reject("not open to India (location in posting header)")
    if not geo_ok(job.get("location"), blob):
        return reject(f"not open to India (location: {job.get('location') or 'restricted in JD'})")

    # --- role --------------------------------------------------------------- #
    bad = role_rejection(title)
    if bad:
        return reject(bad)
    if strict_role and not _ROLE_OK.search(title):
        return reject(f"title not in target roles: '{title}'")

    # --- experience --------------------------------------------------------- #
    lo, hi = required_years(blob)
    # Postings often put the ask in the TITLE ("Angular Developer | 9 to 12 years | Pune"),
    # where there is no "experience" word nearby for required_years() to anchor on.
    t_lo, t_hi = _title_years(title)
    if t_hi and t_hi > (lo if not hi else hi):
        lo, hi = t_lo, t_hi
    out["req_years"] = (lo, hi)
    # A "0-5 years" style range has a falsy floor, so it must be checked before `if lo:`.
    if too_senior(lo, hi, candidate_years):
        return reject(f"needs {lo}{'-' + str(hi) if hi and hi != lo else '+'} yrs (you have {candidate_years})")
    fit = 55
    # Fresher-level postings ("0-1 years", "freshers only") are below your experience —
    # checked OUTSIDE `if lo:` because a 0 floor is falsy.
    if candidate_years >= 2 and ((lo == 0 and hi == 1) or re.search(r"\bfreshers?\s+only\b|0\s*-\s*6\s+months", blob, re.I)):
        return reject(f"fresher-level ({lo}-{hi} yrs) — below your experience")
    if lo:
        if too_senior(lo, hi, candidate_years):
            return reject(f"needs {lo}{'-' + str(hi) if hi and hi != lo else '+'} yrs (you have {candidate_years})")
        if lo <= candidate_years:
            fit += 15
            if hi and lo and hi <= candidate_years + 1 and hi != lo:
                fit += 5; flags.append(f"tight {lo}-{hi}yr range matches you")
            flags.append(f"exp ok ({lo}+ vs your {candidate_years})")
        else:
            fit += 4; flags.append("1-yr experience stretch")
    elif jd_read:
        fit += 8                          # JD read and it states no experience ask
    else:
        fit -= 6                          # JD never read: requirement is unverified, no bonus
        flags.append("JD not read — verify experience/skills")
    if _JUNIOR_OK.search(title):
        fit += 6; flags.append("junior/SDE-1 level")

    # --- Java ---------------------------------------------------------------- #
    jp = java_profile(title, blob)
    if jp == "primary":
        return reject("Java-primary role (you want less Java)")
    if jp == "mixed":
        fit -= 6; out["boost"] -= 6; flags.append("mentions Java (secondary)")

    # --- salary -------------------------------------------------------------- #
    lpa = salary_lpa(blob, job)
    out["salary_lpa"] = lpa
    if lpa:
        if lpa < MIN_ACCEPT_LPA:
            return reject(f"pays ~{lpa} LPA (< your {MIN_ACCEPT_LPA} LPA floor)")
        if lpa >= TARGET_LPA:
            fit += min(12, int((lpa - TARGET_LPA) * 2) + 4)
            out["boost"] += min(10, int(lpa - TARGET_LPA) + 3)
            flags.append(f"pays ~{lpa} LPA")
        else:
            flags.append(f"pays ~{lpa} LPA")
    # --- skills -------------------------------------------------------------- #
    if skills:
        low = " " + blob.lower() + " "
        hits = [s for s in skills if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", low)]
        n = len(set(hits))
        # Generic tools every dev lists don't prove a fit; a JD that was actually read and
        # names NONE of your real stack is a different job — drop it.
        core = [h for h in set(hits) if h.lower() not in _GENERIC_SKILLS]
        if jd_read and len(desc) >= 300 and not core:
            return reject("JD read: none of your core skills are mentioned")
        fit += min(20, n * 3)
        if n:
            flags.append(f"{n} of your skills in JD")

    # --- competition --------------------------------------------------------- #
    staffing = bool(_STAFFING.search(f"{company} {desc[:600]}"))
    emp_raw = str(job.get("company_num_employees") or "")
    nums = re.findall(r"\d+", emp_raw.replace(",", ""))
    employees = int(nums[0]) if nums else 0
    level, cboost, cnotes = competition_level(job, blob, _days_old(job.get("date_posted")), employees, staffing)
    out["competition"] = level
    out["boost"] += cboost
    flags.extend(cnotes)

    out["fit"] = max(0, min(100, fit))
    out["boost"] = max(-30, min(30, out["boost"]))
    return out
