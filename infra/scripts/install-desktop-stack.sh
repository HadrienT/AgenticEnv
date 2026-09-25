#!/usr/bin/env bash
# WP08f -- make "Start Session" in the chat client bring the whole stack up
# without spawning a terminal.
#
# Installs:
#   1. the openhands-bridge as a `systemctl --user` unit (+ linger so it
#      survives disconnects);
#   2. a narrow sudoers NOPASSWD rule so the extension can start/stop the
#      privileged units (llama-server, llama-bridge, docker) silently.
#
# Re-runnable. The sudoers step is the only one that needs root and it asks
# once.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_NAME="$(id -un)"
UNIT_SRC="$REPO/infra/systemd/agenticenv-bridge.service"
SUDOERS_SRC="$REPO/infra/sudoers.d/agenticenv-stack"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

echo "==> openhands-bridge as a user service"
mkdir -p "$USER_UNIT_DIR"
install -m 0644 "$UNIT_SRC" "$USER_UNIT_DIR/agenticenv-bridge.service"
systemctl --user daemon-reload
systemctl --user enable agenticenv-bridge.service
if [[ "$(loginctl show-user "$USER_NAME" -p Linger --value 2>/dev/null || echo no)" != "yes" ]]; then
  echo "    enabling linger (keeps the bridge alive across SSH / VS Code disconnects)"
  sudo loginctl enable-linger "$USER_NAME"
fi
echo "    systemctl --user start agenticenv-bridge   # to start it now"

echo "==> sudoers rule for the privileged units"
if [[ "$USER_NAME" != "hadriensuper" ]]; then
  echo "    NOTE: the shipped rule names user 'hadriensuper'; edit $SUDOERS_SRC first." >&2
fi
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cp "$SUDOERS_SRC" "$tmp"
if sudo visudo -cf "$tmp" >/dev/null; then
  sudo install -m 0440 -o root -g root "$tmp" /etc/sudoers.d/agenticenv-stack
  echo "    installed /etc/sudoers.d/agenticenv-stack"
else
  echo "    REFUSED: $SUDOERS_SRC does not pass 'visudo -c'." >&2
  exit 1
fi

echo
echo "Done. In the extension, 'Start Session' can now start missing components"
echo "silently. Check: systemctl --user status agenticenv-bridge"
