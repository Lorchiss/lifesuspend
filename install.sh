#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/lifesuspend"
HYPR_CONFIG_DIR="$HOME/.config/hypr"
CACHE_DIR="$HOME/.cache/lifesuspend"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: install.sh [--force]

Options:
  --force    Sobrescribe config/hypridle templates en ~/.config/lifesuspend.
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

if [[ ! -f /etc/arch-release ]]; then
  echo "[error] Este instalador esta orientado a Arch Linux." >&2
  exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
  echo "[error] pacman no encontrado." >&2
  exit 1
fi

required_packages=(
  hypridle
  hyprlock
  python
  python-gobject
  gtk4-layer-shell
)

missing_packages=()
for pkg in "${required_packages[@]}"; do
  if ! pacman -Q "$pkg" >/dev/null 2>&1; then
    missing_packages+=("$pkg")
  fi
done

if [[ ${#missing_packages[@]} -gt 0 ]]; then
  echo "[info] instalando dependencias faltantes: ${missing_packages[*]}"
  sudo pacman -S --needed "${missing_packages[@]}"
else
  echo "[info] dependencias del sistema OK"
fi

mkdir -p "$CONFIG_DIR" "$CACHE_DIR" "$BIN_DIR" "$SYSTEMD_USER_DIR"

if [[ ! -f "$CONFIG_DIR/config.toml" || "$FORCE" -eq 1 ]]; then
  cp "$REPO_DIR/templates/config.toml" "$CONFIG_DIR/config.toml"
  echo "[ok] config instalada: $CONFIG_DIR/config.toml"
else
  echo "[skip] config existente preservada: $CONFIG_DIR/config.toml"
fi

if [[ ! -f "$CONFIG_DIR/hypridle.conf" || "$FORCE" -eq 1 ]]; then
  sed "s#{{HOME}}#$HOME#g" "$REPO_DIR/templates/hypridle.conf" > "$CONFIG_DIR/hypridle.conf"
  echo "[ok] hypridle config instalada: $CONFIG_DIR/hypridle.conf"
else
  echo "[skip] hypridle config existente preservada: $CONFIG_DIR/hypridle.conf"
fi

mkdir -p "$HYPR_CONFIG_DIR"
HYPRIDLE_DEFAULT_PATH="$HYPR_CONFIG_DIR/hypridle.conf"
if [[ -e "$HYPRIDLE_DEFAULT_PATH" && ! -L "$HYPRIDLE_DEFAULT_PATH" ]]; then
  if [[ "$FORCE" -eq 1 ]]; then
    mv "$HYPRIDLE_DEFAULT_PATH" "$HYPRIDLE_DEFAULT_PATH.bak.$(date +%s)"
  else
    echo "[warn] existe $HYPRIDLE_DEFAULT_PATH y no es symlink; se deja intacto."
    echo "[warn] usa --force para hacer backup y reemplazarlo."
  fi
fi

if [[ ! -e "$HYPRIDLE_DEFAULT_PATH" || -L "$HYPRIDLE_DEFAULT_PATH" || "$FORCE" -eq 1 ]]; then
  ln -sfn "$CONFIG_DIR/hypridle.conf" "$HYPRIDLE_DEFAULT_PATH"
  echo "[ok] symlink hypridle default: $HYPRIDLE_DEFAULT_PATH -> $CONFIG_DIR/hypridle.conf"
fi

cat > "$BIN_DIR/lifesuspendd" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$REPO_DIR"
export PYTHONPATH="\$REPO_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"

if [[ -f /usr/lib/libgtk4-layer-shell.so.0 ]]; then
  export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so.0\${LD_PRELOAD:+:\$LD_PRELOAD}"
fi

runtime_dir="\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}"
if [[ -z "\${WAYLAND_DISPLAY:-}" ]]; then
  for sock in "\$runtime_dir"/wayland-*; do
    [[ -S "\$sock" ]] || continue
    export WAYLAND_DISPLAY="\$(basename "\$sock")"
    break
  done
fi

exec python3 -m lifesuspend.daemon "\$@"
WRAPPER

cat > "$BIN_DIR/lifesuspendctl" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$REPO_DIR"
export PYTHONPATH="\$REPO_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"

exec python3 -m lifesuspend.cli "\$@"
WRAPPER

chmod +x "$BIN_DIR/lifesuspendd" "$BIN_DIR/lifesuspendctl"
echo "[ok] wrappers instalados en $BIN_DIR"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "[warn] $BIN_DIR no esta en tu PATH actual."
  echo "[warn] agrega en ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo "[warn] y recarga shell: source ~/.zshrc"
fi

cp "$REPO_DIR/systemd/user/lifesuspend-daemon.service" "$SYSTEMD_USER_DIR/"
cp "$REPO_DIR/systemd/user/lifesuspend-idle.service" "$SYSTEMD_USER_DIR/"

echo "[ok] units copiadas a $SYSTEMD_USER_DIR"

if systemctl --user is-active --quiet hypridle.service; then
  echo "[warn] hypridle.service ya esta activo."
  echo "[warn] recomienda desactivarlo para evitar doble gestor idle:"
  echo "       systemctl --user disable --now hypridle.service"
fi

systemctl --user daemon-reload
systemctl --user enable --now lifesuspend-daemon.service lifesuspend-idle.service

echo "[ok] servicios habilitados e iniciados"
echo "[hint] estado: systemctl --user status lifesuspend-daemon.service"
