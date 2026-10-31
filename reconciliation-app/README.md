# Smart Bank Reconciliation

url "https://github.com/Dawit360/reconciliation-app"

Automates the manual audit of company transactions against bank statements.
It cleans messy CSV exports, matches ledger entries to bank lines with a confidence score,
and leaves a human to review only the doubtful items.

| Component | File | Use it for |
|---|---|---|
| Interactive dashboard | `reconciliation.html` | Upload CSVs, tune thresholds, approve or reject suggestions, export results |
| Python / Colab engine | `reconcile_colab.py` | Batch runs, testing, scripting, integration into pipelines |
| Dependencies | `requirements.txt` | Python packages (dashboard needs none) |

---

## Table of contents
1. [How it works](#how-it-works)
2. [Quick start](#quick-start)
3. [Input data and cleaning](#input-data-and-cleaning)
4. [Matching algorithm](#matching-algorithm)
5. [Dashboard guide](#dashboard-guide)
6. [Python / Colab guide](#python--colab-guide)
7. [Configuration reference](#configuration-reference)
8. [Output format](#output-format)
9. [Testing](#testing)
10. [Limitations](#limitations)
11. [Roadmap](#roadmap)
12. [Troubleshooting](#troubleshooting)

---

## How it works

```
 Ledger CSV ─┐                                  ┌─ Matched    (auto-accepted)
             ├─► Clean & ─► Candidate ─► Score ─┼─ Review     (human approves/rejects)
 Bank CSV ───┘   normalise   pairs       & rank └─ Unmatched  (no counterpart found)
```

1. **Clean and normalise** both files (delimiters, headers, dates, amounts, text).
2. **Generate candidates**: a ledger entry and bank line are compared only if the amounts are within tolerance and the dates are within the date window.
3. **Score** each candidate from 0 to 1 using amount, date and description similarity.
4. **Assign** pairs one-to-one, best score first.
5. **Classify** each pair by threshold: Matched, Review or Unmatched.
6. A human works only through the Review and Unmatched lists, then exports the result.

---

## Quick start

### Option A: Dashboard (no install)
1. Open `reconciliation.html` in any modern browser (double-click it).
2. It loads with sample data. Click **Ledger CSV** and **Bank CSV** to load your own.
3. Adjust the sliders, review the yellow items, then **Export CSV**.

All processing happens in your browser. Nothing is uploaded to any server.

### Option B: Google Colab
1. Open <https://colab.research.google.com> and create a new notebook.
2. Paste the contents of `reconcile_colab.py` into a cell and run it. It runs on built-in sample data.
3. To use your own files, replace the last lines with:
   ```python
   ledger = load('ledger.csv')
   bank   = load('bank.csv', flip=False)   # flip=True if the bank shows debits as positive
   res = reconcile(ledger, bank)
   display(res.sort_values('status'))
   res.to_csv('reconciliation_result.csv', index=False)
   ```
4. `load()` opens an upload dialog. Pick the file with the matching name.

### Option C: Local Python
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
`load()` uses the Colab upload dialog. Outside Colab, read your files with `pd.read_csv(..., sep=None, engine="python", encoding="utf-8-sig")` and pass them to `clean_df()`.

---

## Input data and cleaning

Each file needs a **date**, a **description** and an **amount** (or separate debit and credit columns). Exact column names and formats do not matter.

| Aspect | What is handled |
|---|---|
| Delimiter | Comma, semicolon, tab, pipe (auto-detected); quoted fields; UTF-8 BOM |
| Headers | Fuzzy names: *date, posting date, value date*; *description, narration, details, memo, particulars, payee, reference*; *amount*; *debit, withdrawal, paid out*; *credit, deposit, paid in*. With no header row: date, description, amount in that order |
| Dates | `2026-10-05`, `05/10/2026`, `10/05/2026`, `05-Oct-2026`, `Oct 5, 2026`, Excel serial numbers (dashboard only). DD/MM vs MM/DD is decided by scanning the whole column for values above 12 |
| Amounts | Currency symbols, `1,234.50`, `1.234,50`, `(200.00)` as negative, trailing minus, `CR`/`DR` markers, separate debit/credit columns |
| Descriptions | Whitespace collapsed; for matching, punctuation and filler words (`TRF, POS, REF, PAYMENT, CARD, ACH, EFT, ATM, ...`) are ignored and letters/digits are split (`REF1000` becomes `1000`) |
| Bad rows | Skipped when the date or amount cannot be parsed, and counted in the cleaning report |
| Duplicates | Reported as "possible duplicates" but **kept**, since repeated identical payments can be legitimate |
| Sign convention | Ledger and bank should both use negative for money out. Use **Flip bank signs** (`flip=True`) if they differ |

**Ambiguity warning:** if every date in a file has both parts 12 or below (for example `03/04/2026`), DD/MM is assumed. Check the cleaning report line "dates read as ...".

---

## Matching algorithm

**Candidates (indexed, fast).** Bank lines are sorted by amount and found by binary search, so only lines within the amount tolerance are examined, then filtered by the date window. Tolerance is the larger of the absolute tolerance and a percentage of the amount (default 5%). An amount that is not exact must also share description words or a reference number, otherwise it is ignored.

**Score** for each candidate:

```
score = 0.35 * text_similarity          (word overlap, order-independent)
      + 0.25 * date_closeness           (1 - days_apart / (window + 1))
      + 0.20 * amount                   (1 if exact, 0.5 if within tolerance)
      + 0.20 * reference_match          (shared number of 3+ digits, e.g. INV-1000 and REF1000)
```

**Uniqueness bonus (up to +0.25).** If a pair clearly beats every other candidate for either side, confidence rises. The bonus is halved for round amounts (multiples of 10), which collide often. A pair whose amount is not exact can never be auto-accepted (it is capped just below the auto threshold).

**Assignment.** Pairs are sorted by confidence and used one-to-one, best first. Pairs below `review x 0.6` are dropped.

**Split payments.** Remaining bank lines are checked against combinations of 2 to 4 unmatched ledger entries (same direction, nearby dates, shared words or references) whose amounts add up to the bank amount. These are always sent to Review.

| Status | Rule (defaults) |
|---|---|
| Matched | confidence >= 0.70 |
| Review | 0.50 <= confidence < 0.70, or any split payment |
| Unmatched | below the review threshold, or no candidate |

Text similarity is the same in the dashboard and the Python engine, so results should now agree. `reconcile_basic()` keeps the original simple engine for benchmarking.

---

## Dashboard guide

**Summary cards**: auto-matched count, needs-review count, unmatched count, match rate (matched divided by ledger rows), and estimated audit time saved.
*Time saved is an estimate, not a measurement:* it assumes about 2 minutes of manual work per matched item and 0.5 minutes per review item (`(matched x 2 + review x 0.5) / 60` hours). Edit this in `draw()` in the HTML if your numbers differ.

**Controls**
| Control | Effect | Default |
|---|---|---|
| Auto-match above | Score needed to auto-accept | 70% |
| Review above | Score needed to enter the review queue | 50% |
| Date window | Allowed days between ledger and bank date | 4 |
| Amount tolerance | Allowed amount difference | 0.00 |

**Workflow**: load files, check the cleaning report, tune sliders, filter by tab (All, Matched, Review, Unmatched), approve or reject suggestions (or **Approve all review**), then **Export CSV**.

**Notes**: approvals live in the page and are lost on refresh. Export before closing. Changing a slider keeps your approvals for pairs that still exist.

---

## Python / Colab guide

Key functions in `reconcile_colab.py`:

| Function | Purpose |
|---|---|
| `clean_df(df, flip=False)` | Normalise a DataFrame to columns `date`, `description`, `amount`; prints a cleaning summary |
| `load(name, flip=False)` | Colab upload dialog, then clean |
| `norm(text)` | Normalise a description for matching |
| `to_num(value)` | Parse a messy amount string |
| `sim(a, b)` | Description similarity (0 to 1) |
| `reconcile(L, B, auto=0.7, review=0.5, window=4, tol=0.0, tol_pct=0.05, split=True)` | Run the matching; returns a DataFrame |

Example with custom settings:
```python
res = reconcile(ledger, bank, auto=0.85, review=0.55, window=5, tol=0.50)
res.status.value_counts()
```

---

## Configuration reference

| Setting | Dashboard | Python | Default |
|---|---|---|---|
| Auto-match threshold | slider | `auto` | 0.70 |
| Review threshold | slider | `review` | 0.50 |
| Date window (days) | slider | `window` | 4 |
| Amount tolerance | slider | `tol` | 0.00 |
| Flip bank signs | checkbox | `flip` | off |
| Score weights (0.45 / 0.30 / 0.25) | edit in `run()` | edit in `reconcile()` | fixed |

---

## Output format

Exported CSV (`reconciliation.csv` from the dashboard, `reconciliation_result.csv` from Python):

| Column | Meaning |
|---|---|
| `ledger` | Ledger description (and amount in the dashboard export); empty for bank-only items |
| `bank` | Bank description (and amount in the dashboard export); empty for ledger-only items |
| `amount` | Amount (Python export only) |
| `score` | Confidence in percent (dashboard) or 0 to 1 (Python) |
| `status` | Matched, Review, or Unmatched |

---

## Testing

1. **Smoke test**: run with the built-in sample data. Expect most items Matched, a few in Review (shifted dates or changed descriptions, plus a deliberate 37.50 amount difference in the Python sample), and a few Unmatched (missing bank lines, bank fee, interest credit).
2. **Cleaning test**: save a copy of a statement with a semicolon delimiter, `DD-Mon-YYYY` dates and `1.234,50` amounts. The cleaning report should show the right delimiter and date order, and the same match results as the clean version.
3. **Sign test**: negate all bank amounts. The dashboard should warn that signs look opposite. Tick **Flip bank signs** and results should return to normal.
4. **Threshold test**: raise *Auto-match above* to 100% and confirm that nearly everything moves to Review.
5. **Real-data pilot**: reconcile one past, already-audited month and compare against the human result before relying on it.

No automated test suite is included yet.

---

## Limitations

- **Split matching is limited.** One bank payment covering 2 to 4 ledger entries is found (always sent to Review). The reverse (several bank lines for one invoice) and larger groups are not.
- **Single currency.** No conversion or multi-currency handling.
- **No persistence.** Approvals are not saved between sessions; there is no database or user login.
- **No audit trail** of who approved what and when.
- **Greedy assignment.** Best-first matching is fast and usually good, but not globally optimal in rare conflicts.
- **Text similarity is lexical.** Different wording for the same payee (for example a nickname versus a legal name) may score low.
- **Ambiguous dates** (both parts 12 or below) default to DD/MM.
- **Scale.** Candidate generation compares every ledger/bank pair, so very large files (tens of thousands of rows) will be slow in the browser; use the Python version and consider blocking by date.
- Scores from the dashboard and Python versions can differ slightly (different similarity measures).
- This tool supports an audit. It does not replace professional judgement or your organisation's controls.

---

## Roadmap

- Split and many-to-one matching (one payment to many invoices)
- Audit log with reviewer name and timestamp
- Learning from approvals and rejections to tune weights
- Supplier alias dictionary and rules (for example "always match bank fees to account X")
- Multi-currency support
- Persistent storage and multi-user review
- Downloadable cleaned CSVs
- Automated test suite

---

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| Everything is Unmatched | Signs differ: tick **Flip bank signs**. Or widen the date window or amount tolerance |
| Many rows "skipped" in the report | Date or amount columns were misdetected. Rename headers to `date`, `description`, `amount` |
| Wrong day and month | Ambiguous dates. Check "dates read as" in the report and re-export dates as `YYYY-MM-DD` |
| `ValueError: format='mixed'` in Python | pandas older than 2.0. Run `pip install -U pandas` |
| `ModuleNotFoundError: google.colab` | Running outside Colab. Read the CSV yourself and call `clean_df()` |
| `KeyError: 'date'` | No column name resembled "date". Rename the header |
| Too many false Review items | Raise the review threshold or narrow the date window |
| Approvals disappeared | Page was refreshed. Export before closing |

---

## Data privacy

The dashboard runs entirely in your browser and sends no data anywhere. In Colab, uploaded files live in the temporary Colab session. Do not share notebooks that contain real financial data.

---

# Install as an app (Windows, Android, iOS)

One codebase in `app/` runs everywhere. Pick the route that fits your users.

| Platform | Easiest route | Store/installer route |
|---|---|---|
| **Any device** | Host `app/` on HTTPS, open the link, install it (PWA) | n/a |
| **Windows** | Install from Edge/Chrome (PWA), or run the `.exe` built by GitHub Actions | Electron installer (`npm run dist:win`) |
| **Android** | Open the hosted link in Chrome, **Install app** | Capacitor APK/AAB (GitHub Actions or Android Studio) |
| **iOS / iPad** | Open the hosted link in Safari, **Share, Add to Home Screen** | Capacitor + Xcode (needs a Mac and Apple Developer account) |

## 1. Web app (PWA), the fastest way for end users
1. Put the contents of `app/` on any HTTPS host: GitHub Pages, Netlify, Cloudflare Pages or your company server.
2. Users open the link, then:
   - **Windows / Chrome / Edge:** click the install icon in the address bar.
   - **Android / Chrome:** menu, **Install app**.
   - **iPhone / iPad / Safari:** Share, **Add to Home Screen**.
3. It then opens full-screen like a normal app and works offline after the first visit. Data never leaves the device.

Test locally first: `npm install` then `npm run serve`, open <http://localhost:8080>.

## 2. Windows installer (.exe)
**Without a developer machine:** push this project to GitHub, open **Actions, Build apps, Run workflow**, then download `windows-installer`.
**On your PC** (needs Node.js 20+):
```bash
npm install
npm start          # run as a desktop app
npm run dist:win   # builds dist/*.exe installer
```
The installer is unsigned, so Windows SmartScreen shows a warning until you buy a code-signing certificate.

## 3. Android (APK)
**Cloud build:** run the same GitHub workflow and download `android-apk` (a debug APK you can sideload by enabling "install unknown apps").
**Local build** (Node.js, Android Studio):
```bash
npm install
npm run android:add
npm run android:open     # Android Studio opens: Build, Build APK(s)
```
For Google Play you need a signed release **AAB**, a Play Console account and a unique `appId` (edit `capacitor.config.json` and `package.json`).
Optional icons: `npx @capacitor/assets generate` (uses `assets/icon-only.png`).

## 4. iOS (iPhone / iPad)
Requires a **Mac with Xcode**. A free Apple ID installs to your own device for 7 days; distributing to others needs the paid Apple Developer Program.
```bash
npm install
npm run ios:add
npm run ios:open         # Xcode: choose your team, then Run / Archive
```
Without a Mac or developer account, use the PWA route (Safari, Add to Home Screen).

## Updating the app
Edit `app/index.html`, then `npm run sync` for mobile builds. For the PWA, change `V` in `app/sw.js` (for example `recon-v2`) so installed copies refresh.

## Notes on exporting
On Android and iOS apps, **Export CSV** opens the system share sheet (save to Files, email, Drive). On desktop it downloads normally.

---

# Evaluation

`python/evaluate.py` measures accuracy on synthetic data with known correct pairs (clean matches, fuzzy descriptions, date shifts, uninformative descriptions, amount mismatches, missing bank lines, bank-only fees, repeated amounts). It prints a confusion matrix (auto-accepted only, and Matched plus Review), precision, recall, F1, straight-through rate, review rate, and a threshold sweep. Run `reconcile_colab.py` first in Colab, or keep both files together locally, then run `python evaluate.py`.
Synthetic results are a guide only. Validate on one past, audited month of your own data before relying on the tool.


## Benchmark: v1 basic vs v2 engine

Synthetic data: 270 ledger entries, 267 bank lines, 257 true pairs (including batch payments), defaults auto 0.70 / review 0.50. Run `python evaluate.py` to reproduce.

| | Auto precision | Assisted recall | Assisted F1 | Straight-through | Time |
|---|---|---|---|---|---|
| v1 basic | 0.988 | 0.840 | 0.908 | 63.3% | 3.2 s |
| v2 engine | 1.000 | 0.938 | 0.966 | 73.0% | 0.04 s |

v2 scores 5,000 ledger rows in about 2 seconds. Results on real data will differ.


---

# Deploy on GitHub

1. **Create the repository:** on github.com choose **New repository**, name it (for example `smart-bank-reconciliation`), keep it Public (free Pages) or Private (Pages needs a paid plan), and do not add a README.
2. **Upload the project** from the project folder:
   ```bash
   git init
   git add .
   git commit -m "Smart bank reconciliation"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
   (Or use **Add file, Upload files** on the repo page and drag the contents in.)
3. **Turn on the web app:** repo **Settings, Pages, Source: GitHub Actions**. Every push to `main` then publishes `app/` automatically (`.github/workflows/pages.yml`). Your link is `https://YOUR_USERNAME.github.io/YOUR_REPO/`. Open it on a phone or PC and install it as an app.
4. **Windows and Android builds:** repo **Actions, Build apps, Run workflow**. Download the installer and APK from the run's Artifacts. (Pushing a tag such as `v1.0.0` also triggers it.)
5. **Colab link:** replace `YOUR_USERNAME` and `YOUR_REPO` in the badge at the top of this README. It then opens the notebook in Colab with one click.
6. Edit `LICENSE` (your name) and `appId` in `package.json` and `capacitor.config.json`.

Do not commit real bank data. The `.gitignore` excludes `node_modules`, `dist`, `android` and `ios`, but add `*.csv` if you keep real files in the folder.
