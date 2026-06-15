# Job Finder & Resume Tailor

A single-user web app (and optional daily cron):
1. **Find jobs** across many boards — **generic**: ranked to whatever you give it
   (an uploaded resume / target role / JD / skills), never to any baked-in data.
2. **Create a resume** two ways: **(A)** generate your saved resume
   ([`resume_profile.py`](resume_profile.py)) in your own one-page format,
   tailored to a pasted JD, or **(B)** upload any resume and tailor it while
   keeping its exact format. Output is PDF and/or Word.

Your saved profile is used **only** in *Create a resume → A* — the *Find jobs*
section never uses it. The optional daily cron can also append fresh listings to
a Google Sheet.

- **Sources:** [`python-jobspy`](https://github.com/Bunsly/JobSpy) (LinkedIn,
  Indeed, Google, Glassdoor, ZipRecruiter, Naukri, Bayt) **+ Remotive & RemoteOK**
  free APIs — no API key.
- **Schedule (optional):** GitHub Actions cron (free) → Google Sheets.

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

The page has **two independent sections**:

**① Find jobs.** Everything is optional:
- Upload your **resume** — the app infers which roles to search and ranks jobs to it.
- Type a **position/role** (e.g. `Backend Developer, DevOps`) to search exactly that.
- Add a **JD** and/or **skills** to sharpen the ranking.
- Give nothing and a broad default search runs.

Click **Fetch jobs**. It pulls from **LinkedIn, Indeed, Google, Glassdoor,
ZipRecruiter, Naukri, Bayt** (via jobspy) **plus Remotive and RemoteOK** (free
remote-job APIs — startups & MNCs), scores each job 0–100, and shows the
**top N ranked** in one combined list (match chips + direct apply links). A
**Size** column shows company headcount when the board reports it; established
companies (≥150 employees, when known) get a small ranking boost.
   > LinkedIn / Indeed / Google / Remotive / RemoteOK are the workhorses.
   > ZipRecruiter is US/Canada-only and Naukri/Bayt/Glassdoor often block
   > datacenter or repeated requests, so they may return little from a home IP;
   > a board that blocks us or returns nothing never aborts the run.
   > **Note:** a hard "150+ employees only" filter isn't possible — job boards
   > almost never publish headcount — so company size is a soft ranking signal,
   > not a filter.

Tick **Remote only** to keep just remote jobs. On any job row, **Tailor to this ↓**
copies that job's description into section ② so you can tailor your resume to it.

**② Create a tailored resume** — see the next section.

Controls: posting age (24h–7d), how many top jobs to show, and the Remote-only
toggle. Results are cached to `data/jobs_latest.json`, so **Reload cached** is
instant.

### ② Create a resume — two ways

**A · From your saved resume (your format).** Your resume content lives in
[`resume_profile.py`](resume_profile.py) and renders in your own **one-page**
layout (PDF + Word). Paste a job description and the matching skills are
reordered to the front of their category and **bolded**, and the summary leads
with your top matching stack — everything else stays intact. Click **Generate
resume**. (Edit your details once in `resume_profile.py`; both formats stay in
sync. This is the only place your saved data is used — *Find jobs* never is.)

**B · Tailor a resume you upload (keeps your exact format).** Upload any resume
and work a job's requirements into it without restyling:

1. Upload your resume. **`.docx` is edited in place**, so every font, margin and
   color you chose is preserved. A **`.pdf`** can't be edited in place without
   wrecking its layout, so its text is extracted and rebuilt into a clean
   document (you're told when this happens).
2. Optionally paste a **job description** and/or a comma-separated list of
   **skills to emphasize** — both are optional.
3. Pick **PDF / Word / both** and click **Create resume**.

What it does to the document — and nothing more:
- **Bolds** the skills your resume *already has* that the job is asking for.
- Inserts one **"Key Skills for this Role"** line near the top (the matching
  skills you have, plus any you typed in the skills box).
- Shows you, but **never silently adds**, the skills the JD wants that your
  resume is missing — so you decide whether to add them.

PDF output is produced from the tailored Word file via **Microsoft Word**
(`docx2pdf`) so the PDF matches the Word styling exactly. If Word isn't installed
the Word file is still produced and the PDF falls back to a basic text render.

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
