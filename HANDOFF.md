# UpdateBot — Handoff Document

## What This Is

UpdateBot is a Python automation bot for Harbor Capital (Austin real estate PE firm). It reads property Slack channels, uses Claude AI to extract structured updates, appends them to per-property Google Docs, and compiles monthly investor slide decks. It runs as three scheduled Cloud Run jobs on GCP.

---

## Current Status (as of May 2026)

| Job | Status |
|---|---|
| `slack-sync` | **Working** — confirmed end-to-end: reads Slack, extracts with Claude, writes to Google Doc |
| `weekly-notify` | **Working** — confirmed: posts doc review links to Slack review channel |
| `monthly-report` | **Deployed but not yet end-to-end tested** — Slides template placeholders need to be set up |

The `monthly-report` job will not run until June 1 (scheduled for 1st of month). It needs a real Slides template with `{{PLACEHOLDER}}` tags before it can be tested.

---

## Infrastructure

| Resource | Value |
|---|---|
| GCP Project | `harbor-updatebot` |
| Region | `us-central1` |
| Service Account | `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com` |
| Artifact Registry image | `us-central1-docker.pkg.dev/harbor-updatebot/updatebot/updatebot:latest` |
| Config Sheet ID | `1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A` |
| Review Channel ID | `C0B3FEUCDEY` |

**Secrets in Google Secret Manager:**
- `slack-bot-token` → Slack Bot Token (`xoxb-...`)
- `anthropic-api-key` → Anthropic API key

**Auth:** Application Default Credentials (ADC) — no JSON key. Cloud Run uses the attached service account directly. For local development, run `gcloud auth application-default login`.

---

## Schedules

| Job | Cron | When |
|---|---|---|
| `slack-sync` | `0 */4 * * *` | Every 4 hours |
| `weekly-notify` | `0 13 * * 1` | Mondays 8am CT |
| `monthly-report` | `0 13 1 * *` | 1st of month 8am CT |

---

## File Structure

```
UpdateBot/
├── main.py                        # Entrypoint — routes to job by CLI arg
├── config.py                      # Reads config sheet, Property dataclass
├── jobs/
│   ├── slack_sync.py              # Job 1: Slack → Claude → Google Doc
│   ├── weekly_notify.py           # Job 2: Post doc review links to Slack
│   └── monthly_report.py          # Job 3: Fill Slides template, notify analysts
├── services/
│   ├── slack_client.py            # Slack Web API wrapper
│   ├── claude_client.py           # Anthropic API wrapper (extracts 5-section updates)
│   ├── google_docs.py             # Google Docs API (read + prepend with HEADING styles)
│   ├── google_sheets.py           # Google Sheets API (config reads + timestamp writes)
│   └── google_slides.py           # Google Slides API (copy template + fill placeholders)
├── deploy.sh                      # Full deploy script (build + Cloud Run + Scheduler)
├── SETUP.md                       # One-time credential setup guide
└── UpdateBot Config Sheet.csv     # Example of the config sheet structure
```

---

## Config Sheet Structure

The bot reads from a Google Sheet (`CONFIG_SHEET_ID`). One row per property, columns A–N:

| Col | Field | Notes |
|---|---|---|
| A | `property_name` | e.g. "1820 Aguila Azteca LLC" |
| B | `slack_channel_id` | e.g. `C0B463VURQQ` |
| C | `live_doc_id` | Google Doc ID for cumulative updates |
| D | `slides_template_id` | Google Slides template ID |
| E | `cell_cash_balance` | Format: `SHEET_ID:RANGE` e.g. `1abc...:Sheet1!B5` |
| F | `what_we_are_reading_doc_id` | Separate Google Doc with reading list |
| G | `address` | Property address |
| H | `purchase_date` | e.g. `4/24/2025` |
| I | `purchase_price` | e.g. `$12,960,000` |
| J | `size_sqft` | e.g. `108,248 sq ft` |
| K | `num_units` | Number of suites/units |
| L | `year_built` | e.g. `2000` |
| M | `market_name` | e.g. `Laredo` |
| N | `last_sync_timestamp` | Auto-filled by bot (Slack message timestamp) |

**Important:** The config sheet tab is NOT named "Sheet1" — the bot reads with range `A1:N200` (no sheet tab prefix).

---

## Google Doc Format (slack-sync output)

Each sync run prepends a new entry to the top of the live Google Doc. Format:

```
[Month Year] Update - [Property Name]     ← HEADING_2

Hi [Name],

Property Update                            ← HEADING_3
[narrative paragraph]

Active Prospects                           ← HEADING_3
- [Name] — [sq ft], [term], [status]

[Market Name] Market Update               ← HEADING_3
[narrative paragraph]

Financial Update                           ← HEADING_3
Cash Balance: [amount]
[other financial notes]

What We're Reading                         ← HEADING_3
- [article title / source]

────────────────────────────────────────────────────────────
```

---

## Slides Template Placeholders

The `monthly-report` job copies the template and replaces these exact tags:

| Tag | Source |
|---|---|
| `{{PROPERTY_NAME}}` | Config sheet |
| `{{REPORT_PERIOD}}` | Auto-generated (e.g. "Q2 2026") |
| `{{PROPERTY_UPDATES}}` | Extracted from live doc "Property Update" section |
| `{{MARKET_UPDATE}}` | Extracted from live doc "Market Update" section |
| `{{CASH_BALANCE}}` | Read live from Google Sheet cell |
| `{{WHAT_WE_ARE_READING}}` | Read from dedicated "What We're Reading" Google Doc |
| `{{ADDRESS}}` | Config sheet |
| `{{PURCHASE_DATE}}` | Config sheet |
| `{{PURCHASE_PRICE}}` | Config sheet |
| `{{SIZE_SQFT}}` | Config sheet |
| `{{NUM_UNITS}}` | Config sheet |
| `{{YEAR_BUILT}}` | Config sheet |
| `{{MARKET_NAME}}` | Config sheet |

---

## Slack App Scopes Required

The Slack bot (`xoxb-...`) needs these OAuth scopes:
- `channels:history` — read public channel messages
- `channels:read` — list public channels
- `groups:history` — read private channel messages (**required — property channels are private**)
- `groups:read` — list private channels
- `chat:write` — post messages

---

## How to Deploy

```bash
PATH="/opt/homebrew/bin:$PATH" bash deploy.sh
```

This script: enables APIs, grants IAM roles, builds the Docker image via Cloud Build (remote — no local Docker needed), creates/updates the 3 Cloud Run jobs, and creates the 3 Cloud Scheduler triggers. Idempotent — safe to run multiple times.

## How to Manually Trigger a Job

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync --region=us-central1 --project=harbor-updatebot
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute weekly-notify --region=us-central1 --project=harbor-updatebot
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute monthly-report --region=us-central1 --project=harbor-updatebot
```

## How to Read Job Logs

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=slack-sync" --limit=30 --format="value(textPayload)" --project=harbor-updatebot
```

Replace `slack-sync` with `weekly-notify` or `monthly-report` as needed.

---

## What Still Needs to Be Done

1. **Set up the real Slides template** — open the Google Slides template for each property, add `{{PLACEHOLDER}}` tags per the table above, then add the Slides file ID to the config sheet column D. See `SETUP.md` Step 5 for details.

2. **Test `monthly-report` end-to-end** — once the template has placeholders, manually trigger the job and verify a filled deck appears in Google Drive and the review channel gets a Slack notification.

3. **Add real properties to the config sheet** — currently only "Test Property" is in the sheet. Add one row per real property with all columns filled in.

4. **Invite @UpdateBot to all property Slack channels** — run `/invite @UpdateBot` in each private property channel so the bot can read messages.

5. **Populate last_sync_timestamp for real properties** — on first run, leaving `last_sync_timestamp` blank makes the bot read ALL channel history. If the channel has a long history, consider setting the timestamp to a recent date to avoid processing old messages.

---

## Known Issues / Gotchas

- **gcloud not in PATH on Mac** — prefix all gcloud commands with `PATH="/opt/homebrew/bin:$PATH"` if you get "command not found".
- **Config sheet tab name** — the sheet's tab is not named "Sheet1". The bot reads with range `A1:N200` (no tab prefix). `write_cell` also uses just the cell ref (e.g. `N2`) without a tab prefix.
- **cell_cash_balance format** — must be `SHEET_ID:RANGE` with a colon separator, e.g. `1QSXur21Kc...:Sheet1!B5`. The sheet ID is the long string from the URL.
- **Private Slack channels** — require `groups:history` and `groups:read` scopes (not just `channels:history`). These have been added.
- **ADC on local machine** — run `gcloud auth application-default login` once before local testing. Cloud Run uses the attached service account automatically.
