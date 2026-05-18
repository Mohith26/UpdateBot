# UpdateBot — Troubleshooting Runbook

Practical runbook for diagnosing failed jobs and operating UpdateBot day-to-day. For system overview see [HANDOFF.md](../HANDOFF.md). For secrets rotation see [SECRETS_ROTATION.md](SECRETS_ROTATION.md).

---

## 1. Something failed — start here

1. Open the dashboard: https://updatebot-dashboard-818467834208.us-central1.run.app/
2. Find the failed run in **Recent Runs**.
3. Expand the row → read `details_json` for per-property errors. Each property is tagged `success` / `failed` with the exact error string.
4. Decide which branch to follow:

| Symptom | Go to |
|---|---|
| Specific property has a per-property error string | §3 Common errors |
| RunLog row says `running` and is >1h old | §4 Job crashed mid-run |
| You don't see the run at all (scheduled time has passed) | §5 Job didn't start |
| Dashboard returns "Forbidden" / Google blocks you | §6 Dashboard access |
| Job ran but did the wrong thing (config error) | §7 / §8 Config changes |

If `details_json` is empty/`[]` and `status=failed`, the job died before processing any property — go straight to §2 and read Cloud Logging.

---

## 2. Reading Cloud Logging

The dashboard surfaces RunLog rows, not stack traces. For tracebacks you need Cloud Logging directly. All commands assume macOS with gcloud installed via Homebrew — the `PATH=` prefix avoids "command not found".

**slack-sync** (every 4 hours):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=slack-sync" \
  --limit=50 --format='value(textPayload)' \
  --project=harbor-updatebot --freshness=24h
```

**weekly-notify** (Mondays):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=weekly-notify" \
  --limit=50 --format='value(textPayload)' \
  --project=harbor-updatebot --freshness=7d
```

**monthly-report** (1st of month):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=monthly-report" \
  --limit=100 --format='value(textPayload)' \
  --project=harbor-updatebot --freshness=30d
```

**Dashboard service** (Next.js, IAP-fronted):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=updatebot-dashboard" \
  --limit=50 --format='value(textPayload)' \
  --project=harbor-updatebot --freshness=1d
```

**Filter to a specific execution** (when you've identified a bad run in the GCP console):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=slack-sync AND labels.\"run.googleapis.com/execution_name\"=slack-sync-XXXXX" \
  --limit=200 --format='value(textPayload)' --project=harbor-updatebot
```

**Filter to errors only:**
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=slack-sync AND severity>=ERROR" \
  --limit=20 --format='value(textPayload)' --project=harbor-updatebot --freshness=24h
```

---

## 3. Common errors — what they mean, what to do

### `WARN [property]: last_sync_timestamp is empty/ancient, capping lookback to 30d`
First-run behavior for a newly added property (column N in the config sheet is blank or very old). The bot caps the initial Slack lookback so it doesn't ingest years of history. **Expected. Do nothing.** After the first successful run, column N gets populated and subsequent runs are incremental.

### `ERROR [property]: deck has unfilled placeholders: {…}`
The Slides template contains a `{{TAG}}` that the code doesn't know how to fill. Either:
- The template was edited and a new tag was added that isn't in `_resolve_replacements()` in `jobs/monthly_report.py`.
- A tag is misspelled in the template (e.g. `{{ADRESS}}` instead of `{{ADDRESS}}`).

Fix: open the template → make tags match the table in [HANDOFF.md § Slides Template Placeholders](../HANDOFF.md#slides-template-placeholders). If the new tag is legitimate, add it to `_resolve_replacements()` and `services/google_slides.py:fill_placeholders` flow.

### `FAILED_PRECONDITION: Key creation is not allowed on this service account`
Org policy blocks downloading SA JSON keys. UpdateBot is designed to **not need** a JSON key — Cloud Run authenticates via the attached SA (ADC). If you hit this trying to set up local dev, run `gcloud auth application-default login` with your own Google account instead. See [.context/audit_onboarding.md](../.context/audit_onboarding.md) for background.

### Slack `429` / `ratelimited`
The Slack SDK retries 3x with backoff, then raises. If you see persistent 429s:
- Reduce frequency: bump `slack-sync` cron from `0 */4 * * *` to `0 */6 * * *` in `deploy.sh`.
- Split processing: if one channel has thousands of unread messages, manually backfill `last_sync_timestamp` (column N) to a recent date.

### Anthropic `401` / `403` / `authentication_error`
API key is invalid, revoked, or hit a billing limit. Check the Anthropic console → API Keys. Rotate per [SECRETS_ROTATION.md § anthropic-api-key](SECRETS_ROTATION.md#anthropic-api-key). Jobs pick up the new `:latest` version on next execution — no redeploy.

### `ERROR resolving placeholders for [property]`
Almost always one of:
- **Missing `live_doc_id` (column C).** Add it to the config sheet.
- **Malformed `cell_cash_balance` (column E).** Must be `SHEET_ID:RANGE` e.g. `1QSXur21Kc...:Sheet1!B5`. The colon is required. The job will log `WARNING: cell_cash_balance for '[prop]' is malformed (missing ':' separator)` and substitute `[Data not available]` rather than crash.
- **Doc/sheet not shared with the service account.** Share `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com` as Editor (or Viewer where read-only is enough).

### `RunLog: failed to append run row for [job]: …`
The job finished but couldn't write its result row. Causes:
- Config sheet has no tab literally named `RunLog` (case-sensitive). Add a tab named `RunLog` with header row: `timestamp_utc | job_name | status | properties_processed | properties_failed | duration_seconds | summary | details_json`.
- Service account lost Editor access to the config sheet. Re-share with `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com`.

The job's actual work still succeeded — only the dashboard visibility is broken.

### Dashboard returns "Forbidden" / Google "You don't have access"
IAP doesn't recognize the caller's email. See §6.

### `slack_channel_id is empty for '[property]'`
Column B in the config sheet is blank. Fill it in (channel ID starts with `C`, get it from Slack: right-click channel → View channel details → bottom).

### Google Docs `404 Requested entity was not found`
The doc ID is wrong **or** the SA isn't shared on the doc. Open the doc URL — if the SA isn't in the share list, add it as Editor. If the URL 404s for you, the doc ID is wrong in the config sheet.

---

## 4. Job crashed mid-run

`append_run()` is called at the *end* of a job. If the process dies before that (OOM, deploy timeout, unhandled exception in setup), no RunLog row is written for the run — but if a row was pre-created as `running` elsewhere, it will stay stuck.

Recovery:
1. Open the failed Cloud Run execution: GCP console → Cloud Run → Jobs → [job-name] → Executions tab. Click the failed execution → **Logs** tab. Read stderr.
2. Classify:
   - **Transient** (network blip, Google 5xx, Anthropic 529 overloaded): re-trigger the job:
     ```bash
     PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync --region=us-central1 --project=harbor-updatebot
     ```
     (Substitute `weekly-notify` or `monthly-report`.)
   - **Config issue** (bad doc ID, missing tab, wrong scope): fix the config sheet first, then re-trigger.
   - **Code bug**: fix → `bash deploy.sh` to redeploy → re-trigger.
3. Stale `running` rows in the RunLog tab are cosmetic only. Delete them by hand if they clutter the dashboard.

---

## 5. Job didn't start

Possible causes, in order of likelihood:

**Scheduler trigger disabled / deleted.**
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud scheduler jobs list \
  --location=us-central1 --project=harbor-updatebot
```
Expect three rows: `slack-sync-trigger`, `weekly-notify-trigger`, `monthly-report-trigger`, all `ENABLED`. To re-enable:
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud scheduler jobs resume slack-sync-trigger \
  --location=us-central1 --project=harbor-updatebot
```

**SA lost `roles/run.invoker`** (someone tidied IAM).
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud projects get-iam-policy harbor-updatebot \
  --flatten="bindings[].members" \
  --filter="bindings.members:updatebot-sa@harbor-updatebot.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```
Should include `roles/run.invoker` and `roles/secretmanager.secretAccessor`. If missing, re-run `bash deploy.sh` — it re-applies the bindings idempotently.

**Job not deployed in current revision** (e.g. someone deleted the job manually):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs list --region=us-central1 --project=harbor-updatebot
```
If a job is missing, re-run `bash deploy.sh`.

---

## 6. Dashboard access

The dashboard is fronted by Google IAP. Membership is managed at the IAP layer, not in the app.

Current binding: `domain:harborcap.com` is granted `roles/iap.httpsResourceAccessor`. Every active `@harborcap.com` Workspace user can sign in automatically.

**Grant a specific external email** (e.g. an external auditor or investor admin):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run --service=updatebot-dashboard --region=us-central1 \
  --member="user:foo@bar.com" \
  --role="roles/iap.httpsResourceAccessor" \
  --project=harbor-updatebot
```

**Revoke**:
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud iap web remove-iam-policy-binding \
  --resource-type=cloud-run --service=updatebot-dashboard --region=us-central1 \
  --member="user:foo@bar.com" \
  --role="roles/iap.httpsResourceAccessor" \
  --project=harbor-updatebot
```

**List current members**:
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud iap web get-iam-policy \
  --resource-type=cloud-run --service=updatebot-dashboard --region=us-central1 \
  --project=harbor-updatebot
```

Notes:
- IAM changes take **30–60 seconds** to propagate. Hard-refresh the browser (or use an incognito window) before troubleshooting further.
- Removing a user from the `harborcap.com` Workspace also removes their dashboard access — no IAP change needed.
- To lock the dashboard down to a narrower allowlist, remove the `domain:harborcap.com` binding and add `user:` bindings explicitly.

---

## 7. Adding a new property

Concrete checklist. Do steps in this order — later steps depend on earlier ones.

1. **Add a row to the config sheet** (Google Sheet ID `1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A`). Fill columns A–M per the table in [HANDOFF.md § Config Sheet Structure](../HANDOFF.md#config-sheet-structure). Leave column **N (`last_sync_timestamp`) blank**.
2. **Invite the bot to the property's Slack channel.** In the channel: `/invite @UpdateBot`. Without this, `slack-sync` will fail with `not_in_channel`.
3. **Share the property's live Google Doc** (column C) with `updatebot-sa@harbor-updatebot.iam.gserviceaccount.com` as **Editor**.
4. **Share the Slides template** (column D) with the same SA as **Viewer** (the job copies the file via Drive API — Viewer is sufficient because copying writes to a new file).
5. **Share the "What We're Reading" doc** (column F) and the financials sheet referenced in column E with the SA as Viewer.
6. **Manually trigger `slack-sync`** to confirm the property processes cleanly:
   ```bash
   PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync \
     --region=us-central1 --project=harbor-updatebot
   ```
7. **Watch the dashboard** Recent Runs. The new property should appear in `details_json` with `status: success`. Column N in the config sheet will be auto-populated with the latest Slack message timestamp.

If step 7 shows `failed` for the new property, the error string in `details_json` will point straight at §3 above (most often: not invited to channel, or doc not shared).

---

## 8. Adding a new config column

Required if you want a new field to flow into Slides decks or job logic. Three code changes plus docs.

1. **`config.py`**:
   - Bump `_NUM_COLS` (currently `14`).
   - Add the new field to the `_COL` dict (next zero-indexed column).
   - Add the field to the `Property` dataclass.
   - Add the field to the `Property(...)` constructor call inside `load_properties()`.
   - Update the `read_range(CONFIG_SHEET_ID, "A1:N200")` range to extend through the new column (e.g. `A1:O200`).
2. **Update the job(s) that need the new field.** For example, if it's a Slides placeholder, add it to `_resolve_replacements()` in `jobs/monthly_report.py` *and* add the corresponding `{{TAG}}` to every property's Slides template.
3. **Update [HANDOFF.md](../HANDOFF.md)** — the *Config Sheet Structure* table.
4. **Sanity-check locally** (requires `gcloud auth application-default login` first):
   ```bash
   CONFIG_SHEET_ID=1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A \
   REVIEW_CHANNEL_ID=C0B3FEUCDEY \
   SLACK_BOT_TOKEN=dummy ANTHROPIC_API_KEY=dummy \
   python -c "import config; props = config.load_properties(); print(len(props), 'properties'); print(props[0])"
   ```
5. **Redeploy**: `PATH="/opt/homebrew/bin:$PATH" bash deploy.sh`.

The `last_sync_timestamp` column **must remain the last column** — `update_last_sync()` computes the column letter from `_COL["last_sync_timestamp"]`. If you insert a new column to the right of N, update the existing config-sheet column N values to slide right as well.
