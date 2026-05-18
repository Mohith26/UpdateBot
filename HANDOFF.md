# UpdateBot — Handoff (current as of 2026-05-15)

## TL;DR for a fresh agent

UpdateBot is a Python automation for Harbor Capital (Austin real-estate PE firm) that turns property Slack updates into investor-facing Google Docs + monthly Slides decks. It runs as 3 scheduled Cloud Run **jobs** on GCP, plus a 4th Cloud Run **service** (Next.js admin dashboard) protected by IAP.

If you're picking up this project cold, read in this order:
1. **This file** (you are here) — current state, infra values, branch state
2. **`docs/TROUBLESHOOTING.md`** — runbook for debugging failures, every common error + fix, exact gcloud commands
3. **`docs/SECRETS_ROTATION.md`** — when/how to rotate the 2 Secret Manager secrets
4. **`.context/qa_backlog.md`** — prioritized backlog from iteration-1 audit; what's fixed vs deferred
5. **`.context/slides_template_spec.md`** — spec for the (not-yet-built) Google Slides template
6. **`.context/audit_onboarding.md`** + the agent-summary findings inline in conversation history if available — full audit details
7. **`SETUP.md`** — one-time credential setup (mostly historical; most is already done)

The codebase is small enough to read in ~30 min. Start with `main.py` then jobs/ then services/ then dashboard/.

---

## Current status (component-by-component)

| Component | Status | Notes |
|---|---|---|
| `slack-sync` job | **Working** — last verified 2026-05-14 with Test Property | Reads Slack → Claude extract → prepend to Google Doc → update `last_sync_timestamp`. Per-property try/except, 30d lookback cap on empty/ancient timestamps, Slack 429 retry. |
| `weekly-notify` job | **Working** | Posts doc review links to review channel. Status logic distinguishes doc-assembly success from Slack-post success. |
| `monthly-report` job | **Deployed, not yet tested end-to-end** — blocked on Slides template | Has `--dry-run` flag for preview without writes. Detects unfilled `{{PLACEHOLDER}}` post-fill and marks property as failed without deleting the deck. |
| Admin dashboard | **Deployed** at `https://updatebot-dashboard-818467834208.us-central1.run.app/` | Next.js 14 on Cloud Run with IAP. Shows recent RunLog rows, property status, trigger buttons. |
| RunLog (Sheets tab) | **Wired into all 3 jobs** | Each job writes a `running` row at start, updates to terminal status at end. Crashed jobs leave `running` rows visible on dashboard. |
| Test Property setup | **Working** | One row in config sheet. Slack channel set up, doc shared with SA. |
| Real properties | **Not yet added** | User action — add rows to config sheet with full column data. |
| Slides template | **Not yet built** | Spec in `.context/slides_template_spec.md`. User action — build in Google Slides per spec (3 slides, 13 placeholder tags, cap `{{PROPERTY_UPDATES}}` to ~250 words). |

The `monthly-report` cron is scheduled for the 1st of each month at 8am CT (13:00 UTC). Next firing is 2026-06-01.

---

## Infrastructure

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
| Dashboard URL | `https://updatebot-dashboard-818467834208.us-central1.run.app/` |
| Dashboard auth | IAP, restricted to `domain:harborcap.com` (Google sign-in) |

**Secrets in Google Secret Manager:**
- `slack-bot-token` → Slack Bot Token (`xoxb-…`)
- `anthropic-api-key` → Anthropic API key
- `dashboard-password` → **orphaned**, IAP replaced it; safe to delete (`gcloud secrets delete dashboard-password`)

**Org policies that affect this project (Harbor Cap GCP org):**
- `iam.disableServiceAccountKeyCreation` — **blocks creating JSON keys for any SA**. Always use ADC; never expect a JSON key path.
- `iam.allowedPolicyMemberDomains` (Domain Restricted Sharing) — **blocks `allUsers` and external domains in IAM bindings**. Only `harborcap.com` members allowed. This is why dashboard uses IAP, not `--allow-unauthenticated`.

---

## Schedules

| Job | Cron | When |
|---|---|---|
| `slack-sync` | `0 */4 * * *` | Every 4 hours |
| `weekly-notify` | `0 13 * * 1` | Mondays 8am CT |
| `monthly-report` | `0 13 1 * *` | 1st of month, 8am CT |

---

## Repo layout

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
│   ├── slack_sync.py             # Slack → Claude → Google Doc
│   ├── weekly_notify.py          # Posts doc review links to Slack
│   └── monthly_report.py         # Slides template → filled deck → Slack post
├── services/
│   ├── slack_client.py           # Slack Web API wrapper; 30d lookback cap; 429 retry
│   ├── claude_client.py          # Anthropic API wrapper
│   ├── google_docs.py            # Google Docs read + prepend with HEADING styles
│   ├── google_sheets.py          # Sheets API for config + last_sync timestamps
│   ├── google_slides.py          # Slides API; copy + fill + detect unfilled placeholders
│   └── run_log.py                # RunLog Sheets tab: start_run + finalize_run lifecycle
├── dashboard/                    # Next.js 14 App Router + Tailwind
│   ├── Dockerfile                # Multi-stage node:22-alpine standalone build
│   ├── app/
│   │   ├── page.tsx              # Server component, fetches RunLog + properties
│   │   ├── layout.tsx            # Reads `X-Goog-Authenticated-User-Email` from IAP
│   │   ├── components/           # RunsTable, PropertiesTable, JobTriggers, StatusBadge, RefreshButton
│   │   └── api/jobs/run/route.ts # POST endpoint to trigger jobs via Cloud Run Admin API
│   ├── lib/sheets.ts             # ADC auth, fetchRuns + fetchProperties
│   └── lib/time.ts               # Relative + local time formatters with TZ
├── docs/
│   ├── TROUBLESHOOTING.md        # Runbook (READ THIS WHEN DEBUGGING)
│   └── SECRETS_ROTATION.md       # Rotation procedures
├── .context/                     # Working notes, gitignored
│   ├── qa_backlog.md             # Iteration-1 audit findings + decisions
│   ├── slides_template_spec.md   # Spec for the (unbuilt) Slides template
│   ├── monthly_report_audit.md   # Earlier audit, already fixed
│   ├── audit_onboarding.md       # Onboarding gaps audit (iter 1)
│   └── attachments/              # User-provided files (pptx, log pastes, etc.)
└── UpdateBot Config Sheet.csv    # Example of config sheet schema
```

---

<a id="config-sheet-structure"></a>
## Config sheet schema (columns A–N)

| Col | Field | Notes |
|---|---|---|
| A | `property_name` | e.g. "1820 Aguila Azteca LLC" |
| B | `slack_channel_id` | e.g. `C0B463VURQQ` |
| C | `live_doc_id` | Google Doc for cumulative updates |
| D | `slides_template_id` | Google Slides template |
| E | `cell_cash_balance` | Format: `SHEET_ID:RANGE` e.g. `1abc…:Sheet1!B5`. **Validated at load time** since iter 1. |
| F | `what_we_are_reading_doc_id` | Separate Doc with reading list |
| G | `address` |  |
| H | `purchase_date` |  |
| I | `purchase_price` |  |
| J | `size_sqft` |  |
| K | `num_units` |  |
| L | `year_built` |  |
| M | `market_name` |  |
| N | `last_sync_timestamp` | **Bot-managed.** Don't manually edit. |

Main tab read with range `A1:N200` (no tab prefix — main tab is NOT named "Sheet1").

## RunLog sheet schema (separate tab named `RunLog`, columns A–H)

| Col | Field | Notes |
|---|---|---|
| A | `timestamp_utc` | ISO 8601 |
| B | `job_name` | `slack-sync` / `weekly-notify` / `monthly-report` |
| C | `status` | `running` / `success` / `partial` / `failed` |
| D | `properties_processed` |  |
| E | `properties_failed` |  |
| F | `duration_seconds` |  |
| G | `summary` | Short human-readable string |
| H | `details_json` | JSON array `[{name, status, error?, urls?}]` |

A `running` row is written at job start by `start_run()`; the same row is updated to terminal status at end by `finalize_run()`. If a job crashes mid-run, the `running` row stays visible on the dashboard — that's the operator's signal something died. **Legacy fallback:** if `start_run()` fails (e.g. RunLog tab missing), `finalize_run()` falls back to `append_run()` to write a single terminal row at end. So a missing RunLog tab gracefully degrades to "no row written" rather than crashing the job.

<a id="slides-template-placeholders"></a>
## Slides template placeholders (13 tags)

The `monthly-report` job copies the template and replaces these exact tags in `_resolve_replacements` (`jobs/monthly_report.py`):

| Tag | Source |
|---|---|
| `{{PROPERTY_NAME}}` | config sheet col A |
| `{{REPORT_PERIOD}}` | derived from current date (e.g. "Q2 2026") |
| `{{PROPERTY_UPDATES}}` | "Property Update" section of live doc, capped at ~250 words |
| `{{MARKET_UPDATE}}` | "Market Update" section of live doc |
| `{{CASH_BALANCE}}` | live read from sheet cell per col E (`SHEET_ID:RANGE`) |
| `{{WHAT_WE_ARE_READING}}` | dedicated doc (col F) or section in live doc |
| `{{ADDRESS}}` | col G |
| `{{PURCHASE_DATE}}` | col H |
| `{{PURCHASE_PRICE}}` | col I |
| `{{SIZE_SQFT}}` | col J |
| `{{NUM_UNITS}}` | col K |
| `{{YEAR_BUILT}}` | col L |
| `{{MARKET_NAME}}` | col M (the market name itself, e.g. "Laredo" — distinct from `{{MARKET_UPDATE}}` which is the narrative) |

If the template ever introduces a new tag not in this list, `find_unfilled_placeholders()` will detect it and mark the property as failed. To add a new tag: add it to `_resolve_replacements`, add a column / data source if needed, and rebuild the template.

See `.context/slides_template_spec.md` (gitignored — see notes below) for the layout spec.

---

## How to deploy

```bash
PATH="/opt/homebrew/bin:$PATH" bash deploy.sh
```

Idempotent. Builds both images via Cloud Build, deploys 3 jobs + 1 service, creates 3 scheduler triggers, enables IAP on the dashboard, binds `domain:harborcap.com` for access.

**Preconditions** (deploy.sh fails fast if missing):
- OAuth consent screen configured (one-time, click-ops at https://console.cloud.google.com/apis/credentials/consent?project=harbor-updatebot — Internal user type, app name "UpdateBot Admin")
- IAP API enabled (deploy.sh enables it automatically on first run)

## How to manually trigger jobs

**From dashboard:** click a trigger button. (Buttons: slack-sync / weekly-notify / monthly-report dry-run / monthly-report).

**From CLI:**
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync --region=us-central1 --project=harbor-updatebot --wait
```

## How to read job logs

See `docs/TROUBLESHOOTING.md` § 2 for the full gcloud logging command per job. Quick one-liner:

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=slack-sync" \
  --limit=50 --format='value(textPayload)' --project=harbor-updatebot --freshness=24h
```

---

## Recent changes (2026-05-12 to 2026-05-15)

### Iteration 0 — Bot deployment + dashboard build
- Built admin dashboard (Next.js + Cloud Run + IAP), wired to RunLog Sheets tab
- Hardened the 3 Python jobs after a code audit: per-property try/except, accurate Slack notifications, narrative length caps, cash-balance validation
- Added `--dry-run` mode for `monthly-report`
- Switched dashboard auth from Basic Auth to IAP after discovering org policy blocked `allUsers`
- Added trigger buttons in dashboard with confirms + auto-refresh

### Iteration 1 — Audit-driven fixes (this iteration)
4 parallel read-only audit agents covered: dashboard UX, job runtime resilience, onboarding/maintenance, data model. Triage and fix in `.context/qa_backlog.md`.

Backend (Python):
- `services/run_log.py`: new `start_run()` / `finalize_run()` for crash detection — RunLog row written at job start, updated at end
- `services/slack_client.py`: 30-day lookback cap when `last_sync_timestamp` is empty/ancient; Slack 429 retry honoring `Retry-After`
- `services/google_slides.py`: `find_unfilled_placeholders()` to detect literal `{{TAG}}` patterns surviving the fill; deck is NOT deleted on failure (operator inspects)
- `config.py`: validate `cell_cash_balance` format at load (raises with clear error)
- `jobs/weekly_notify.py`: cleaner status logic separating doc-assembly success from Slack-post success
- `jobs/monthly_report.py`: marks property as failed if unfilled placeholders detected

Dashboard (TypeScript):
- Timestamps now show local time + TZ abbreviation, not just relative
- IAP 401/403 detection → "Session expired" callout
- "NEVER SYNCED" red badge for empty `lastSync`
- `router.refresh()` 5s after successful trigger
- Per-button disable (can queue multiple jobs)
- Actionable empty-state copy
- Missing `RunLog` tab surfaces as explicit error
- `running` status renders as yellow badge

Docs:
- `docs/TROUBLESHOOTING.md` (254 lines)
- `docs/SECRETS_ROTATION.md` (89 lines)

---

## Pending user actions (only the user can do these)

These remain blocked on real-world setup and were intentionally not auto-fixed:

1. **Build the Google Slides template** per `.context/slides_template_spec.md`. 3 slides, 13 placeholders. Open issue from spec: `{{PROPERTY_UPDATES}}` body overflows slide 1 → 250-word cap already applied in code; user can confirm this looks OK in real template OR split into `_PART1` / `_PART2` if not.
2. **Add real properties to config sheet** — currently only "Test Property". One row per property, columns A–N filled in.
3. **Invite `@UpdateBot` to all property Slack channels** — `/invite @UpdateBot` in each private channel. Required scopes already granted.
4. **Share live docs + Slides templates with `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com`** as Editor (docs) / Viewer (Slides templates).
5. **Optionally delete the orphaned `dashboard-password` secret:**
   ```bash
   PATH="/opt/homebrew/bin:$PATH" gcloud secrets delete dashboard-password --project=harbor-updatebot
   ```

---

## Branch state (uncommitted work)

Current branch: **`Mohith26/continue-handoff`** (tracking `origin/Mohith26/continue-handoff`)

Substantial uncommitted work spanning iterations 0 + 1. Modified files:
- `deploy.sh`, `main.py`
- `config.py`
- `jobs/slack_sync.py`, `jobs/weekly_notify.py`, `jobs/monthly_report.py`
- `services/slack_client.py`, `services/google_slides.py`
- `HANDOFF.md` (this file)

Untracked / new files:
- `services/run_log.py`
- `dashboard/` (entire directory)
- `docs/TROUBLESHOOTING.md`, `docs/SECRETS_ROTATION.md`
- `.context/` (gitignored — qa_backlog, audits, attachments, slides spec)

**Nothing has been committed since `0983327 Add UpdateBot automation bot`.** Recommend splitting into logical commits before pushing:
1. Backend hardening (iteration 0)
2. Dashboard scaffold + deploy.sh wiring (iteration 0)
3. IAP migration (iteration 0)
4. Iteration-1 audit fixes (backend + dashboard + docs)

---

## Deferred items (iteration-2 candidates)

From `.context/qa_backlog.md`:

- `triggered_by` column on RunLog (cron / manual / dry-run) — schema change + dashboard column
- Property failure indicator on dashboard PropertiesTable (read most-recent RunLog row per property)
- `details_json` 50KB Sheets cell size cap with truncation marker (not blocking at 1-property scale yet)
- Slack message ID audit trail (enable "replay this time window")
- Doc idempotency / race-condition handling (substantial)
- Property uniqueness validation (collision on `slack_channel_id` / `live_doc_id`)
- Structured JSON Cloud Logging fields
- Mobile responsiveness audit
- Pagination beyond 25 RunLog rows on dashboard
- IAP membership management documentation (covered partially in TROUBLESHOOTING.md)
- Schema-extension checklist for adding config columns (covered in TROUBLESHOOTING.md)

---

## Notes for the next agent

**Note on `.context/` directory:** Gitignored. Contains working notes (audits, qa_backlog, slides spec, attachments) that are referenced from this handoff and TROUBLESHOOTING.md. If you've cloned the repo fresh, this directory won't exist — ask the user for the contents of `.context/qa_backlog.md` and `.context/slides_template_spec.md` at minimum.

**How the dashboard threads `--dry-run` and other args to the jobs:** `dashboard/app/api/jobs/run/route.ts` calls the Cloud Run Admin API `projects.locations.jobs.run` endpoint with a `RunJobRequest`. For `monthly-report` with `dryRun: true`, it sets `overrides.containerOverrides[0].args = ["monthly-report", "--dry-run"]` to override the default args. This same mechanism is the natural extension point for adding `triggered_by` plumbing later.

**System invariants you must preserve:**
- ADC only — no JSON keys ever (org policy blocks them anyway). Local dev uses `gcloud auth application-default login`. Cloud Run uses attached SA.
- All long-running auth = IAP for the dashboard, `domain:harborcap.com` only. `allUsers` bindings will be silently rejected by org policy.
- `last_sync_timestamp` in config sheet column N is bot-managed. Do not overwrite from agent code.
- RunLog `running` rows MUST be updated in place via `finalize_run(row_key, …)` — do not append a new row at the end. Otherwise crash detection breaks.
- The `monthly-report` job's args are overridden by the dashboard trigger API (`--dry-run`). Default Cloud Run job args = just `["monthly-report"]`.

**Known sharp edges (called out in agent feedback during iteration 1):**
- `_extract_section` in `monthly_report.py` silently defaults missing sections to `"No updates this period."` — deck can ship with that bland string if the live doc has no matching headings. Warning is logged but not surfaced on dashboard.
- `prepend_update` in `google_docs.py` is non-idempotent. Current code path is correct (timestamp written only after prepend succeeds) but a regression in the future would risk lost or duplicate messages.
- `find_unfilled_placeholders` only inspects shape text, not tables or speaker notes or slide masters. Widen if template style evolves.
- `start_run`'s parse of `updatedRange` assumes standard `Tab!A12:H12` shape. A tab rename that introduces brackets would break it.
- Cron + manual triggers can collide if scheduler fires while operator manually clicks the button. Currently no locking; consequence is rare (2 decks created same hour for a property).

**Commands to NEVER run autonomously without confirming with user:**
- Anything that modifies live secrets, IAM, or schedulers (mutating GCP state outside dev)
- `git push --force` to shared branches
- `gcloud projects delete`
- Destructive operations on the config sheet (deletion of properties, schema migrations)

**Helpful starter prompts you might receive:**
- "Continue iteration 2 from the backlog" → start with `triggered_by` and property failure indicator (both have direct UX impact)
- "Add a new property" → see TROUBLESHOOTING.md § 7 (the user does this manually, not you)
- "Debug a failure" → start with TROUBLESHOOTING.md decision tree, then dashboard, then Cloud Logging
- "Add a new placeholder to monthly-report" → modify the slides template (user) + add to `_resolve_replacements` in `monthly_report.py` (you)
- "Onboard a successor" → see iteration-1 onboarding audit in `.context/audit_onboarding.md`

When in doubt, ask the user. Mohith (user) wants concise communication and clear next steps. He's tech-comfortable but not a developer; default to plain-language summaries with code blocks for exact commands.
