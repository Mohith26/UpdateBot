#!/bin/bash
set -e

PROJECT_ID="harbor-updatebot"
REGION="us-central1"
SERVICE_ACCOUNT="updatebot-sa@harbor-updatebot.iam.gserviceaccount.com"
CONFIG_SHEET_ID="1rzWizfU17kk-Ytk1nu1rfOBSuLI7JKlryYUAj8wU49A"
REVIEW_CHANNEL_ID="C0B3FEUCDEY"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/updatebot/updatebot:latest"

echo "==> Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "==> Enabling required APIs (this takes ~1 min)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
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
