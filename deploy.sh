#!/bin/bash
set -e

PROJECT_ID="harbor-updatebot"
REGION="us-central1"
SERVICE_ACCOUNT="updatebot-sa@harbor-updatebot.iam.gserviceaccount.com"
CONFIG_SHEET_ID="1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A"
REVIEW_CHANNEL_ID="C0B3FEUCDEY"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/updatebot/updatebot:latest"
DASHBOARD_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/updatebot/dashboard:latest"
DASHBOARD_SERVICE="updatebot-dashboard"

echo "==> Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "==> Enabling required APIs (this takes ~1 min)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  iap.googleapis.com \
  --quiet

echo "==> Creating Artifact Registry repository..."
gcloud artifacts repositories create updatebot \
  --repository-format=docker \
  --location=$REGION \
  --quiet 2>/dev/null || echo "  Repository already exists, skipping."

echo "==> Granting service account access to Secret Manager..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet

echo "==> Granting service account permission to execute Cloud Run jobs..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" \
  --quiet

echo "==> Building image with Cloud Build (uploads code to Google, builds remotely)..."
gcloud builds submit \
  --tag=$IMAGE \
  --project=$PROJECT_ID \
  .

echo "==> Deploying Cloud Run jobs..."
for JOB in slack-sync weekly-notify monthly-report; do
  echo "  Deploying $JOB..."
  gcloud run jobs create $JOB \
    --image=$IMAGE \
    --region=$REGION \
    --service-account=$SERVICE_ACCOUNT \
    --args=$JOB \
    --set-secrets=SLACK_BOT_TOKEN=slack-bot-token:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest \
    --set-env-vars=CONFIG_SHEET_ID=$CONFIG_SHEET_ID,REVIEW_CHANNEL_ID=$REVIEW_CHANNEL_ID \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null || \
  gcloud run jobs update $JOB \
    --image=$IMAGE \
    --region=$REGION \
    --service-account=$SERVICE_ACCOUNT \
    --set-secrets=SLACK_BOT_TOKEN=slack-bot-token:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest \
    --set-env-vars=CONFIG_SHEET_ID=$CONFIG_SHEET_ID,REVIEW_CHANNEL_ID=$REVIEW_CHANNEL_ID \
    --project=$PROJECT_ID \
    --quiet
  echo "  $JOB deployed."
done

echo "==> Creating Cloud Scheduler triggers..."

# slack-sync: every 4 hours
gcloud scheduler jobs create http slack-sync-trigger \
  --location=$REGION \
  --schedule="0 */4 * * *" \
  --uri="https://$REGION-run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/slack-sync:run" \
  --message-body='{}' \
  --oauth-service-account-email=$SERVICE_ACCOUNT \
  --quiet 2>/dev/null || echo "  slack-sync-trigger already exists, skipping."

# weekly-notify: Mondays 8am CT (13:00 UTC)
gcloud scheduler jobs create http weekly-notify-trigger \
  --location=$REGION \
  --schedule="0 13 * * 1" \
  --uri="https://$REGION-run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/weekly-notify:run" \
  --message-body='{}' \
  --oauth-service-account-email=$SERVICE_ACCOUNT \
  --quiet 2>/dev/null || echo "  weekly-notify-trigger already exists, skipping."

# monthly-report: 1st of month 8am CT (13:00 UTC)
gcloud scheduler jobs create http monthly-report-trigger \
  --location=$REGION \
  --schedule="0 13 1 * *" \
  --uri="https://$REGION-run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/monthly-report:run" \
  --message-body='{}' \
  --oauth-service-account-email=$SERVICE_ACCOUNT \
  --quiet 2>/dev/null || echo "  monthly-report-trigger already exists, skipping."

echo "==> Checking IAP prerequisites..."
if [ -z "$(gcloud services list --enabled --filter=name:iap.googleapis.com --project=$PROJECT_ID --format='value(name)')" ]; then
  echo ""
  echo "ERROR: IAP API (iap.googleapis.com) is not enabled in project $PROJECT_ID."
  echo "It should have been enabled earlier in this script — try re-running deploy.sh."
  echo ""
  exit 1
fi

if [ -z "$(gcloud iap oauth-brands list --project=$PROJECT_ID --format='value(name)' 2>/dev/null)" ]; then
  echo ""
  echo "ERROR: No OAuth brand exists in project $PROJECT_ID — IAP cannot be enabled."
  echo ""
  echo "Configure the OAuth consent screen first:"
  echo "  1. Open https://console.cloud.google.com/apis/credentials/consent?project=$PROJECT_ID"
  echo "  2. User Type: Internal"
  echo "  3. App name: UpdateBot Admin"
  echo "  4. User support email: your @harborcap.com address"
  echo "  5. Developer contact email: your @harborcap.com address"
  echo "  6. Save, then re-run deploy.sh."
  echo ""
  exit 1
fi

echo "==> Building dashboard image with Cloud Build..."
gcloud builds submit dashboard/ \
  --tag=$DASHBOARD_IMAGE \
  --project=$PROJECT_ID

echo "==> Deploying Cloud Run service '$DASHBOARD_SERVICE'..."
gcloud run deploy $DASHBOARD_SERVICE \
  --image=$DASHBOARD_IMAGE \
  --region=$REGION \
  --service-account=$SERVICE_ACCOUNT \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --min-instances=0 \
  --max-instances=2 \
  --set-env-vars=CONFIG_SHEET_ID=$CONFIG_SHEET_ID \
  --project=$PROJECT_ID \
  --quiet

echo "==> Enabling IAP on '$DASHBOARD_SERVICE'..."
gcloud run services update $DASHBOARD_SERVICE \
  --iap \
  --region=$REGION \
  --project=$PROJECT_ID \
  --quiet

echo "==> Granting IAP service agent permission to invoke '$DASHBOARD_SERVICE'..."
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud run services add-iam-policy-binding $DASHBOARD_SERVICE \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --project=$PROJECT_ID \
  --quiet

echo "==> Granting harborcap.com domain access to IAP-protected '$DASHBOARD_SERVICE'..."
gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service=$DASHBOARD_SERVICE \
  --region=$REGION \
  --member="domain:harborcap.com" \
  --role="roles/iap.httpsResourceAccessor" \
  --project=$PROJECT_ID

DASHBOARD_URL=$(gcloud run services describe $DASHBOARD_SERVICE \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="value(status.url)")

echo ""
echo "========================================="
echo "Deployment complete!"
echo "========================================="
echo ""
echo "Cloud Run Jobs:"
gcloud run jobs list --region=$REGION --project=$PROJECT_ID
echo ""
echo "Cloud Scheduler Triggers:"
gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID
echo ""
echo "Dashboard URL: $DASHBOARD_URL"
