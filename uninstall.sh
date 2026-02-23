#!/usr/bin/env bash
set -euo pipefail

PURGE_CONFIG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-config)
      PURGE_CONFIG=1
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: uninstall.sh [--purge-config]

Options:
  --purge-config   Elimina ~/.config/lifesuspend y ~/.cache/lifesuspend.
USAGE
      exit 0
      ;;
    *)
      echo "[error] argumento desconocido: $1" >&2
      exit 2
      ;;
  esac
  shift
done

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

systemctl --user disable --now lifesuspend-idle.service lifesuspend-daemon.service >/dev/null 2>&1 || true

rm -f "$SYSTEMD_USER_DIR/lifesuspend-daemon.service"
rm -f "$SYSTEMD_USER_DIR/lifesuspend-idle.service"
rm -f "$BIN_DIR/lifesuspendd"
rm -f "$BIN_DIR/lifesuspendctl"

systemctl --user daemon-reload

if [[ "$PURGE_CONFIG" -eq 1 ]]; then
  rm -rf "$HOME/.config/lifesuspend" "$HOME/.cache/lifesuspend"
  echo "[ok] configuracion y cache eliminados"
else
  echo "[ok] configuracion preservada en ~/.config/lifesuspend"
fi

echo "[ok] lifesuspend desinstalado"
