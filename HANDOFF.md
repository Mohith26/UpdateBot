# UpdateBot — Handoff (current as of 2026-05-18)

This document onboards a new agent or developer to UpdateBot. Read it end-to-end before touching code. The bot ships real investor decks and edits live Google Docs; mistakes are visible to LPs.

---

## 1. TL;DR for a fresh agent

UpdateBot is a Python automation for **Harbor Capital** (Austin real-estate PE firm) that turns property Slack updates into investor-facing Google Docs + monthly Slides decks. It runs as **3 scheduled Cloud Run jobs** on GCP, plus a **4th Cloud Run service** (Next.js admin dashboard) protected by IAP.

If you are picking this up cold, read in this order:

1. **This file** (you are here) — full current state, infra values, branch state, lessons learned
2. **`docs/TROUBLESHOOTING.md`** — runbook for debugging failures, decision tree, exact gcloud commands
3. **`docs/SECRETS_ROTATION.md`** — when/how to rotate the Secret Manager secrets
4. **`.context/qa_backlog.md`** + **`.context/qa_backlog_iter2.md`** — prioritized backlogs from both audit iterations
5. **`.context/slides_template_spec.md`** — spec for the (not-yet-built) Google Slides template
6. **`SETUP.md`** — one-time credential setup (mostly historical)

The codebase is small — about 30 minutes to read. Start at `main.py`, then `jobs/`, then `services/`, then `dashboard/`.

**User context:** the primary operator is Mohith (`MOHITH@harborcap.com`). Tech-comfortable but not a developer. Prefers concise communication, exact commands, and decisions surfaced with tradeoffs. Default to plain-language summaries with code blocks for any command he needs to run.

---

## 2. Current status (component-by-component)

| Component | Status | Notes |
|---|---|---|
| `slack-sync` job | **Working + verified end-to-end** | Reads Slack → Claude extract → Google Doc edit → advance `last_sync_timestamp`. Now **idempotent per month** (replaces existing month entry instead of stacking) with tone matching and `(vN)` version suffix on revisions. |
| `weekly-notify` job | **Working** | Posts doc review links to review channel. Keeps current behavior. A new `weekly-digest` job is *designed* (not yet built) to augment, not replace. |
| `monthly-report` job | **Deployed, not yet tested end-to-end** — blocked on Slides template | Has `--dry-run` flag that now writes a RunLog row with resolved placeholders for dashboard inspection (iter-2 fix). Detects unfilled `{{TAG}}` post-fill. |
| Admin dashboard | **Deployed** at `https://updatebot-dashboard-818467834208.us-central1.run.app/` | Next.js 14 on Cloud Run + IAP (`@harborcap.com` only). Self-polls RunLog while any row is `running`. Stale-running detection. Remediation links. |
| RunLog (Sheets tab) | **Wired into all 3 jobs** | `start_run` writes a `running` row; `finalize_run` updates columns B:H (preserving column A start timestamp). Crashed jobs leave `running` rows visible. |
| Test Property setup | **Working — used for live testing this session** | Slack channel populated with 4 fake updates; live doc has May 2026 entry built via merge cycles; March + earlier entries kept as tone references. |
| Real properties | **Not yet added** | User action — add rows to config sheet with full column data. |
| Slides template | **Not yet built** | User action — see `.context/slides_template_spec.md`. |
| `weekly-digest` job | **Designed (Q1–Q10 answered), not yet implemented** | New job to post per-property weekly Slack digests. Brainstorm in progress when handoff was requested. |

Next monthly-report firing: 2026-06-01 13:00 UTC (8am CT).

---

## 3. Infrastructure (single source of truth)

| Resource | Value |
|---|---|
| GCP Project | `harbor-updatebot` |
| Project Number | `818467834208` |
| Region | `us-central1` |
| Service Account | `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com` (ADC; **no JSON key** — org policy blocks key creation) |
| Artifact Registry repo | `us-central1-docker.pkg.dev/harbor-updatebot/updatebot/` |
| Jobs image | `…/updatebot/updatebot:latest` (Python jobs) |
| Dashboard image | `…/updatebot/dashboard:latest` (Next.js service) |
| Config Sheet ID | `1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A` |
| Review Channel ID | `C0B3FEUCDEY` |
| Dashboard URL (canonical) | `https://updatebot-dashboard-818467834208.us-central1.run.app/` |
| Dashboard URL (hash alias) | `https://updatebot-dashboard-enmf7qdi4q-uc.a.run.app/` (same service) |
| Dashboard auth | IAP, restricted to `domain:harborcap.com` |
| Latest dashboard revision | `updatebot-dashboard-00005-2g5` (as of 2026-05-18 deploy) |

**Secrets in Google Secret Manager:**

- `slack-bot-token` → Slack Bot Token (`xoxb-…`)
- `anthropic-api-key` → Anthropic API key
- `dashboard-password` → **orphaned** since IAP migration; safe to delete

**Org policies that affect this project (Harbor Cap GCP org):**

- `iam.disableServiceAccountKeyCreation` — blocks creating JSON keys for any SA. Always use ADC; never expect a JSON key path. This is why the dashboard uses ADC via `google.auth.GoogleAuth` and not a credentials file.
- `iam.allowedPolicyMemberDomains` (Domain Restricted Sharing) — blocks `allUsers` and external domains in IAM bindings. Only `harborcap.com` members allowed. This is why the dashboard uses IAP, not `--allow-unauthenticated`.

---

## 4. Schedules

| Job | Cron | When (CT) |
|---|---|---|
| `slack-sync` | `0 */4 * * *` | Every 4 hours |
| `weekly-notify` | `0 13 * * 1` | Mondays 8am CT |
| `monthly-report` | `0 13 1 * *` | 1st of month, 8am CT |
| `weekly-digest` (planned) | `0 22 * * 5` | Fridays 5pm CT (22:00 UTC) — to be created |

---

## 5. Repo layout

```
pattaya/
├── HANDOFF.md                    # this file
├── SETUP.md                      # one-time credential setup (mostly historical)
├── deploy.sh                     # full deploy: builds Python + dashboard images, deploys jobs + service, enables IAP
├── cloudbuild.yaml
├── Dockerfile                    # Python jobs container
├── requirements.txt
├── main.py                       # entrypoint: routes to job by CLI arg; supports `monthly-report --dry-run`
├── config.py                     # Property dataclass + config sheet load; validates cell_cash_balance at load
├── jobs/
│   ├── slack_sync.py             # Slack → Claude → Google Doc; idempotent per month w/ (vN) suffix
│   ├── weekly_notify.py          # Posts doc review links to Slack review channel
│   └── monthly_report.py         # Slides template → filled deck → Slack post; --dry-run writes RunLog
├── services/
│   ├── slack_client.py           # Slack Web API wrapper; 30d lookback; 429 retry w/ 30s cap; SlackRateLimitExceeded
│   ├── claude_client.py          # Anthropic wrapper; merge prompt + tone examples
│   ├── google_docs.py            # find_month_section / replace_section / read_recent_monthly_sections / prepend_update
│   ├── google_sheets.py          # Sheets API for config + last_sync timestamps
│   ├── google_slides.py          # Slides API; copy + fill + detect unfilled placeholders (widened field mask)
│   └── run_log.py                # RunLog Sheets tab: start_run + finalize_run (preserves col A)
├── dashboard/                    # Next.js 14 App Router + Tailwind, deployed to Cloud Run with IAP
│   ├── Dockerfile                # Multi-stage node:22-alpine standalone build
│   ├── app/
│   │   ├── page.tsx              # Server component, fetches RunLog + properties (force-dynamic)
│   │   ├── layout.tsx            # Reads X-Goog-Authenticated-User-Email from IAP
│   │   ├── components/
│   │   │   ├── RunsTable.tsx     # Self-polling; stale-running badge; remediation links; DRY-RUN badge; placeholders table
│   │   │   ├── PropertiesTable.tsx
│   │   │   ├── JobTriggers.tsx   # 4 trigger buttons; MONTHLY typed confirm; poll-refresh; IAP redirect detect
│   │   │   ├── StatusBadge.tsx
│   │   │   └── RefreshButton.tsx
│   │   └── api/jobs/run/route.ts # POST endpoint to trigger jobs via Cloud Run Admin API
│   ├── lib/sheets.ts             # ADC auth, fetchRuns + fetchProperties
│   └── lib/time.ts               # Relative + local time formatters with TZ
├── docs/
│   ├── TROUBLESHOOTING.md        # Runbook (READ THIS WHEN DEBUGGING)
│   └── SECRETS_ROTATION.md       # Rotation procedures
├── .context/                     # Working notes, gitignored
│   ├── qa_backlog.md             # Iter-1 audit findings + decisions
│   ├── qa_backlog_iter2.md       # Iter-2 audit findings + decisions
│   ├── slides_template_spec.md   # Spec for the (unbuilt) Slides template
│   └── attachments/              # User-provided files (log pastes, RunLog dumps, etc.)
└── UpdateBot Config Sheet.csv    # Example of config sheet schema
```

---

## 6. Config sheet schema (main tab, columns A–N)

| Col | Field | Notes |
|---|---|---|
| A | `property_name` | e.g. "1820 Aguila Azteca LLC" |
| B | `slack_channel_id` | e.g. `C0B463VURQQ` |
| C | `live_doc_id` | Google Doc for cumulative updates |
| D | `slides_template_id` | Google Slides template |
| E | `cell_cash_balance` | Format: `SHEET_ID:RANGE` e.g. `1abc…:Sheet1!B5`. **Validated at load time.** Empty is OK (renders as `[Data not available]` in deck). |
| F | `what_we_are_reading_doc_id` | Separate Doc with reading list |
| G | `address` |  |
| H | `purchase_date` |  |
| I | `purchase_price` |  |
| J | `size_sqft` |  |
| K | `num_units` |  |
| L | `year_built` |  |
| M | `market_name` |  |
| N | `last_sync_timestamp` | **Bot-managed.** Don't manually edit unless you intend to force re-sync. Empty = trigger 30d lookback. |

Main tab is read with range `A1:N200` (no tab prefix — main tab is NOT named "Sheet1").

## 7. RunLog sheet schema (separate tab named `RunLog`, columns A–H)

| Col | Field | Notes |
|---|---|---|
| A | `timestamp_utc` | **Start time** — written by `start_run`. **Never overwritten** by `finalize_run` (iter-2 fix). |
| B | `job_name` | `slack-sync` / `weekly-notify` / `monthly-report` / `monthly-report (dry-run)` |
| C | `status` | `running` / `success` / `partial` / `failed` |
| D | `properties_processed` |  |
| E | `properties_failed` |  |
| F | `duration_seconds` | Real wall-clock duration (computed at finalize). |
| G | `summary` | Short human-readable string. Dry-run starts with `"Dry-run:"`. |
| H | `details_json` | JSON array. For success: `[{name, status, urls?}]`. For dry-run: includes `placeholders: {…}` per property. |

`start_run` appends a `running` row. `finalize_run` updates **columns B:H only** of the same row by `row_key` (parsed from the `updatedRange` Google returns) — column A keeps the start timestamp so the dashboard shows the real "when" of the run, not "just now" after a long job finalizes. If `start_run` fails (e.g., RunLog tab missing), `finalize_run` gracefully falls back to `append_run`.

Dashboard reads rows 2–1000, reverses, slices first 25 (newest first).

---

## 8. Slides template placeholders (13 tags)

The `monthly-report` job copies the template and replaces these exact tags in `_resolve_replacements` (`jobs/monthly_report.py`):

| Tag | Source |
|---|---|
| `{{PROPERTY_NAME}}` | config sheet col A |
| `{{REPORT_PERIOD}}` | derived from current date (e.g. "Q2 2026") |
| `{{PROPERTY_UPDATES}}` | "Property Update" section of live doc, capped at ~250 words |
| `{{MARKET_UPDATE}}` | "Market Update" section of live doc |
| `{{CASH_BALANCE}}` | live read from sheet cell per col E |
| `{{WHAT_WE_ARE_READING}}` | dedicated doc (col F) or section in live doc |
| `{{ADDRESS}}` | col G |
| `{{PURCHASE_DATE}}` | col H |
| `{{PURCHASE_PRICE}}` | col I |
| `{{SIZE_SQFT}}` | col J |
| `{{NUM_UNITS}}` | col K |
| `{{YEAR_BUILT}}` | col L |
| `{{MARKET_NAME}}` | col M (market name itself, distinct from `{{MARKET_UPDATE}}` narrative) |

`find_unfilled_placeholders` now inspects shape text, table cells, and notes pages (iter-2 widened field mask). If any `{{TAG}}` survives the fill, the property is marked failed and the deck is **kept** for inspection (not deleted).

---

## 9. How to deploy / trigger / read logs

### Deploy (idempotent)

```bash
PATH="/opt/homebrew/bin:$PATH" bash deploy.sh
```

Builds both images via Cloud Build, deploys 3 jobs + 1 service, creates 3 scheduler triggers, enables IAP, binds `domain:harborcap.com`. End-to-end takes ~5–7 minutes.

**Preconditions** (deploy.sh fails fast if missing):

- OAuth consent screen configured (one-time, click-ops at https://console.cloud.google.com/apis/credentials/consent?project=harbor-updatebot — Internal user type, app name "UpdateBot Admin")
- IAP API enabled (deploy.sh enables it automatically on first run)

### Trigger a job

**From dashboard:** click a trigger button. Buttons: `slack-sync`, `weekly-notify`, `monthly-report (dry-run)`, `monthly-report`. Real monthly-report requires typing the word `MONTHLY` to confirm.

**From CLI:**

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync \
  --region=us-central1 --project=harbor-updatebot --wait
```

### Read job logs

See `docs/TROUBLESHOOTING.md` § 2 for full details. Quick recipe:

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="slack-sync"' \
  --limit=80 --format='value(timestamp,textPayload)' \
  --project=harbor-updatebot --order=asc \
  --freshness=24h
```

---

## 10. What's changed across iterations

### Iter 0 — bot deployment + dashboard build (pre-history)

- Built admin dashboard (Next.js + Cloud Run + IAP), wired to RunLog Sheets tab.
- Hardened the 3 Python jobs: per-property try/except, accurate Slack notifications, narrative length caps, cash-balance validation.
- Added `--dry-run` mode for `monthly-report`.
- Switched dashboard auth from Basic Auth to IAP (org policy blocked `allUsers`).
- Added trigger buttons in dashboard with confirms + auto-refresh.

### Iter 1 — audit-driven fixes

Four parallel read-only audit agents covered: dashboard UX, job runtime resilience, onboarding/maintenance, data model. Backlog: `.context/qa_backlog.md`.

Notable Iter 1 fixes:

- `services/run_log.py` introduced. `start_run` / `finalize_run` lifecycle wired into all jobs.
- `services/slack_client.py`: 30-day lookback cap on empty/ancient timestamps; 429 retry honoring `Retry-After`.
- `services/google_slides.py`: `find_unfilled_placeholders` for post-fill safety.
- `config.py`: validate `cell_cash_balance` format at load.
- Dashboard: timestamps in local time + TZ; IAP 401/403 → "Session expired"; `NEVER SYNCED` badge; `router.refresh()` after trigger; per-button disable; explicit missing-RunLog-tab error; `running` yellow badge.
- `docs/TROUBLESHOOTING.md` (254 lines) + `docs/SECRETS_ROTATION.md` (89 lines).

### Iter 2 — stress-test fixes (this session, early)

Backlog: `.context/qa_backlog_iter2.md`. All 9 P0 items landed inline (agents kept timing out, so done directly):

- **`services/slack_client.py`:** `MAX_RETRY_WAIT_SECONDS = 30` cap. When Slack's `Retry-After` exceeds 30s, raises `SlackRateLimitExceeded`. `jobs/slack_sync.py` catches it per-property and continues — one rate-limited channel no longer kills the entire run.
- **`services/run_log.py`:** `finalize_run` now writes to range `B{row}:H{row}` (not `A:H`) with a 7-column payload. Column A keeps the original start timestamp so the dashboard "When" stays honest.
- **`jobs/monthly_report.py`:** dry-run writes a RunLog row with `details_json` containing per-property resolved `placeholders` dict. Job label becomes `monthly-report (dry-run)` so the dashboard can distinguish.
- **`services/google_slides.py`:** widened field mask in `find_unfilled_placeholders` to cover table cells, element groups, and notes pages.
- **`config.py`:** `_validate_cell_cash_balance` uses `split(":", 1)` to match the consumer.
- **`dashboard/app/components/JobTriggers.tsx`:** post-trigger poll-refresh sequence at 5s/15s/30s/60s/120s/240s (instead of single 5s); real `monthly-report` requires typing `MONTHLY` via `prompt()` instead of one-click `confirm()`; `opaqueredirect` / `redirected` response detection so IAP session expiry surfaces as "Session expired" instead of generic Network Error.
- **`dashboard/app/components/RunsTable.tsx`:** stale-running "likely crashed" red treatment when a `running` row's age exceeds 2× typical duration; DRY-RUN badge when `jobName` or `summary` indicates dry-run; remediation links in expanded row (Cloud Run executions, logs, config sheet); inline `placeholders` table for dry-run details.

### Post-iter-2 features (this session, later)

- **Doc idempotency.** Slack-sync now finds the existing entry for the current month (`find_month_section`) and *merges* into it via a single atomic `batchUpdate` (delete + insert + paragraph styling) instead of always prepending. If no existing entry, falls back to prepend. New helpers in `services/google_docs.py`: `find_month_section`, `read_recent_monthly_sections`, `replace_section`, shared `_section_insert_requests`.
- **Tone matching.** Up to 3 prior monthly sections are passed to Claude as style reference. New `extract_property_updates` signature: `existing_section: str | None` and `tone_examples: list[str]`. When `existing_section` is set, prompt switches to a MERGE prompt that asks for a refreshed entry rather than a fresh summary.
- **Version suffix `(vN)`.** First merge of a month tags the heading `(v2)`, next `(v3)`, etc. Original un-suffixed entry is treated as implicit v1. Malformed suffixes (`(v)` with no digits) collapse back to `(v2)`. Logic lives in `_next_version_suffix` in `jobs/slack_sync.py`.
- **Dashboard self-polling.** `RunsTable.tsx` now drives its own polling: while any visible row has `status === "running"`, it calls `router.refresh()` every 10s and once on `visibilitychange` (when the tab returns to foreground). This is independent of trigger origin — cron runs benefit too, not just dashboard-initiated runs.

---

## 11. Active in-progress work — `weekly-digest`

A brainstorm was in progress when this handoff was requested. Design decisions made so far (Q1–Q10 from the brainstorming dialogue):

- **Q1 — Scope:** one Slack post per property (not aggregated).
- **Q2 — Channel:** posted to the property's own `slack_channel_id` (not to the review channel).
- **Q3 — Sections:** single section, no persistent "Partners Prospects" tracker (user changed from A→B during brainstorm).
- **Q5 — Grouping:** single "Weekly Updates:" section. No partner/direct split.
- **Q7 — Relation to weekly-notify:** AUGMENT — keep `weekly-notify` unchanged; add new feature alongside.
- **Q8 — Job structure:** new separate Cloud Run job `weekly-digest` with its own cron trigger.
- **Schedule:** Fridays 5pm CT (22:00 UTC), cron `0 22 * * 5`.
- **Q9 — Source:** past 7 days of Slack messages from the property channel + the live doc's current-month section as standing context.
- **Q10 — Tone:** internal/candid voice — direct, opinionated, no investor hedging (e.g., "X is dead", "Y is dragging their feet"). Match the user's pasted examples that include phrases like "horrible financials, we are moving on".

**Note on tone + audience:** the digest posts into the property's own Slack channel. If LPs are in that channel, the candid voice is a leak risk. **Worth confirming with the user before implementing** — either restrict the post to a partner-only channel, or shift to investor-grade voice.

**What was not yet decided / written down:**

- Exact format of the "doc has been updated" line (one-liner at top? at bottom? with link to the live doc?)
- Behavior when there were zero Slack messages in the past 7 days (skip the post entirely? post "No new updates this week"?)
- Whether to run a fresh `slack-sync` immediately before the digest to ensure doc is current, or just rely on the periodic 4-hour cron
- Few-shot examples in the prompt to anchor tone (the user pasted two example digests — those should be passed in)

**Next steps after design approval:** invoke `writing-plans` skill per brainstorming protocol. Output should be a detailed implementation plan covering: new `weekly_digest.py` job module; entrypoint route in `main.py`; new prompt in `services/claude_client.py`; new Cloud Scheduler trigger in `deploy.sh`; new RunLog row lifecycle; testing approach.

---

## 12. Pending user actions (only the user can do these)

1. **Build the Google Slides template** per `.context/slides_template_spec.md`. 3 slides, 13 placeholders. `{{PROPERTY_UPDATES}}` capped at 250 words to fit slide 1; user can confirm in real template, OR split into `_PART1` / `_PART2` if not.
2. **Add real properties to config sheet.** Currently only "Test Property". One row per property, columns A–N filled in.
3. **Invite `@UpdateBot` to all property Slack channels** (`/invite @UpdateBot` in each private channel). Scopes already granted.
4. **Share live docs + Slides templates with `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com`** as Editor (docs) / Viewer (Slides templates).
5. **Decide audience question for `weekly-digest`** — candid voice OK in property channel? Or shift to investor-grade?
6. **Optionally delete orphaned `dashboard-password` secret:**

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud secrets delete dashboard-password --project=harbor-updatebot
```

---

## 13. Branch state (current)

**Branch:** `Mohith26/continue-handoff` (tracking `origin/Mohith26/continue-handoff`)

**Pushed commits on top of `main`:**

```
4acf1eb slack-sync: tag merged monthly entries with (vN) suffix
10c77a2 dashboard: poll for running rows independent of trigger origin
3b0ad98 slack-sync: idempotent monthly entries with tone matching
cce5b13 Update HANDOFF.md with persona, invariants, and docs pointers
09ae9d7 Deploy: build/deploy dashboard service with IAP; add operator docs
fdf5f9d Add admin dashboard (Next.js on Cloud Run + IAP)
bee5385 Backend: per-run RunLog, dry-run mode, and resilience fixes
0983327 Add UpdateBot automation bot
```

**Working tree:** clean prior to this handoff edit. The pending `weekly-digest` feature is purely design (no code yet). This update to `HANDOFF.md` is the only uncommitted change once written.

**Deployed image timestamps (Artifact Registry):**

- Jobs: rebuilt 2026-05-18 17:47 UTC (latest, includes `(vN)` suffix)
- Dashboard: rebuilt 2026-05-18 17:48 UTC (latest, includes self-polling)

**No PR has been opened against `main` yet.** When the operator is satisfied with the live behavior, open a PR with the cumulative diff for review before merging.

---

## 14. Deferred items (iter-3 candidates)

From `.context/qa_backlog.md` + `.context/qa_backlog_iter2.md`:

- `triggered_by` column on RunLog (cron / manual / dry-run) — schema change + dashboard column
- Property failure indicator on dashboard PropertiesTable (read most-recent RunLog row per property)
- `details_json` 50KB Sheets cell size cap with truncation marker (not blocking at 1-property scale yet)
- Slack message ID audit trail (enable "replay this time window")
- `_resolve_oldest` 30d cap permanently abandons 31–365d window — at least log persistently per property
- Property uniqueness validation (collision on `slack_channel_id` / `live_doc_id`)
- Structured JSON Cloud Logging fields
- Mobile responsiveness audit
- Pagination beyond 25 RunLog rows on dashboard
- Scale-readiness audit (5–10 properties) — deferred from iter 2, agent timed out
- Deck quality audit — deferred from iter 2 (re-run when Slides template exists)
- IAP membership management documentation (partial in TROUBLESHOOTING.md)
- Schema-extension checklist for adding config columns (partial in TROUBLESHOOTING.md)

---

## 15. Lessons learned from this session

These are the non-obvious gotchas that bit us during testing and the resolutions, so the next agent doesn't have to rediscover them.

### 15.1 The bot is forward-only against Slack — deleting doc entries doesn't trigger re-sync

The bot tracks "what Slack messages I've processed" (via `last_sync_timestamp` in column N), not "what's in the doc." If you delete a section from the live doc, slack-sync will NOT rebuild it on the next run — it'll just see "no new Slack messages" and exit cleanly.

To force a rebuild of a deleted month: either (a) clear `last_sync_timestamp` for that property and re-run (triggers the 30d lookback cap, re-processes all recent messages and creates a fresh entry), or (b) paste a new Slack message and let the next sync pick it up (creates a fresh prepended entry since `find_month_section` returns `None` for the deleted month).

### 15.2 `cell_cash_balance` validation runs at load time and blocks ALL jobs

Any single malformed property in the config sheet blocks every job that calls `config.load_properties()` — including `slack-sync`, which doesn't use cash balance at all. This is intentional (fail fast) but a surprise during onboarding.

If you see `Failed to load properties: Invalid cell_cash_balance for property 'X'`: either fix the format to `SHEET_ID:RANGE` (e.g., `1abc…:Sheet1!B5`) or **clear the cell entirely** (empty is permitted and renders as `[Data not available]` in the deck).

### 15.3 Dashboard cache: `router.refresh()` doesn't fire when the tab is backgrounded

This bit us. The old `JobTriggers` post-trigger refresh schedule (5s/15s/30s/60s/120s/240s) relies on `setTimeout` firing client-side, but browsers throttle timers heavily for backgrounded tabs. A user who triggered a job, switched tabs, came back 5 minutes later, and saw the row still as `running` thought the job had crashed — when in fact the row had finalized in the sheet, the dashboard just hadn't re-fetched.

Fix shipped: `RunsTable.tsx` now self-polls every 10s while any row is `running`, and also calls `router.refresh()` on `visibilitychange` when the tab returns to foreground. Independent of who triggered the job, so cron runs benefit too.

Verification: 16:07 UTC slack-sync started, finalized at 16:08:04, dashboard kept showing `running` for >5 min until we fixed this. Compare logs (`gcloud logging read … job_name=slack-sync`) against the actual RunLog row state via direct Sheets read to distinguish "job crashed" from "dashboard stale" — almost always it's the latter.

### 15.4 `gcloud` reauth can wedge — `gcloud auth login` resets it

Google Workspace enforces periodic gcloud CLI reauth. Sometimes the password prompt repeats 3+ times even with the correct password. The fix is to bypass the inline reauth flow with a full re-login:

```bash
gcloud auth login
# (browser opens, sign in fresh with MOHITH@harborcap.com)
gcloud auth application-default login   # if ADC is also stale
```

Then re-run whatever you were doing.

### 15.5 `monthly-report (dry-run)` job_name needs base-name stripping for Cloud Run links

Since iter 2, dry-run RunLog rows have `job_name = "monthly-report (dry-run)"`. The Cloud Run jobs in the actual `gcloud run jobs` registry are named `monthly-report` (no parens). When constructing log/execution URLs in the dashboard, strip the `(dry-run)` suffix. There's a `jobBaseName()` helper in `RunsTable.tsx` for this.

### 15.6 Doc-idempotency edge case: same heading twice

If somehow the doc has two paragraphs both matching `^{Month} {Year} Update`, `find_month_section` returns only the **first** one, and slack-sync will merge into it. Stale duplicates further down survive. This was flagged as a "good enough" tradeoff vs. parsing the entire doc to deduplicate — but if it ever bites in production, the fix is to walk all matches and merge them together.

### 15.7 Always test deploy with `bash deploy.sh` end-to-end after changes

Idempotent and ~5–7 minutes. Cloud Build caches layers so successive deploys are fast. There's no "deploy just the dashboard" or "deploy just the jobs" mode — the script always does both. That's fine; it has not been a friction point.

### 15.8 The dashboard image was rebuilt today (2026-05-18) twice

If you're inspecting Artifact Registry timestamps to understand "what's deployed when", note that the post-iter-2 fix wave produced two deploys today:

- `10:51` UTC — iter-2 fixes (Slack cap, finalize column A, dry-run RunLog, dashboard poll-refresh, MONTHLY confirm, stale-running, remediation links, IAP redirect, DRY-RUN badge)
- `17:48` UTC — doc idempotency + (vN) suffix + dashboard self-polling

### 15.9 Test Property's current state (for resuming testing)

- `slack_channel_id`: still wired
- `cell_cash_balance`: **cleared** (was set to a sheet ID with no `:RANGE`, blocking jobs)
- `last_sync_timestamp`: advanced past the 4 fake updates pasted during testing
- Live doc: contains May 2026 entry (built via merge cycles in this session) + March 2026 and earlier entries (preserved as tone references)

If you want to test from scratch, clear `last_sync_timestamp` on the Test Property row to force re-sync against the existing Slack messages.

---

## 16. System invariants you must preserve

- **ADC only** — no JSON keys ever (org policy blocks them anyway). Local dev: `gcloud auth application-default login`. Cloud Run: attached SA.
- **Dashboard auth = IAP, `domain:harborcap.com` only.** `allUsers` bindings are silently rejected by org policy.
- **`last_sync_timestamp` in config sheet column N is bot-managed.** Do not overwrite from agent code; only `slack_sync.py` should write it.
- **RunLog `running` rows MUST be finalized in place via `finalize_run(row_key, …)`** — do not append a new terminal row. Otherwise crash detection (yellow `running` badge stuck forever) breaks.
- **`finalize_run` writes B:H only.** Column A is the start timestamp, set once by `start_run`. Do NOT widen back to A:H — long-running jobs would appear "just now" on the dashboard after they finalize.
- **`monthly-report` dry-run uses `job_label = "monthly-report (dry-run)"`** in RunLog. Anywhere downstream that maps `job_name` to a Cloud Run resource must strip `(dry-run)` first.
- **Doc edits must be atomic.** All `replace_section` operations go through a single Docs `batchUpdate` with `deleteContentRange` + `insertText` + style requests so a partial failure can't leave a deleted-but-not-replaced section.
- **Order of writes in slack-sync:** doc edit (prepend OR replace_section) MUST succeed before `last_sync_timestamp` advances. The current code preserves this; any future refactor must too. Otherwise crashed mid-write = lost Slack messages.
- **Cloud Run `monthly-report` job's default args are just `["monthly-report"]`.** The dashboard trigger API overrides args to `["monthly-report", "--dry-run"]` for dry-run via `overrides.containerOverrides[0].args` in `dashboard/app/api/jobs/run/route.ts`. This is also the extension point for adding `triggered_by` plumbing later.

---

## 17. Known sharp edges

- **`_extract_section` in `monthly_report.py` silently defaults missing sections to `"No updates this period."`** Deck can ship with that bland string if the live doc has no matching headings. Warning is logged but not surfaced on the dashboard.
- **`prepend_update` and `replace_section` are non-idempotent at the API level.** Current code preserves correctness via the `last_sync_timestamp`-after-write ordering, but a regression there would risk lost or duplicate messages.
- **`start_run`'s parse of `updatedRange`** assumes standard `Tab!A12:H12` shape. A tab rename that introduces brackets or unusual characters would break it.
- **Cron + manual triggers can collide.** Currently no locking; consequence is rare (2 RunLog rows for same property in same hour). For now, fine.
- **`find_unfilled_placeholders` widened mask covers shapes/tables/notes, but NOT slide masters or layout backgrounds.** Widen further if template style evolves.
- **Doc idempotency assumes a single heading per month per property.** Duplicate headings → only first is replaced.
- **The `dashboard-password` secret in Secret Manager is unused** (IAP migration orphaned it). Safe to delete; not yet deleted.

---

## 18. Commands to NEVER run autonomously without confirming with user

- Anything that modifies live secrets, IAM bindings, or schedulers (mutating GCP state outside dev)
- `git push --force` to shared branches
- `gcloud projects delete`
- Destructive operations on the config sheet (deleting properties, renaming columns, schema migrations)
- `gcloud run services delete` on `updatebot-dashboard` (would require full re-IAP setup to restore)
- `gcloud run jobs delete` on any of the three job names (would require re-creating cron triggers)

---

## 19. Helpful starter prompts

- **"Continue iter 3 from the backlog"** → start with `triggered_by` and property failure indicator (both have direct UX impact). Both are in the deferred list above.
- **"Add a new property"** → user does this manually via the config sheet, not you. See TROUBLESHOOTING.md § 7.
- **"Debug a failure"** → start with TROUBLESHOOTING.md decision tree, then dashboard inline-expand (it has remediation links now), then Cloud Logging via the gcloud commands in TROUBLESHOOTING.md § 2.
- **"Add a new placeholder to monthly-report"** → modify the slides template (user) + add to `_resolve_replacements` in `monthly_report.py` (you).
- **"Implement weekly-digest"** → resume the brainstorm in § 11, confirm the audience/tone question with the user, then invoke `writing-plans` per the brainstorming skill protocol. Do NOT write code until the plan is reviewed.

---

## 20. Notes on `.context/` directory

Gitignored. Contains working notes (audits, qa_backlog, slides spec, attachments) referenced from this handoff and TROUBLESHOOTING.md. If you've cloned the repo fresh, this directory won't exist — ask the user for the contents of `.context/qa_backlog.md`, `.context/qa_backlog_iter2.md`, and `.context/slides_template_spec.md` at minimum.

The most useful attachment from this session is `.context/attachments/pasted_text_2026-05-18_11-19-26.txt` — a raw export of the live RunLog tab as of mid-session. Useful for understanding what real data looks like.
