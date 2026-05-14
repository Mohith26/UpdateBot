# UpdateBot — One-Time Setup Guide

Complete these steps before running the bot for the first time. Each section tells you exactly where to go and what to copy.

---

## Step 1 — Slack App

1. Go to https://api.slack.com/apps → **Create New App** → **From Scratch**
2. Name it `UpdateBot`, select your Harbor Capital workspace
3. In the left sidebar → **OAuth & Permissions** → scroll to **Bot Token Scopes**
4. Add these scopes:
   - `channels:history`
   - `channels:read`
   - `chat:write`
5. Scroll up → **Install to Workspace** → Allow
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`) — you'll need this later
7. In Slack, add `@UpdateBot` to every property channel and to your review channel (e.g. `#property-updates-review`)
8. Get each property channel's ID: right-click the channel → **View channel details** → scroll to the bottom — the ID starts with `C`
9. Do the same for your review channel

---

## Step 2 — Anthropic API Key

1. Go to https://console.anthropic.com
2. Sign in (create an account if needed — this is separate from your claude.ai subscription)
3. Navigate to **API Keys** → **Create Key**
4. Copy the key — you'll only see it once

> **Note:** Check with your Anthropic account rep — your Enterprise plan may include API credits that apply here.

---

## Step 3 — Google Cloud Project

1. Go to https://console.cloud.google.com
2. Click the project dropdown at the top → **New Project**
3. Name it `harbor-updatebot`, select your Harbor Capital Workspace org → **Create**
4. Make sure this new project is selected

**Enable APIs** (do all four):
- Go to **APIs & Services** → **Enable APIs and Services**
- Search and enable each:
  - Google Docs API
  - Google Sheets API
  - Google Slides API
  - Google Drive API

**Create a Service Account:**
1. Go to **IAM & Admin** → **Service Accounts** → **Create Service Account**
2. Name: `updatebot-sa` → **Create and Continue** → **Done**
3. No need to create or download a JSON key — the bot uses Application Default Credentials (ADC) instead

**Copy the service account email** (looks like `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com`) — you'll use it to share files and attach it to Cloud Run.

---

## Step 4 — Share Google Drive Files with the Bot

For each property, share the following files with the service account email (as **Editor**):
- The property's live Google Doc (where Slack updates are appended)
- The property's "What We're Reading" Google Doc (maintained manually each quarter)
- The property's Google Sheet with financials (cash balance cell)
- The Slides template

Also share the **UpdateBot Config Sheet** (Step 6 below) with the service account email as **Editor**.

---

## Step 5 — Add Placeholders to Your Slides Template

Your template follows the same 3-slide format as the Aquila Azteca example. Open your Google Slides template and replace the corresponding text with these exact tags:

**Slide 1 — Property Updates + Project Details**

| Tag | Replaces |
|---|---|
| `{{PROPERTY_NAME}}` | Entity name, e.g. "1820 Aguila Azteca LLC" — appears in header on every slide |
| `{{REPORT_PERIOD}}` | Period label, e.g. "Q1 2026 Update" — appears in header on every slide |
| `{{PROPERTY_UPDATES}}` | The full property narrative (leasing activity, tenant status, broker updates, strategy) |
| `{{ADDRESS}}` | Property address |
| `{{PURCHASE_DATE}}` | Purchase date |
| `{{PURCHASE_PRICE}}` | Purchase price |
| `{{SIZE_SQFT}}` | Building size in sq ft |
| `{{NUM_UNITS}}` | Number of units/suites |
| `{{YEAR_BUILT}}` | Year built |

**Slide 2 — Financial Updates + What We're Reading**

| Tag | Replaces | Source |
|---|---|---|
| `{{CASH_BALANCE}}` | Cash and reserve balance figure, e.g. "$453,199" | Google Sheet cell |
| `{{WHAT_WE_ARE_READING}}` | Full list of articles and sources | Dedicated Google Doc |

**Slide 3 — Market Update**

| Tag | Replaces |
|---|---|
| `{{MARKET_NAME}}` | Market name, e.g. "Laredo" |
| `{{MARKET_UPDATE}}` | Full market analysis narrative |

> The bot always makes a fresh copy of the template each period — your original is never modified.

---

## Step 6 — Create the UpdateBot Config Sheet

1. In Google Drive, create a new Google Sheet named **UpdateBot Config**
2. Set up the header row in row 1 with these exact column names (A through O):

| Col | Header | Example value |
|---|---|---|
| A | `property_name` | 1820 Aguila Azteca LLC |
| B | `slack_channel_id` | C0123ABC |
| C | `live_doc_id` | *(Google Doc ID for property updates)* |
| D | `slides_template_id` | *(Google Slides template ID)* |
| E | `cell_cash_balance` | `1QSXur21Kc...:Sheet1!B5` — Sheet ID, colon, then cell reference |
| F | `what_we_are_reading_doc_id` | *(Google Doc ID for reading list)* |
| G | `address` | 1820 Aguila Azteca Dr, Laredo, TX 78043 |
| H | `purchase_date` | 4/24/2025 |
| I | `purchase_price` | $12,960,000 |
| J | `size_sqft` | 108,248 sq ft |
| K | `num_units` | 2 |
| L | `year_built` | 2000 |
| M | `market_name` | Laredo |
| N | `last_sync_timestamp` | *(leave blank — bot fills this automatically)* |

3. Add one row per property, filling in each column.

**"What We're Reading" doc:** Create a separate Google Doc per property where your team pastes in the article titles and sources each quarter. The bot reads it verbatim and drops it into the slide. Share this doc with the service account email.

**How to get a file ID:** Open the Google Doc/Sheet/Slides file → the ID is the long string in the URL between `/d/` and `/edit`.

---

## Step 7 — Store Secrets in Google Secret Manager

1. In the GCP console → **Security** → **Secret Manager** → **Enable API** if prompted
2. Create two secrets (no Google credential needed — Cloud Run uses the attached service account directly):

| Secret name | Value |
|---|---|
| `slack-bot-token` | Your `xoxb-...` Bot Token from Step 1 |
| `anthropic-api-key` | Your Anthropic API key from Step 2 |

For each: **Create Secret** → paste the value → **Create Secret Version**

**For local testing:** Instead of a JSON key, run this once in your terminal:
```
gcloud auth application-default login
```
This lets the code on your laptop authenticate with your own Google account during development.

---

## Step 8 — Note Your IDs

Collect these before deployment:

- [ ] Config Sheet ID (from its URL)
- [ ] Review Channel ID (from Slack, e.g. `C0456DEF`)
- [ ] GCP Project ID (shown in the GCP console header)

You'll set these as environment variables during the Cloud Run deployment step.

---

Once all steps above are done, you're ready to deploy. Run the developer setup to verify credentials work before deploying to the cloud.
