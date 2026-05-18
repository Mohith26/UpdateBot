# UpdateBot — Secrets Rotation

Procedures for rotating each secret used by UpdateBot. All secrets live in **Google Secret Manager** in project `harbor-updatebot`. Cloud Run jobs read them via `--set-secrets=…:latest`, so adding a new secret version is picked up automatically on the next job execution — **no redeploy needed**.

For broader debugging see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## `slack-bot-token`

**What it is:** The Slack Bot User OAuth token (`xoxb-…`) for the `UpdateBot` Slack app. Used by `slack-sync` (reads property channel history) and `weekly-notify` / `monthly-report` (posts to the review channel).

**Rotate when:** the bot is reinstalled into the workspace, scopes are changed, you suspect compromise, or for annual hygiene.

**Get a new value:**
1. Go to https://api.slack.com/apps → `UpdateBot`.
2. Left sidebar → **OAuth & Permissions**.
3. Click **Rotate** (or **Reinstall to Workspace** if you changed scopes) → copy the new `xoxb-…` token.

**Update Secret Manager:**
```bash
PATH="/opt/homebrew/bin:$PATH" printf "xoxb-NEW-TOKEN-HERE" | \
  gcloud secrets versions add slack-bot-token --data-file=- --project=harbor-updatebot
```

**Verify:** trigger `slack-sync` and watch logs for successful channel reads.
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud run jobs execute slack-sync \
  --region=us-central1 --project=harbor-updatebot
```
A working token shows `Found N new messages` per property in logs. A bad token surfaces as `Slack API error … invalid_auth` (see [TROUBLESHOOTING.md § 3](TROUBLESHOOTING.md#3-common-errors--what-they-mean-what-to-do)).

**Rollback** (if the new token is bad — find the previous version ID via `gcloud secrets versions list slack-bot-token --project=harbor-updatebot`):
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud secrets versions disable <NEW_VERSION_ID> \
  --secret=slack-bot-token --project=harbor-updatebot
```

---

## `anthropic-api-key`

**What it is:** API key for the Anthropic API. Used by `slack-sync` to extract structured updates from raw Slack messages via Claude.

**Rotate when:** annually, on suspected compromise, or when the key is shown as expired in the Anthropic console.

**Get a new value:**
1. Go to https://console.anthropic.com → **API Keys**.
2. **Create Key** → name it `updatebot-prod-YYYY-MM` → copy the key (shown only once).
3. (Optional) once the new key is verified working, delete the old key in the Anthropic console.

**Update Secret Manager:**
```bash
PATH="/opt/homebrew/bin:$PATH" printf "sk-ant-NEW-KEY-HERE" | \
  gcloud secrets versions add anthropic-api-key --data-file=- --project=harbor-updatebot
```

**Verify:** trigger `slack-sync` against a channel that has new messages; success logs show `Summarizing with Claude...` followed by `Appended update to doc.`. A bad key surfaces as `anthropic.AuthenticationError` / HTTP 401 in Cloud Logging.

**Rollback:**
```bash
PATH="/opt/homebrew/bin:$PATH" gcloud secrets versions disable <NEW_VERSION_ID> \
  --secret=anthropic-api-key --project=harbor-updatebot
```

---

## `dashboard-password` (deprecated — delete if present)

The dashboard previously used HTTP Basic Auth. After migrating to Google IAP (see [dashboard/README.md](../dashboard/README.md)), this secret is orphaned. Delete it:

```bash
PATH="/opt/homebrew/bin:$PATH" gcloud secrets delete dashboard-password \
  --project=harbor-updatebot
```

If the command returns `NOT_FOUND`, the cleanup has already been done — nothing further to do.

---

## General notes

- Cloud Run jobs are configured with `--set-secrets=…:latest`. The next job execution after `versions add` reads the new value automatically. **No redeploy required.**
- To list all secret versions for a given secret:
  ```bash
  PATH="/opt/homebrew/bin:$PATH" gcloud secrets versions list <SECRET_NAME> \
    --project=harbor-updatebot
  ```
- Keep at least one previous version `ENABLED` for a few days post-rotation so rollback is a one-liner.
