#!/bin/zsh
# Herding Cats - hourly catch-up sweep, scheduled runner.
# Fired by launchd hourly 08:00-18:00 Mon-Fri (see com.canvas.herding-cats-sweep.plist).
#
# Why this exists: cats were arriving in two evening dumps rather than through
# the day. On 2026-09-08 and 09-09 completions landed at six or more separate
# points and the daily count was 37 each. From 09-10 the same amount of work
# produced around 10 a day, because a 14-hour day was being reconstructed from
# memory at 8pm and whatever was not remembered then never got logged.
#
# What it does: POSTs /api/sweep, which runs the narrow half of the
# herding-cats skill through the claude CLI and logs whatever clears the
# strong-evidence bar. The app owns the window, the cooldown and the lock, so
# this script deliberately holds no scheduling logic of its own.
#
# It writes cats into the real herd. There is no dry-run mode here; to test
# against scratch data, run the endpoint by hand with HERD_HOME set and a
# spare port, never 8787.

set -eo pipefail

# Bootstrap Homebrew under launchd (HOMEBREW_PREFIX is only set in interactive
# shells via /etc/zprofile).
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# The sweep shells out to gws, gh, ccvault and sqlite3, and reaches MCP servers
# whose tokens live in the interactive shell env.
if [[ -r "$HOME/.zshrc" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.zshrc" || true
fi

# claude lives in ~/.local/bin, which launchd does not put on PATH.
if [[ -d "$HOME/.local/bin" ]]; then
  export PATH="$HOME/.local/bin:$PATH"
fi

PROJECT_DIR="$HOME/tools-and-projects/rosie/herding-cats-app"
LOGDIR="$HOME/Library/Logs/herding-cats"
LOGFILE="$LOGDIR/sweep-$(date +%Y-%m-%d).log"
PORT=8787
BASE="http://127.0.0.1:${PORT}"

mkdir -p "$LOGDIR"
cd "$PROJECT_DIR"

exec >> "$LOGFILE" 2>&1

echo "==== hourly sweep $(date '+%Y-%m-%d %H:%M:%S') ===="

# Is the dashboard up, and does it want a sweep? One question, one request.
#
# This used to check `lsof -ti:$PORT` first. lsof lives in /usr/sbin, which is
# not on the PATH launchd provides, so the check exited 127 (command not
# found) on every scheduled run and the script read that as "server down" and
# skipped. Ten silent no-ops, an empty log, and `runs = 0` in launchctl.
#
# Asking the server directly avoids the whole class of problem: curl is on the
# base PATH, the script already depends on it, and a reply proves the server
# is up in a way that inspecting the port never did.
#
# A closed window is the normal overnight and weekend state rather than a
# fault, so a failure to connect exits quietly instead of starting a server
# Jess did not open. Nothing is lost by skipping, because the next sweep's
# window reaches back to the last recorded one.
STATUS="$(curl -s -m 10 "${BASE}/api/sweep" 2>/dev/null || true)"
if [[ -z "$STATUS" ]]; then
  echo "dashboard not answering on $PORT - skipping. Next run picks up the gap."
  exit 0
fi

COOLING="$(printf '%s' "$STATUS" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("cooling",0))' 2>/dev/null || echo 0)"
if [[ "$COOLING" != "0" ]]; then
  echo "swept ${COOLING}s ago, still cooling - skipping."
  exit 0
fi

echo "posting /api/sweep ..."

# The endpoint streams server-sent events for the dashboard's progress panel.
# Nothing is watching here, so the body is kept only for the log. --no-buffer
# so a stalled run still writes what it got.
HTTP_CODE="$(curl -s -N --no-buffer -m 900 -o "${LOGFILE}.body" -w '%{http_code}' \
  -X POST "${BASE}/api/sweep?trigger=schedule" || echo 000)"

echo "HTTP ${HTTP_CODE}"

# 409 is another sweep already running, 429 is the cooldown. Both mean the work
# is already covered, so neither is a failure worth alerting on.
case "$HTTP_CODE" in
  200) echo "sweep completed." ;;
  409) echo "a sweep was already running - fine, it covers this window." ;;
  429) echo "cooldown rejected the run - fine, a recent sweep covers this window." ;;
  000) echo "ERROR: no response, the request timed out or the server went away." ;;
  *)   echo "ERROR: unexpected status ${HTTP_CODE}." ;;
esac

# The reply is the agent's narration, not the record. Cats logged are counted
# from the herd by the endpoint itself, so read /api/sweep for the real result.
if [[ -s "${LOGFILE}.body" ]]; then
  echo "--- response tail ---"
  tail -c 2000 "${LOGFILE}.body"
  echo
  rm -f "${LOGFILE}.body"
fi

AFTER="$(curl -s -m 10 "${BASE}/api/sweep" || true)"
if [[ -n "$AFTER" ]]; then
  printf '%s' "$AFTER" | /usr/bin/python3 -c '
import json, sys
d = json.load(sys.stdin)
print("recorded: day={} clock={} logged={}".format(
    d.get("day"), d.get("clock"), d.get("logged")))
' 2>/dev/null || true
fi

echo "finished $(date '+%H:%M:%S')"
