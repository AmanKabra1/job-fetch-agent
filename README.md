# Daily Job Fetch Agent

Scrapes **backend developer / software engineer / software developer** roles from
LinkedIn, Indeed, and Google Jobs every day and appends new listings (with a
direct apply link) to a Google Sheet you can open on your phone.

- **Source:** [`python-jobspy`](https://github.com/Bunsly/JobSpy) — no API key
- **Schedule:** GitHub Actions cron (free)
- **Output:** Google Sheets (deduped, append-only)

---

## One-time setup

### 1. Create the Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com) and create a sheet named exactly **`Job Listings`**.
   (Change `SHEET_NAME` in `fetch_jobs.py` if you want a different name.)

### 2. Create a Google service account (free)
1. Open the [Google Cloud Console](https://console.cloud.google.com/) → create/select a project.
2. Enable two APIs: **Google Sheets API** and **Google Drive API**
   (APIs & Services → Library → search → Enable).
3. APIs & Services → **Credentials** → *Create Credentials* → **Service account**. Name it anything, click Done.
4. Click the new service account → **Keys** → *Add Key* → *Create new key* → **JSON**. A `.json` file downloads.
5. Open that JSON file, copy the `"client_email"` value (looks like `something@project.iam.gserviceaccount.com`).
6. Back in your **Job Listings** sheet → **Share** → paste that email → give it **Editor** access.

### 3a. Run locally (test it first)
1. Rename the downloaded JSON to `service_account.json` and put it in this folder.
   > It's already in `.gitignore` — never commit it.
2. Install deps and run:
   ```bash
   pip install -r requirements.txt
   python fetch_jobs.py
   ```
3. Check your sheet — it should now have rows.

### 3b. Run daily on GitHub Actions (free)
1. Push this folder to a GitHub repo.
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `GOOGLE_CREDENTIALS`
   - Value: paste the **entire contents** of `service_account.json`
3. Go to the **Actions** tab → enable workflows → run **Daily Job Fetch** manually once to confirm.
4. From then on it runs every day at **09:00 IST** (`30 3 * * *` UTC in the workflow file).

---

## Customizing

All knobs are at the top of [`fetch_jobs.py`](fetch_jobs.py):

| Setting | What it does |
|---|---|
| `SEARCH_TERMS` | The roles to search for |
| `LOCATION` / `COUNTRY_INDEED` | Where to search |
| `SITES` | Which boards to hit (`linkedin`, `indeed`, `google`, `glassdoor`, `zip_recruiter`) |
| `HOURS_OLD` | Only jobs posted within N hours |
| `RESULTS_WANTED` | Results per term per site |

To change the schedule, edit the `cron:` line in `.github/workflows/daily-jobs.yml`.

---

## Tailored resume builder

When you find a job worth applying to, generate a resume **in your own format**
with the matching skills pushed to the front and bolded, exported as **PDF and/or
Word**. Output lands in [`resume/`](resume/).

```bash
pip install -r requirements.txt   # adds reportlab + python-docx

# Auto-tailor from a job description (recommended):
python resume_builder.py new --title "Backend Developer" --company "Acme" --jd jd.txt

# Or paste the JD inline:
python resume_builder.py new --title "Node.js Developer" --company "Acme" \
    --jd-text "We need a Node.js / NestJS engineer with MySQL and AWS ..."

# No JD -> plain base resume:
python resume_builder.py new --title "Software Engineer" --company "Acme"
```

What tailoring does: it scans the JD, and for every skill of yours it finds
(see `SKILL_KEYWORDS` in [`resume_profile.py`](resume_profile.py)) it reorders
that skill to the front of its category, **bolds it**, and rewrites the summary
line to lead with your top matching stack. Everything else (experience,
projects, education) stays intact so the resume always reads naturally.

| Command | What it does |
|---|---|
| `new --title T --company C [--jd FILE \| --jd-text "..."] [--format pdf\|docx\|both]` | Build a resume (default: both formats) |
| `list` | Show every resume you've generated |
| `delete "<base-name>"` | Delete one resume (both formats) |
| `delete --all` | Delete every generated resume |

- **Edit your details once** in [`resume_profile.py`](resume_profile.py) — PDF and
  Word stay in sync.
- Files are named `Aman-Kabra_<Company>_<Title>_<date>.{pdf,docx}`, so the
  `delete` base name is everything before the extension.
- PDF is built with `reportlab`, Word with `python-docx` — **no Microsoft Word
  required**.

---

## Web dashboard (jobs + resume in your browser)

[`app.py`](app.py) is **one FastAPI app** that runs in two modes:

| Mode | When | Jobs come from | Live "Fetch" button |
|---|---|---|---|
| **Local** (`JOBS_SOURCE=live`, default) | `python app.py` on your machine | live scrape (python-jobspy) | ✅ yes |
| **Vercel** (`JOBS_SOURCE=sheet`) | deployed to Vercel | your Google Sheet | ❌ (reads Sheet) |

> **Why two modes?** Job boards block Vercel's datacenter IPs and serverless
> functions time out on a 60-90s scrape — so scraping must run locally (or via
> the GitHub Actions cron that fills the Sheet). The hosted page reads that data.

### Run the dashboard locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:8000
```

Then:
1. Click **"Fetch today's jobs"** — it scrapes LinkedIn/Indeed/Google across your
   7 resume-matched search terms, scores each job 0-100 against your skills, and
   shows the **top 50 ranked** (with match chips + direct apply links).
2. On any row, pick **PDF / Word / both** and click **Generate** — a resume
   tailored to *that* job's description is built and downloaded. It also appears
   in the **Generated resumes** panel with Download / Delete.

Controls: posting age (24h–7d) and how many top jobs to show. Results are cached
to `data/jobs_latest.json`, so **Reload cached** is instant.

> First scrape can take ~1 minute (LinkedIn descriptions are fetched so the
> resume tailoring has text to match). If a board returns little, Indeed +
> Google usually carry the run.

### Deploy the dashboard to Vercel

The hosted page shows the jobs from your Google Sheet (kept fresh by the daily
GitHub Actions cron) and still builds tailored resumes on demand.

1. Install the CLI and log in: `npm i -g vercel && vercel login`
2. From this folder: `vercel` (accept defaults). [`vercel.json`](vercel.json)
   routes everything to [`api/index.py`](api/index.py), which loads `app` in
   **sheet mode**. [`api/requirements.txt`](api/requirements.txt) keeps the
   function small (no jobspy/pandas).
3. In the Vercel project → **Settings → Environment Variables**, add:
   - `GOOGLE_CREDENTIALS` = the full contents of `service_account.json`
   - (optional) `SHEET_NAME` / `WORKSHEET_NAME` if you renamed them
4. `vercel --prod` to publish. Open the URL → **Load jobs from Sheet**.

> The deployed page has **no live scrape button** by design — it reads the Sheet.
> Keep running the daily GitHub Actions cron (or `python fetch_jobs.py` locally)
> to keep the Sheet current.

## Notes
- LinkedIn is the most rate-limited board; if it returns few/zero results in CI,
  Indeed + Google usually carry the run.
- The sheet is **append-only and deduped by `job_url`**, so the same job is never added twice.
