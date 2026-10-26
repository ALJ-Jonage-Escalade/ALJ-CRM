#!/bin/bash
# ==============================================================================
# ALJ ESCALADE — Firestore backups (0 € / month at the club's data size)
# Checks, and on request creates, every backup layer of the (default) database.
#
# Usage (from code_source/):
#   ./scripts/setup_firestore_backups.sh              Read-only report (same as --check)
#   ./scripts/setup_firestore_backups.sh --check      Read-only report, exit code 1 if a layer is missing
#   ./scripts/setup_firestore_backups.sh --apply      Create what is missing (asks first, never edits or deletes)
# ==============================================================================
#
# Layers:
#   1. Point-in-time recovery (7 days) and delete protection on the database
#   2. Managed backups: daily (kept 14 days) and weekly (kept 14 weeks)
# Restore procedures: documentations/base_firestore.md, section "Sauvegardes".

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

DATABASE="(default)"
DAILY_RETENTION="14d"
WEEKLY_RETENTION="14w"
WEEKLY_DAY="SUN"
MAX_BACKUP_AGE_HOURS=36

usage() {
    sed -n '6,9p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
}

MODE="check"
while [ $# -gt 0 ]; do
    case "$1" in
        --check) MODE="check" ;;
        --apply) MODE="apply" ;;
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
    echo "On your PC, install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    echo "Or run this script from Google Cloud Shell (gcloud is pre-installed)."
    exit 1
fi

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$CURRENT_PROJECT" ] || [ "$CURRENT_PROJECT" = "(unset)" ]; then
    CURRENT_PROJECT="smart-amplifier-510811-n6"
fi

confirm() {
    read -r -p "$1 (y/N): " answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || { echo "Cancelled."; exit 0; }
}

MISSING_LAYERS=()
WARNINGS=0

ok()      { echo "  ✅ $1"; }
missing() { echo "  ❌ $1"; MISSING_LAYERS+=("$2"); }
warn()    { echo "  ⚠️  $1"; WARNINGS=$((WARNINGS + 1)); }

hours_since() {
    echo $(( ($(date +%s) - $(date -d "$1" +%s)) / 3600 ))
}

# gcloud prints durations in seconds ("1209600s"); the flags take "14d" / "14w"
retention_seconds() {
    case "$1" in
        *d) echo $(( ${1%d} * 86400 )) ;;
        *w) echo $(( ${1%w} * 604800 )) ;;
    esac
}

echo "=============================================================================="
echo "💾 ALJ ESCALADE — Firestore backups ($MODE)"
echo "=============================================================================="
echo "  - Google Cloud project : $CURRENT_PROJECT"
echo "  - Database             : $DATABASE"
echo ""

# ------------------------------------------------------------------------------
# 1. Database settings
# ------------------------------------------------------------------------------
echo "1. Database"
DB_SETTINGS=$(gcloud firestore databases describe --database="$DATABASE" "${PROJECT_FLAG[@]}" \
    --format='csv[no-heading](pointInTimeRecoveryEnablement,deleteProtectionState)')
IFS=, read -r PITR_STATE DELETE_PROTECTION <<< "$DB_SETTINGS"

if [ "$PITR_STATE" = "POINT_IN_TIME_RECOVERY_ENABLED" ]; then
    ok "Point-in-time recovery enabled (7 days)"
else
    missing "Point-in-time recovery disabled" "pitr"
fi
if [ "$DELETE_PROTECTION" = "DELETE_PROTECTION_ENABLED" ]; then
    ok "Delete protection enabled"
else
    missing "Delete protection disabled" "delete-protection"
fi
# ------------------------------------------------------------------------------
# 2. Managed backups
# ------------------------------------------------------------------------------
echo ""
echo "2. Managed backups"
# One line per schedule: retention, weekday (empty for a daily schedule)
SCHEDULES=$(gcloud firestore backups schedules list --database="$DATABASE" "${PROJECT_FLAG[@]}" \
    --format='csv[no-heading](retention,weeklyRecurrence.day)')

DAILY_SCHEDULE=$(echo "$SCHEDULES" | awk -F, '$1 != "" && $2 == "" { print $1; exit }')
WEEKLY_SCHEDULE=$(echo "$SCHEDULES" | awk -F, '$2 != "" { print $1 " " $2; exit }')

if [ -z "$DAILY_SCHEDULE" ]; then
    missing "No daily backup schedule" "daily-schedule"
elif [ "${DAILY_SCHEDULE%s}" -lt "$(retention_seconds "$DAILY_RETENTION")" ]; then
    warn "Daily backups kept only ${DAILY_SCHEDULE} (expected $DAILY_RETENTION)"
else
    ok "Daily backups, kept $DAILY_RETENTION"
fi
if [ -z "$WEEKLY_SCHEDULE" ]; then
    missing "No weekly backup schedule" "weekly-schedule"
elif [ "$(echo "$WEEKLY_SCHEDULE" | awk '{ print $1 }' | tr -d s)" -lt "$(retention_seconds "$WEEKLY_RETENTION")" ]; then
    warn "Weekly backups kept only $(echo "$WEEKLY_SCHEDULE" | awk '{ print $1 }') (expected $WEEKLY_RETENTION)"
else
    ok "Weekly backups ($(echo "$WEEKLY_SCHEDULE" | awk '{ print $2 }')), kept $WEEKLY_RETENTION"
fi

LATEST_BACKUP=$(gcloud firestore backups list "${PROJECT_FLAG[@]}" \
    --format='value(snapshotTime,state)' | sort -r | head -n 1)
if [ -z "$LATEST_BACKUP" ]; then
    warn "No backup yet"
else
    read -r BACKUP_TIME BACKUP_STATE <<< "$LATEST_BACKUP"
    BACKUP_AGE=$(hours_since "$BACKUP_TIME")
    BACKUP_COUNT=$(gcloud firestore backups list "${PROJECT_FLAG[@]}" --format='value(name)' | wc -l)
    if [ "$BACKUP_STATE" != "READY" ] || [ "$BACKUP_AGE" -gt "$MAX_BACKUP_AGE_HOURS" ]; then
        warn "Latest backup: $BACKUP_TIME, $BACKUP_STATE, ${BACKUP_AGE} h old ($BACKUP_COUNT kept)"
    else
        ok "Latest backup: $BACKUP_TIME, ${BACKUP_AGE} h old ($BACKUP_COUNT kept)"
    fi
fi

echo ""
if [ ${#MISSING_LAYERS[@]} -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo "✅ All backup layers are in place."
    exit 0
fi
echo "Missing: ${#MISSING_LAYERS[@]} · Warnings: $WARNINGS"

if [ "$MODE" = "check" ]; then
    [ ${#MISSING_LAYERS[@]} -eq 0 ] || echo "Run with --apply to create what is missing."
    exit 1
fi

if [ ${#MISSING_LAYERS[@]} -eq 0 ]; then
    echo "Nothing to create; the warnings above need a manual look."
    exit 1
fi

# ------------------------------------------------------------------------------
# Apply: create only what is missing, never edit or delete an existing resource
# ------------------------------------------------------------------------------
echo ""
echo "To create in $CURRENT_PROJECT (production):"
printf '  - %s\n' "${MISSING_LAYERS[@]}"
confirm "Create these resources?"

needs() {
    printf '%s\n' "${MISSING_LAYERS[@]}" | grep -qx "$1"
}

if needs "pitr" || needs "delete-protection"; then
    DB_FLAGS=()
    needs "pitr" && DB_FLAGS+=(--enable-pitr)
    needs "delete-protection" && DB_FLAGS+=(--delete-protection)
    echo "🔧 Database: ${DB_FLAGS[*]}"
    gcloud firestore databases update --database="$DATABASE" "${PROJECT_FLAG[@]}" "${DB_FLAGS[@]}" > /dev/null
fi

if needs "daily-schedule"; then
    echo "🔧 Daily backup schedule, kept $DAILY_RETENTION"
    gcloud firestore backups schedules create --database="$DATABASE" "${PROJECT_FLAG[@]}" \
        --recurrence=daily --retention="$DAILY_RETENTION" > /dev/null
fi

if needs "weekly-schedule"; then
    echo "🔧 Weekly backup schedule ($WEEKLY_DAY), kept $WEEKLY_RETENTION"
    gcloud firestore backups schedules create --database="$DATABASE" "${PROJECT_FLAG[@]}" \
        --recurrence=weekly --day-of-week="$WEEKLY_DAY" --retention="$WEEKLY_RETENTION" > /dev/null
fi

echo ""
echo "✅ Done. Run --check to confirm."
