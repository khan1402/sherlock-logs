#!/usr/bin/env bash
# notify.sh - post a pipeline result to Slack (#deployments).
#
#   NOTIFY_STATUS=SUCCESS NOTIFY_TEXT="Version abc1234 is live" bash ci/notify.sh
#
# NOTIFY_STATUS: SUCCESS | BLOCKED | ROLLED_BACK | MANUAL_ROLLBACK | ROLLBACK_FAILED
# Needs SLACK_WEBHOOK_URL - Jenkins provides it from the 'slack-webhook' credential.
# Optional NOTIFY_COMMIT_LABEL renames the "Commit" field (the rollback job uses it).
#
# Never fails the build: a Slack outage must not break a deployment.
set -uo pipefail

: "${SLACK_WEBHOOK_URL:?SLACK_WEBHOOK_URL is not set}"

case "${NOTIFY_STATUS:-}" in
  SUCCESS)         color="#2eb886"; title=":white_check_mark: Deployed" ;;
  BLOCKED)         color="#d00000"; title=":no_entry: Blocked - nothing was deployed" ;;
  ROLLED_BACK)     color="#f2a900"; title=":warning: Deploy failed - automatically rolled back" ;;
  MANUAL_ROLLBACK) color="#439fe0"; title=":leftwards_arrow_with_hook: Manual rollback done" ;;
  ROLLBACK_FAILED) color="#d00000"; title=":rotating_light: Deploy AND rollback failed - manual action needed" ;;
  *)               color="#808080"; title="${NOTIFY_STATUS:-Pipeline result}" ;;
esac

export NOTIFY_COLOR="$color" NOTIFY_TITLE="$title"
NOTIFY_COMMIT="$(git log -1 --format='%h %s (%an)' 2>/dev/null || echo unknown)"
export NOTIFY_COMMIT

# Build the JSON with Python, so quotes or special characters in commit
# messages can never break the message.
payload="$(python3 - <<'PY'
import json, os

def esc(text):
    # Slack treats & < > as control characters.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

env = os.environ.get
build = f"<{env('BUILD_URL', '')}|{env('JOB_NAME', 'job')} #{env('BUILD_NUMBER', '?')}>"
print(json.dumps({
    "text": env("NOTIFY_TITLE"),
    "attachments": [{
        "color": env("NOTIFY_COLOR"),
        "title": env("NOTIFY_TITLE"),
        "text": esc(env("NOTIFY_TEXT", "")),
        "fields": [
            {"title": "Build", "value": build, "short": True},
            {"title": "Version", "value": env("IMAGE_TAG", "-") or "-", "short": True},
            {"title": env("NOTIFY_COMMIT_LABEL", "Commit"), "value": esc(env("NOTIFY_COMMIT", "")), "short": False},
        ],
        "footer": "Jenkins - Automation Alchemy",
    }],
}))
PY
)"

# --retry: a short network or DNS hiccup gets 3 more tries, 5 s apart.
if curl -sS -m 10 --retry 3 --retry-delay 5 --retry-all-errors -o /dev/null -w '%{http_code}' -X POST \
     -H 'Content-Type: application/json' --data "$payload" "$SLACK_WEBHOOK_URL" | grep -q '^200$'; then
  echo "Slack notification sent: ${NOTIFY_STATUS:-}"
else
  echo "Slack notification FAILED (ignored - the build result is not affected)"
fi
exit 0
