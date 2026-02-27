# lifesuspend

[![Platform](https://img.shields.io/badge/platform-Arch%20Linux-1793D1?logo=arch-linux&logoColor=white)](https://archlinux.org)
[![Compositor](https://img.shields.io/badge/compositor-Hyprland-58E1FF)](https://hyprland.org)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Wayland](https://img.shields.io/badge/display-Wayland-6D4AFF)](https://wayland.freedesktop.org)

`lifesuspend` es un repo standalone para Arch + Hyprland que agrega una pantalla de inactividad con overlay translucido y simulacion de Conway's Game of Life.

## Features

- Overlay fullscreen por monitor con GTK4 + layer-shell.
- Simulacion en un solo plano global para todos los monitores (continua entre pantallas).
- Simulacion Game of Life sparse (B3/S23) con seed mixto (organico + gliders).
- Control IPC por socket Unix con `lifesuspendctl`.
- Integracion con `hypridle`:
  - 10s: mostrar overlay.
  - resume: ocultar overlay.
  - 300s: ejecutar lock (`hyprlock`).
- Instalacion automatica con `install.sh` (deps + systemd user units).

## Quick Install

```bash
git clone https://github.com/<tu-usuario>/lifesuspend.git && cd lifesuspend && bash install.sh
```

Comprobacion rapida:

```bash
systemctl --user status lifesuspend-daemon.service lifesuspend-idle.service
lifesuspendctl preview --seconds 5
```

## Estructura

```text
lifesuspend/
  install.sh
  uninstall.sh
  src/lifesuspend/
  templates/
  systemd/user/
  tests/
```

## Requisitos

- Arch Linux
- Hyprland
- `sudo` habilitado para instalar dependencias

Dependencias gestionadas por instalador:

- `hypridle`
- `hyprlock`
- `python`
- `python-gobject`
- `gtk4-layer-shell`

## Instalacion

```bash
git clone <tu-repo>/lifesuspend.git
cd lifesuspend
bash install.sh
```

Si luego no te reconoce `lifesuspendctl`, agrega `~/.local/bin` al `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Esto hace:

1. Preflight Arch + paquetes.
2. Instala faltantes con `sudo pacman -S --needed ...`.
3. Instala wrappers en `~/.local/bin/`:
   - `lifesuspendd`
   - `lifesuspendctl`
4. Crea config en `~/.config/lifesuspend/`.
5. Crea symlink de compatibilidad:
   - `~/.config/hypr/hypridle.conf -> ~/.config/lifesuspend/hypridle.conf`
6. Instala y enciende:
   - `lifesuspend-daemon.service`
   - `lifesuspend-idle.service`

## Configuracion

Archivo: `~/.config/lifesuspend/config.toml`

```toml
[idle]
screensaver_timeout_sec = 10
lock_timeout_sec = 300

[visual]
overlay_opacity = 0.72
cell_size_px = 6
fps = 30
seed_style = "mixed"

[simulation]
step_hz = 12
max_alive_cells = 90000
spawn_pattern_every_sec = 2

[lock]
command = "hyprlock"
fallback_command = "loginctl lock-session"
```

## CLI

```bash
lifesuspendctl show
lifesuspendctl hide
lifesuspendctl lock
lifesuspendctl status
lifesuspendctl reload
lifesuspendctl preview --seconds 5
```

`preview` muestra overlay por N segundos y luego ejecuta `hide` automaticamente.

## Servicios

- `lifesuspend-daemon.service`: daemon visual + IPC.
- `lifesuspend-idle.service`: `hypridle` leyendo `~/.config/hypr/hypridle.conf`.

Estado rapido:

```bash
systemctl --user status lifesuspend-daemon.service
systemctl --user status lifesuspend-idle.service
journalctl --user -u lifesuspend-daemon.service -f
```

## Testing

```bash
make test
# o directamente
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Pruebas manuales recomendadas:

```bash
# Estado general
lifesuspendctl status --json

# Preview sin quedarse "a ciegas"
lifesuspendctl preview --seconds 5

# Flujo manual completo
lifesuspendctl show
lifesuspendctl hide
lifesuspendctl lock
```

## Comportamiento de la simulacion

- `seed_style = "mixed"`:
  - clusters organicos aleatorios
  - patrones prehechos iniciales
  - relleno aleatorio hasta densidad objetivo
- patrones prehechos actualmente activos:
  - `glider` (spaceship)
  - `lwss` (spaceship)
  - `blinker` (oscilador)
  - `toad` (oscilador)
  - `beacon` (oscilador)
  - `block` (still-life)
  - `r_pentomino` (methuselah)
- durante la ejecucion se inyecta 1 patron del pool cada `spawn_pattern_every_sec`.
- `seed_style != "mixed"` usa seed aleatorio puro.

## Troubleshooting

- Si no aparece overlay, verifica entorno Wayland en el servicio:
  - `echo $WAYLAND_DISPLAY`
  - `ls /run/user/$UID/wayland-*`
- Si ya usas otro `hypridle`, desactivalo para evitar conflicto:
  - `systemctl --user disable --now hypridle.service`

## Desinstalacion

```bash
bash uninstall.sh
```

Para borrar tambien configuracion/cache:

```bash
bash uninstall.sh --purge-config
```
