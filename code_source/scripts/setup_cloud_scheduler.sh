#!/bin/bash
# ==============================================================================
# ALJ ESCALADE — Cloud Scheduler job of the daily MyCompet results batch
# Creates or updates the job and its service account, with the settings below. Run again at any time:
# it only brings the job back to these settings. Not part of deploy_cloud_run.sh (one-time setup).
#
# Usage (from code_source/, or in Google Cloud Shell):
#   ./scripts/setup_cloud_scheduler.sh              Create or update the service account and the job
#   ./scripts/setup_cloud_scheduler.sh --dry-run    Show the current job and the commands, change nothing
#   ./scripts/setup_cloud_scheduler.sh --status     Last run of the job and batch logs of the last day (read-only)
#
# The app accepts the job's OIDC token only from SERVICE_ACCOUNT_EMAIL with the audience AUDIENCE: keep them
# equal to DEFAULT_SCHEDULER_SERVICE_ACCOUNT / DEFAULT_SCHEDULER_AUDIENCE in src/infrastructure/security/api_auth.py
# (tests/test_setup_cloud_scheduler.py checks it). On the first setup, run this script BEFORE deploying the app
# version that requires the token: the job then already sends it, and the next 07:00 run does not get 401.
# ==============================================================================

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

EXPECTED_PROJECT="smart-amplifier-510811-n6"
REGION="europe-west1"
SERVICE_NAME="alj-escalade-api"
JOB_NAME="batch-resultats-competitions"
SCHEDULE="0 7 * * *"
TIME_ZONE="Europe/Paris"
AUDIENCE="https://alj-escalade-api-bdxfydatoa-ew.a.run.app"
ROUTE="/api/competitions/cron/fetch-results"
# Above the batch's time budget (150 s, DEFAULT_TIME_BUDGET_SECONDS): it stops cleanly before this deadline
ATTEMPT_DEADLINE="180s"
MAX_RETRY_ATTEMPTS="0"
SERVICE_ACCOUNT_NAME="alj-results-scheduler"

usage() {
    sed -n '7,10p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
}

MODE="apply"
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run|--status)
            [ "$MODE" = "apply" ] || { echo "❌ --dry-run and --status cannot be combined."; exit 1; }
            MODE="${1#--}"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

if ! command -v gcloud &> /dev/null; then
    echo "❌ ERROR: the 'gcloud' command was not found."
    echo "Install the Google Cloud SDK (https://cloud.google.com/sdk/docs/install) or use Google Cloud Shell."
    exit 1
fi

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
    PROJECT="$EXPECTED_PROJECT"
fi
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT.iam.gserviceaccount.com"
TARGET_URI="$AUDIENCE$ROUTE"

confirm() {
    read -r -p "$1 (y/N): " answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || { echo "Cancelled."; exit 0; }
}

# Prints the command; runs it unless --dry-run
run() {
    printf '   $'
    printf ' %q' "$@"
    printf '\n'
    if [ "$MODE" != "dry-run" ]; then
        "$@"
    fi
}

describe_job() {
    gcloud scheduler jobs describe "$JOB_NAME" --project "$PROJECT" --location "$REGION" \
        --format='yaml(schedule,timeZone,state,attemptDeadline,retryConfig,httpTarget.uri,httpTarget.httpMethod,httpTarget.oidcToken,lastAttemptTime,status)'
}

echo "=============================================================================="
echo "⏰ ALJ ESCALADE — Cloud Scheduler ($MODE)"
echo "=============================================================================="
echo "  - Google Cloud project : $PROJECT"
echo "  - Job                  : $JOB_NAME ($REGION)"
echo "  - Schedule             : $SCHEDULE ($TIME_ZONE)"
echo "  - Target               : POST $TARGET_URI"
echo "  - Deadline / retries   : $ATTEMPT_DEADLINE / $MAX_RETRY_ATTEMPTS"
echo "  - OIDC token           : $SERVICE_ACCOUNT_EMAIL (audience $AUDIENCE)"
echo ""

if [ "$PROJECT" != "$EXPECTED_PROJECT" ]; then
    echo "⚠️  The app expects the account and audience of project $EXPECTED_PROJECT (api_auth.py): on another"
    echo "   project, set ALJ_SCHEDULER_SERVICE_ACCOUNT / ALJ_SCHEDULER_AUDIENCES on the Cloud Run service."
    echo ""
fi

# ------------------------------------------------------------------------------
# Status (read-only)
# ------------------------------------------------------------------------------
if [ "$MODE" = "status" ]; then
    echo "📋 Job (status empty or code 0 = last run succeeded):"
    describe_job
    echo ""
    echo "📜 Batch logs of the last day:"
    gcloud logging read \
        "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND textPayload:\"BATCH_RESULTATS\"" \
        --project "$PROJECT" --freshness=1d --limit 50 --format='value(timestamp,textPayload)'
    exit 0
fi

# ------------------------------------------------------------------------------
# Create or update (--dry-run: show only)
# ------------------------------------------------------------------------------
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT" --region "$REGION" \
    --format='value(status.url)' 2>/dev/null || true)
if [ -z "$SERVICE_URL" ]; then
    echo "❌ Cloud Run service $SERVICE_NAME not found in $PROJECT ($REGION): deploy it first."
    exit 1
fi
if [ "$SERVICE_URL" != "$AUDIENCE" ]; then
    echo "⚠️  The service URL is $SERVICE_URL, not $AUDIENCE: the job would call another address than the app's,"
    echo "   and the app would refuse the token's audience. Update AUDIENCE here and in api_auth.py first."
    exit 1
fi

if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project "$PROJECT" > /dev/null 2>&1; then
    SA_EXISTS=true
else
    SA_EXISTS=false
fi
if CURRENT_JOB=$(describe_job 2>/dev/null); then
    JOB_EXISTS=true
    echo "📋 Current job:"
    echo "$CURRENT_JOB" | sed 's/^/   /'
else
    JOB_EXISTS=false
    echo "📋 The job does not exist yet."
fi
echo ""

if [ "$MODE" = "dry-run" ]; then
    echo "🔎 Dry run: commands that would run (nothing is changed)"
else
    echo "ℹ️  The job runs on production data: a run sends a real e-mail and writes the results."
    confirm "Create or update the service account and the job?"
fi
echo ""

if [ "$SA_EXISTS" = true ]; then
    echo "✅ Service account $SERVICE_ACCOUNT_EMAIL already exists."
else
    echo "👤 Service account (no role: the app checks the token itself, the service stays --allow-unauthenticated):"
    run gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" --project "$PROJECT" \
        --display-name "Cloud Scheduler - batch des résultats MyCompet"
fi
echo ""

JOB_SETTINGS=(
    --project "$PROJECT"
    --location "$REGION"
    --schedule "$SCHEDULE"
    --time-zone "$TIME_ZONE"
    --uri "$TARGET_URI"
    --http-method POST
    --attempt-deadline "$ATTEMPT_DEADLINE"
    --max-retry-attempts "$MAX_RETRY_ATTEMPTS"
    --oidc-service-account-email "$SERVICE_ACCOUNT_EMAIL"
    --oidc-token-audience "$AUDIENCE"
)
if [ "$JOB_EXISTS" = true ]; then
    echo "🔁 Job update:"
    run gcloud scheduler jobs update http "$JOB_NAME" "${JOB_SETTINGS[@]}"
else
    echo "🆕 Job creation:"
    run gcloud scheduler jobs create http "$JOB_NAME" "${JOB_SETTINGS[@]}"
fi

if [ "$MODE" = "dry-run" ]; then
    exit 0
fi

echo ""
echo "=============================================================================="
echo "✅ JOB READY"
echo "=============================================================================="
describe_job | sed 's/^/   /'
echo ""
echo "If a run fails with a token error, Cloud Scheduler may not be allowed to create tokens for the account:"
echo "   gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL --project $PROJECT \\"
echo "       --member serviceAccount:service-<project number>@gcp-sa-cloudscheduler.iam.gserviceaccount.com \\"
echo "       --role roles/iam.serviceAccountTokenCreator"
echo ""
echo "▶️  Checks (read-only):"
echo "   $0 --status                                   # after the next 07:00 run"
echo "   curl -i -X POST $TARGET_URI    # 401 once the app requiring the token is deployed"
echo "   A manual run (gcloud scheduler jobs run $JOB_NAME --location $REGION) sends a real e-mail: only with the team's OK."
