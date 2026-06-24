# Job Finder & Resume Tailor

A single-user web app (and optional daily cron):
1. **Find jobs** across many boards — **generic**: ranked to whatever you give it
   (an uploaded resume / target role / JD / skills), never to any baked-in data.
2. **Create a resume** two ways: **(A)** generate your saved resume
   ([`resume_profile.py`](resume_profile.py)) in your own one-page format,
   tailored to a pasted JD, or **(B)** upload any resume and tailor it while
   keeping its exact format. Output is PDF and/or Word.

Your saved profile is used **only** in *Create a resume → A* — the *Find jobs*
section never uses it. The optional daily cron writes fresh listings to a plain
**JSON feed file** (`data/jobs.json`) that the hosted app reads — **no Google
Sheet, no service account, no credentials.**

- **Sources:** [`python-jobspy`](https://github.com/Bunsly/JobSpy) (LinkedIn,
  Indeed, Google, Glassdoor, ZipRecruiter, Naukri, Bayt) **+ Remotive & RemoteOK**
  free APIs — no API key. Optional web-search sources (company career pages,
  recent LinkedIn *hiring posts*) activate when `TAVILY_API_KEY` is set.
- **Schedule (optional):** GitHub Actions cron (free) → commits `data/jobs.json`.

---

## One-time setup

There is **no external service to configure** — the feed is just a file in the
repo. Two steps:

### 1. Run locally (test it first)
```bash
pip install -r requirements.txt
python fetch_jobs.py
```
This scrapes the boards and writes/updates **`data/jobs.json`** (newest first,
deduped by URL, capped at the 1000 most recent). Open the file to confirm it has
rows.

### 2. Run daily on GitHub Actions (free)
1. Push this folder to a GitHub repo.
2. Go to the **Actions** tab → enable workflows → run **Daily Job Fetch** once
   manually to seed `data/jobs.json`.
3. From then on it runs **every day at 09:00 IST** (`30 3 * * *` UTC), scrapes,
   and **commits the refreshed `data/jobs.json` back to the repo** by itself.
   You don't run it again by hand — manual runs are only for an extra mid-day
   refresh.

> The workflow commits the feed using the built-in `GITHUB_TOKEN`
> (`permissions: contents: write` in the workflow) — no secrets needed.

---

## Customizing what the cron fetches

> **Important:** the daily cron uses the **fixed search config** below — it does
> **not** use your uploaded resume/profile. (Resume-based personalized matching
> runs only in *local live* mode in the dashboard.) Edit these to change what the
> feed contains.

All knobs are at the top of [`fetch_jobs.py`](fetch_jobs.py):

| Setting | What it does |
|---|---|
| `SEARCH_TERMS` | The roles to search for (default: backend / software engineer / software developer) |
| `LOCATION` / `COUNTRY_INDEED` | Where to search (default: India) |
| `SITES` | Which boards to hit (`linkedin`, `indeed`, `google`, `glassdoor`, `zip_recruiter`, `naukri`, `bayt`) |
| `HOURS_OLD` | Only jobs posted within N hours (default 48) |
| `RESULTS_WANTED` | Results per term per site |
| `MAX_STORED` | How many of the most recent jobs the feed keeps |

To change the schedule, edit the `cron:` line in `.github/workflows/daily-jobs.yml`.

---

## Web dashboard (jobs + resume in your browser)

[`app.py`](app.py) is **one FastAPI app** that runs in two modes:

| Mode | When | Jobs come from | Live "Fetch" button |
|---|---|---|---|
| **Local** (`JOBS_SOURCE=live`, default) | `python app.py` on your machine | live scrape (python-jobspy) | ✅ yes |
| **Hosted** (`JOBS_SOURCE=feed`) | deployed to Vercel | the committed `data/jobs.json` feed | ❌ (reads the feed) |

> **Why two modes?** Job boards block Vercel's datacenter IPs and serverless
> functions time out on a 60-90s scrape — so scraping runs locally (or via the
> GitHub Actions cron that writes the feed). The hosted page reads that data.
> (`JOBS_SOURCE=sheet` is still accepted as an alias for `feed` for older deploys.)

### Run the dashboard locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:8000
```

The page has **two independent sections**:

**① Find jobs.** Everything is optional:
- Upload your **resume** — the app infers which roles to search and ranks jobs to it.
- Type a **position/role** (e.g. `Backend Developer, DevOps`) to search exactly that.
- Add a **JD** and/or **skills** to sharpen the ranking.
- Give nothing and a broad default search runs.

Click **Fetch jobs**. It pulls from **LinkedIn, Indeed, Google, Glassdoor,
ZipRecruiter, Naukri, Bayt** (via jobspy) **plus Remotive and RemoteOK**, scores
each job 0–100, and shows the **top N ranked** in one combined list (match chips
+ direct apply links).

**How jobs are ranked** (all soft signals — nothing except hard skill/experience
gates is filtered out):
- **Skill / experience / title match** to your inputs is the base score, and a
  strong match to your **target role** gets an extra boost (your search
  preference ranks first).
- **Pay above your current salary** (`CURRENT_LPA`, default `6.3`) floats jobs up
  and shows a green **"↑ LPA"** badge. Jobs that don't list pay are **never
  hidden** (most boards don't publish salary).
- **Freshness** — the most recently posted jobs sort to the top.

Tick **Remote only** to keep just remote jobs. **Search company career pages
directly** (on by default) adds Greenhouse/Lever/Ashby ATS boards, Hacker News
"Who's Hiring", and We Work Remotely. On any job row, **Tailor to this ↓** copies
that job's description into section ②.

**② Create a tailored resume** — see the next section.

Controls: posting age (24h–7d), how many top jobs to show, and the Remote-only
toggle. Results are cached to `data/jobs_latest.json`, so **Reload cached** is
instant.

### ② Create a resume — two ways

**A · From your saved resume (your format).** Your resume content lives in
[`resume_profile.py`](resume_profile.py) and renders in your own **one-page**
layout (PDF + Word). Paste a job description and the matching skills are
reordered to the front of their category and **bolded**, and the summary leads
with your top matching stack. Click **Generate resume**.

**B · Tailor a resume you upload (keeps your exact format).** Upload any resume
and work a job's requirements into it without restyling:

1. Upload your resume. **`.docx` is edited in place**, so every font, margin and
   color you chose is preserved. A **`.pdf`** can't be edited in place without
   wrecking its layout, so its text is extracted and rebuilt into a clean
   document (you're told when this happens).
2. Optionally paste a **job description** and/or a comma-separated list of
   **skills to emphasize**.
3. Pick **PDF / Word / both** and click **Create resume**.

You get **two versions** of every tailored resume:
- **A — Standard:** bolds the skills your resume *already has* that the job wants,
  plus any skills you typed. Honest — safe to send anywhere.
- **B — ATS-optimized:** version A **plus** the JD's remaining important keywords
  appended for maximum ATS keyword coverage / a higher ATS score. ⚠️ This can
  list skills your resume didn't originally have — **verify they're truthful
  before sending.**

PDF output is produced from the tailored Word file via **Microsoft Word**
(`docx2pdf`) so the PDF matches the Word styling exactly. If Word isn't installed
the Word file is still produced and the PDF falls back to a basic text render.

### Deploy the dashboard to Vercel

The hosted page shows the jobs from `data/jobs.json` (kept fresh by the daily
GitHub Actions cron) and still builds tailored resumes on demand.

1. Install the CLI and log in: `npm i -g vercel && vercel login`
2. From this folder: `vercel` (accept defaults). [`vercel.json`](vercel.json)
   routes everything to [`api/index.py`](api/index.py), which loads `app` in
   **feed mode**. [`api/requirements.txt`](api/requirements.txt) keeps the
   function small (no jobspy/pandas/gspread).
3. In the Vercel project → **Settings → Environment Variables**, add:
   - `JOBS_SOURCE` = `feed`
   - *(optional)* `TAVILY_API_KEY` = your Tavily key — enables the web-search
     career-page sources and **recent LinkedIn hiring posts**.
   - *(optional)* `CURRENT_LPA` = your current pay in LPA (default `6.3`) — jobs
     paying above this rank higher.
4. **Connect the project to your GitHub repo** (Vercel → Project → Git) so each
   cron commit of `data/jobs.json` **auto-redeploys** the site with fresh jobs.
5. `vercel --prod` to publish. Open the URL → **Load latest jobs**.

> The deployed page has **no live scrape button** by design — it reads the feed.
> Keep the daily GitHub Actions cron running (or run `python fetch_jobs.py`
> locally and commit) to keep the feed current.

## Notes
- LinkedIn is the most rate-limited board; if it returns few/zero results in CI,
  Indeed + Google usually carry the run.
- The feed is **newest-first, deduped by `job_url`, and capped** at `MAX_STORED`,
  so the same job is never stored twice and the committed file can't grow forever.
- **LinkedIn *posts*** can't be scraped directly (login + ToS); the "recent
  hiring posts" source uses public web search (Tavily) instead, so its coverage
  is partial — only what's publicly indexed.
