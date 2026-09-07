#!/usr/bin/env bash
#
# Keep the Wine Voyage API running on a Mac that stays on, so the site works
# from your phone without you starting anything first.
#
#   ./scripts/install_launchd.sh --print     # render the plist, install nothing
#   ./scripts/install_launchd.sh             # install and start it
#   ./scripts/install_launchd.sh --uninstall # stop it and remove it
#
# This installs a LaunchAgent, which starts when you log in — not at boot. On a
# machine that reboots unattended, turn on automatic login (System Settings >
# Users & Groups > Automatic login) or the API will be down until someone logs
# in. A LaunchDaemon would start at boot but runs as root, which this app has no
# reason to do.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.winevoyage.api"
TEMPLATE="$REPO/deploy/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

render() {
  sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" "$TEMPLATE"
}

case "${1:-}" in
  --print)
    render
    exit 0
    ;;
esac

if [ "$(uname -s)" != "Darwin" ]; then
  echo "launchd is macOS only. On Linux, use a systemd unit; on either, 'pm2 start ./run.sh --name winevoyage' also works." >&2
  echo "To see what this would have installed: $0 --print" >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$TARGET" 2>/dev/null || true
  rm -f "$TARGET"
  echo "Removed $LABEL."
  exit 0
fi

if [ ! -d "$REPO/.venv" ] && [ ! -d "$REPO/venv" ]; then
  echo "No virtualenv in $REPO — run the setup steps in the README first." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
render > "$TARGET"

# bootout first so re-running this picks up an edited plist.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET" 2>/dev/null || launchctl load "$TARGET"

echo "Installed $TARGET"
echo
PORT="${PORT:-8420}"
for _ in $(seq 1 10); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "✓ API is up on port $PORT and will restart with the machine."
    echo
    echo "Next, if you have not already:"
    echo "  tailscale serve --bg --https=443 http://127.0.0.1:$PORT"
    echo "  tailscale serve status      # the https://…ts.net name goes in Settings"
    exit 0
  fi
  sleep 1
done

echo "! The job is installed but /health did not answer within 10s."
echo "  Logs: tail -f $HOME/Library/Logs/winevoyage.log"
echo "  Status: launchctl print gui/$(id -u)/$LABEL | head -20"
exit 1
