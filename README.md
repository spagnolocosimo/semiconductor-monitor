# Semiconductor Capital Return Monitor

Deployable static website + GitHub Actions scheduled price updater. Tracks SMH, SOXX, MU, NVDA, TSM, ASML, AMAT and LRCX.

## Publish and automate
1. Create a GitHub repository and upload **all files**, preserving `.github/workflows/update.yml` and `data/`.
2. In repository **Settings → Pages**, choose **Deploy from a branch**, `main` and `/ (root)`. Save.
3. In **Actions**, open **Update semiconductor monitor**, click **Run workflow** to test the update. Confirm a commit to `data/latest.json` and visit the GitHub Pages URL.
4. GitHub Actions is scheduled at 20:00 and 21:00 UTC weekdays. `update.py` permits only the matching **22:00 Europe/Amsterdam** run, handling CET/CEST automatically. GitHub scheduled runs can be delayed; this is best-effort, not a precise SLA.
5. If automatic commits are blocked, set **Settings → Actions → General → Workflow permissions → Read and write permissions**. Repository branch protections may also prevent commits.

## Data boundaries
- Prices: `yfinance`, most recent **completed** US trading session. At 22:00 Amsterdam the NYSE may still be open; no partial session is presented as a close. Weekly closes use Friday-ending resampling.
- ETF flows: **not automatically available from yfinance**. Add source-verified full-week net creation/redemption observations to `data/curated_evidence.json`. Required fields: `ticker`, `window_end` (YYYY-MM-DD), `window_type`=`full_week`, `net_usd_m`, `source`, `verified`: true.
- Fund trades: add dated sourced records to the same JSON. Required: `date`, `ticker`, `manager`, `action`=`BUY`/`SELL`, `shares`, `source`, `verified`: true. Only mark `net_buying_verified`: true when the manager's net buying for the evaluation window is supported, not merely an isolated buy.
- SEC 13F: preloaded Appaloosa Q2/Q3 directly checked. Quarterly holdings do **not** reveal trade dates or shorts. Expand with independently verified filings, not secondary guesses.
- **Green** requires both ETF stabilization, verified positive flows in two of three recent weeks, and net-buying evidence from two independent managers. **Yellow** means incomplete/early recovery. **Red** indicates clear price deterioration. **Unknown** when fresh prices cannot be retrieved.
- The site is *not* a continuously running hosted server. GitHub Pages serves the published files; the scheduled Action commits updated JSON. It will not auto-fetch private/paid institutional feeds.

## Local test
`pip install -r requirements.txt && python update.py && python -m http.server 8000`, then open `http://localhost:8000`. Manual runs ignore the 22:00 gate.
