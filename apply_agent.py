"""
Auto-fill assistant for job applications on Greenhouse / Lever / Ashby.
========================================================================
These three ATS platforms host a genuinely PUBLIC application form — it's
the same form any applicant fills in their own browser, so opening it and
filling in the standard fields you'd fill anyway is not automating someone
else's private account (unlike LinkedIn Easy Apply / Naukri 1-click, which
act through YOUR logged-in session on THEIR platform and are against those
platforms' terms of service — this project does not automate those).

This deliberately never clicks the final Submit button. Testing against a
real, live Lever posting (Spotify, read-only — no submit) found:
  - an hCaptcha field on the form. Defeating a CAPTCHA would be exactly the
    kind of anti-bot evasion this project won't build.
  - required custom screening questions specific to that job/company (work
    authorization, etc.) that only the applicant can answer honestly.
So the browser opens VISIBLY (headless=False) with the known, generic fields
filled in (name, email, phone, resume, LinkedIn/GitHub links, cover note),
and is left open for the user to review, answer anything custom, solve any
CAPTCHA, and click the real Submit button themselves.

Local-only: this launches a real desktop browser window on whatever machine
runs `python app.py`. It makes no sense on Vercel and app.py never calls it
there (see ON_VERCEL in app.py).
"""

import base64
import os
import threading
import time
from urllib.parse import urlparse

# playwright is imported lazily, inside autofill_application() — app.py imports
# this module unconditionally (including on Vercel, for detect_ats()), and
# Vercel's serverless deploy never installs playwright/a browser (this feature
# is local-only), so a top-level import here would crash the whole hosted app.

# session_id -> {"playwright", "browser", "page", "opened_at"}
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL = 45 * 60  # close an abandoned (never-submitted) browser after 45 min


def detect_ats(job_url: str) -> str:
    """Which auto-fillable ATS this job_url is hosted on ('lever', 'greenhouse',
    'ashby', 'workable'), or '' if it's not one of them.

    Deliberately excluded, and NOT a TODO — these go through a login-gated
    account action on the job board itself, the same reason LinkedIn Easy
    Apply is excluded, not a technical limitation:
      - LinkedIn (Easy Apply), Naukri (1-click apply), Indeed (Indeed Apply),
        Foundit (1-click apply) — all act through YOUR logged-in session on
        THAT platform.
      - SmartRecruiters — checked live: its "I'm interested" button redirects
        to a separate "oneclick-ui" flow (typically a LinkedIn/Google social-
        login quick-apply), the same account-gated pattern, not a plain form.
    Ashby IS a public form but renders a fully custom React layout per job
    with no stable selectors across postings, so detect_ats() recognizes it
    (for the UI badge) but autofill_application() below has no filler for it —
    the browser still opens on the real posting, nothing gets pre-filled."""
    host = urlparse(job_url or "").netloc.lower()
    if "lever.co" in host:
        return "lever"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "ashbyhq.com" in host:
        return "ashby"
    if "workable.com" in host:
        return "workable"
    return ""


def _split_name(full_name: str):
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _try_fill(page, selector, value, label, filled):
    if not value:
        return
    try:
        page.fill(selector, value, timeout=3000)
        filled.append(label)
    except Exception:
        pass


def _try_fill_any(page, selectors, value, label, filled):
    """Like _try_fill, but tries each selector in turn and stops at the first
    that exists — for a field whose id/name differs across postings but whose
    other attributes (aria-label, placeholder) stay stable."""
    if not value:
        return
    for sel in selectors:
        try:
            page.fill(sel, value, timeout=1500)
            filled.append(label)
            return
        except Exception:
            continue


def _try_upload(page, selectors, path, filled):
    if not path or not os.path.exists(path):
        return
    for sel in selectors:
        try:
            page.set_input_files(sel, path, timeout=5000)
            filled.append("resume")
            return
        except Exception:
            continue


# Custom per-job TEXT questions (not yes/no) that recur across many postings,
# matched by the question's visible label text. Deliberately text-only: a
# wrong text value is easy to spot and fix before submitting, so this is safe
# to guess at. Yes/No questions (relocate, work authorization) are NOT
# auto-answered anywhere in this file, even though `screening` carries those
# values too — a wrong radio-button guess looks identical to a correct one at
# a glance, and getting work authorization wrong is a worse outcome than the
# few seconds saved. Those stay for the human to click.
_TEXT_QUESTION_KEYWORDS = (
    (("current ctc", "current salary", "current compensation", "current annual"), "current_ctc"),
    (("expected ctc", "expected salary", "expected compensation", "expected annual"), "expected_ctc"),
    (("notice period",), "notice_period"),
    (("current location", "current city", "which city", "where are you based"), "location"),
    (("linkedin",), "linkedin"),
)


_LABEL_TEXT_JS = """(node) => {
  if (node.getAttribute('aria-label')) return node.getAttribute('aria-label');
  if (node.id) {
    const lab = document.querySelector('label[for="' + node.id + '"]');
    if (lab && lab.innerText && lab.innerText.trim()) return lab.innerText;
  }
  // The immediate wrapper is usually just the input itself (empty innerText) --
  // the actual question text is a sibling a level or two further up. Climb
  // until an ancestor's text is non-empty, capped so a huge match (e.g. the
  // whole form) can't silently answer the wrong question.
  let el = node.parentElement;
  for (let i = 0; i < 5 && el; i++) {
    const t = (el.innerText || '').trim();
    if (t) return t.length > 400 ? t.slice(0, 400) : t;
    el = el.parentElement;
  }
  return '';
}"""


def _label_text(el) -> str:
    """Best-effort visible question text for a field: its <label for=id>, or
    failing that the text of its nearest block-level ancestor."""
    try:
        return el.evaluate(_LABEL_TEXT_JS) or ""
    except Exception:
        return ""


def _answer_text_questions(page, screening):
    """Fill recurring custom TEXT questions (CTC/notice period/location/
    LinkedIn) by matching each blank text field's visible label against
    _TEXT_QUESTION_KEYWORDS. Skips fields that already have a value (so it
    never overwrites a standard field filled moments earlier) and never
    touches radios/checkboxes/selects."""
    filled = []
    if not screening:
        return filled
    for el in page.query_selector_all(
            "textarea, input[type='text'], input[type='url'], input[type='number']"):
        try:
            if (el.input_value() or "").strip():
                continue  # already has something in it — don't clobber it
            label = _label_text(el).lower()
        except Exception:
            continue
        if not label:
            continue
        for keywords, key in _TEXT_QUESTION_KEYWORDS:
            val = screening.get(key)
            if val and any(k in label for k in keywords):
                try:
                    el.fill(str(val), timeout=1500)
                    filled.append(f"'{key}' question")
                except Exception:
                    pass
                break
    return filled


def _fill_lever(page, full_name, email, phone, resume_path, cover_note, linkedin, github, screening):
    filled = []
    _try_fill(page, "input[name='name']", full_name, "name", filled)
    _try_fill(page, "input[name='email']", email, "email", filled)
    _try_fill(page, "input[name='phone']", phone, "phone", filled)
    _try_fill(page, "input[name=\"urls[LinkedIn]\"]", linkedin, "LinkedIn URL", filled)
    _try_fill(page, "input[name=\"urls[GitHub]\"]", github, "GitHub URL", filled)
    # Not every Lever board has a comments/cover-letter box — harmless no-op if absent.
    _try_fill(page, "textarea[name='comments']", cover_note, "cover note", filled)
    _try_upload(page, ["input[name='resume']"], resume_path, filled)
    filled += _answer_text_questions(page, screening)
    return filled


def _fill_greenhouse(page, full_name, email, phone, resume_path, cover_note, linkedin, github, screening):
    filled = []
    first, last = _split_name(full_name)
    _try_fill(page, "#first_name", first, "first name", filled)
    _try_fill(page, "#last_name", last, "last name", filled)
    _try_fill(page, "#email", email, "email", filled)
    _try_fill(page, "#phone", phone, "phone", filled)
    _try_upload(page, ["#resume", "input[name='job_application[resume]']"], resume_path, filled)
    # Greenhouse's older template has a dedicated #cover_letter_text box; its
    # newer job-boards.greenhouse.io template instead has a generic textarea
    # labelled "Additional Information" (id varies per posting -- confirmed
    # live against a real Anthropic posting) or sometimes "Cover Letter".
    _try_fill_any(page, ["#cover_letter_text",
                         "textarea[aria-label='Additional Information']",
                         "textarea[aria-label='Cover Letter']"],
                  cover_note, "cover note", filled)
    filled += _answer_text_questions(page, screening)
    return filled


def _fill_ashby(page, full_name, email, phone, resume_path, cover_note, linkedin, github, screening):
    # Ashby renders a fully custom React form per job — no selector is stable
    # across postings, so there's nothing generic worth auto-filling here. The
    # browser still opens on the real posting, saving the click-through.
    return []


def _fill_workable(page, full_name, email, phone, resume_path, cover_note, linkedin, github, screening):
    # Workable's fields are hidden behind a cookie banner + an "Apply" button
    # that has to be clicked first to reveal the form (confirmed live against
    # a real posting) — button wording varies a bit per company, so try a few.
    for txt in ("Accept all", "Accept cookies", "I accept", "Allow all"):
        try:
            page.get_by_role("button", name=txt, exact=False).first.click(timeout=1500)
            break
        except Exception:
            continue
    for txt in ("Apply for this job", "Apply now", "Apply"):
        try:
            page.get_by_role("button", name=txt, exact=False).first.click(timeout=3000)
            page.wait_for_timeout(1000)
            break
        except Exception:
            continue

    filled = []
    first, last = _split_name(full_name)
    _try_fill(page, "input[name='firstname']", first, "first name", filled)
    _try_fill(page, "input[name='lastname']", last, "last name", filled)
    _try_fill(page, "input[name='email']", email, "email", filled)
    _try_fill(page, "input[name='phone']", phone, "phone", filled)
    _try_fill(page, "textarea[name='cover_letter']", cover_note, "cover note", filled)
    _try_upload(page, ["input[data-ui='resume']", "input[type='file']"], resume_path, filled)
    filled += _answer_text_questions(page, screening)
    return filled


_FILLERS = {"lever": _fill_lever, "greenhouse": _fill_greenhouse, "ashby": _fill_ashby,
            "workable": _fill_workable}


def _cleanup_stale():
    now = time.time()
    with _SESSIONS_LOCK:
        stale = [sid for sid, s in _SESSIONS.items() if now - s["opened_at"] > _SESSION_TTL]
    for sid in stale:
        close_session(sid)


def close_session(session_id: str):
    """Close a still-open auto-fill browser (e.g. the user is done / gave up)."""
    with _SESSIONS_LOCK:
        s = _SESSIONS.pop(session_id, None)
    if not s:
        return
    try:
        s["browser"].close()
    except Exception:
        pass
    try:
        s["playwright"].stop()
    except Exception:
        pass


def autofill_application(job_url, ats, full_name="", email="", phone="",
                          resume_path=None, cover_note="", linkedin="", github="",
                          screening=None, headless=False):
    """Open a browser window, navigate to the job's real application page, and
    fill in whatever standard fields that ATS exposes, plus any recurring
    custom TEXT question (current/expected CTC, notice period, location,
    LinkedIn) matched from `screening` -- see _answer_text_questions. Never
    answers a Yes/No question and never touches Submit — returns with the
    browser left open (headless=False in production) for the user to finish
    and submit themselves."""
    if ats not in _FILLERS:
        return {"ok": False, "message": f"Auto-fill isn't supported for '{ats or 'this site'}'."}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "message":
                "Playwright isn't installed. Run: pip install playwright  &&  "
                "playwright install chromium"}

    _cleanup_stale()
    session_id = base64.urlsafe_b64encode(os.urandom(9)).decode()
    p = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        filled = _FILLERS[ats](page, full_name, email, phone, resume_path,
                                cover_note, linkedin, github, screening or {})
        screenshot_b64 = base64.b64encode(page.screenshot(full_page=True)).decode()

        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = {"playwright": p, "browser": browser, "page": page,
                                      "opened_at": time.time()}
        browser.on("disconnected", lambda *_: _SESSIONS.pop(session_id, None))

        return {
            "ok": True, "session_id": session_id, "filled_fields": filled,
            "screenshot_b64": screenshot_b64,
            "message": ("Opened in a browser window on this computer. Review it, "
                        "answer anything custom, solve any CAPTCHA, and click the "
                        "real Submit button yourself when ready."),
        }
    except Exception as e:
        if p:
            try:
                p.stop()
            except Exception:
                pass
        return {"ok": False, "message": f"Could not open/fill the application: {e}"}
