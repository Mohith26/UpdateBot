# UpdateBot Dashboard

Read-only Next.js admin UI for UpdateBot. Renders the latest `RunLog` rows and per-property sync status from the same Google Sheet the bot uses. Runs as a Cloud Run service authed via Application Default Credentials (ADC) — no JSON keys. Access is gated by Google IAP, restricted to `@harborcap.com` Workspace users.

## Env vars

| Name | Description |
|---|---|
| `CONFIG_SHEET_ID` | Spreadsheet ID. Defaults to the production sheet. |

Auth uses ADC: on Cloud Run the attached service account (`updatebot-sa@harbor-updatebot.iam.gserviceaccount.com`) is picked up automatically. The service account must have read access to the spreadsheet.

## One-time setup (before the first deploy)

Configure the OAuth consent screen for IAP. In the GCP console:

1. Open https://console.cloud.google.com/apis/credentials/consent?project=harbor-updatebot
2. User Type: **Internal**
3. App name: **UpdateBot Admin**
4. User support email: your `@harborcap.com` address
5. Developer contact: your `@harborcap.com` address
6. Save.

This creates the OAuth brand IAP needs. The deploy script will fail fast with instructions if this step is missing.

## Deploy

From the repo root:

```bash
PATH="/opt/homebrew/bin:$PATH" bash deploy.sh
```

This builds the Python jobs image, builds the dashboard image, deploys the `updatebot-dashboard` Cloud Run service, enables IAP, and grants `harborcap.com` access. The final service URL is printed at the end.

## Access

Visit the printed Dashboard URL — Google sign-in opens. Sign in with your `@harborcap.com` account. Non-`@harborcap.com` accounts get a Google "you don't have access" page. Once signed in, your email appears in the top-right of the page ("Signed in as ...").

## Local dev

```bash
gcloud auth application-default login   # one-time, uses your Google account
cp .env.example .env.local              # optional — defaults are fine
npm install
npm run dev
```

Open http://localhost:3000. No auth gate locally (IAP only runs in front of Cloud Run). The "Signed in as" indicator is blank locally because there's no `X-Goog-Authenticated-User-Email` header — by design.

## Revoking access

- A specific user signs out of their Google account, or you remove them from the `harborcap.com` Workspace.
- To restrict to a narrower allowlist, replace the `domain:harborcap.com` binding in `deploy.sh` with one or more `user:foo@harborcap.com` members.

## Cleanup of the old password secret

The dashboard no longer uses HTTP Basic Auth. If the `dashboard-password` secret from the previous setup still exists, delete it:

```bash
gcloud secrets delete dashboard-password --project=harbor-updatebot
```
