from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path
from typing import Any

from .config import AppConfig, DEFAULT_CONFIG_PATH, resolve_socket_path
from .ipc import JsonIpcServer
from .lock import run_lock_command
from .overlay import OverlayRenderer


class LifesuspendDaemon:
  def __init__(
    self,
    *,
    config_path: str | Path,
    socket_path: str | Path,
    logger: logging.Logger,
  ) -> None:
    self.logger = logger
    self.config_path = Path(config_path).expanduser()
    self.socket_path = Path(socket_path).expanduser()

    self._config = AppConfig.load(self.config_path)
    self._renderer = OverlayRenderer(self._config, logger=self.logger)
    self._ipc = JsonIpcServer(self.socket_path, self._handle_ipc, logger=self.logger)

    self._state = "hidden"
    self._state_lock = threading.Lock()

  def run(self) -> None:
    self.logger.info("lifesuspendd iniciando")
    self.logger.info("config=%s socket=%s", self.config_path, self.socket_path)

    self._ipc.start()
    try:
      self._renderer.run()
    finally:
      self._ipc.stop()
      self.logger.info("lifesuspendd detenido")

  def stop(self) -> None:
    self.logger.info("deteniendo daemon")
    self._renderer.stop()
    self._ipc.stop()

  def _set_state(self, value: str) -> None:
    with self._state_lock:
      self._state = value

  def _get_state(self) -> str:
    with self._state_lock:
      return self._state

  def show(self) -> Response:
    self._renderer.show()
    self._set_state("visible")
    return {
      "ok": True,
      "state": "visible",
      "details": "Overlay visible",
    }

  def hide(self) -> Response:
    self._renderer.hide()
    self._set_state("hidden")
    return {
      "ok": True,
      "state": "hidden",
      "details": "Overlay oculto",
    }

  def reload(self) -> Response:
    self._config = AppConfig.load(self.config_path)
    self._renderer.reload_config(self._config)
    return {
      "ok": True,
      "state": self._get_state(),
      "details": "Configuracion recargada",
    }

  def lock(self) -> Response:
    self._set_state("locking")
    self._renderer.hide()

    lock_result = run_lock_command(
      self._config.lock.command,
      self._config.lock.fallback_command,
      logger=self.logger,
    )

    self._set_state("hidden")
    return {
      "ok": lock_result.ok,
      "state": "locking" if lock_result.ok else "hidden",
      "details": lock_result.details,
    }

  def status(self) -> Response:
    return {
      "ok": True,
      "state": self._get_state(),
      "details": "Daemon operativo",
      "socket": str(self.socket_path),
      "config": str(self.config_path),
    }

  def _handle_ipc(self, payload: dict[str, Any]) -> dict[str, Any]:
    cmd = str(payload.get("cmd", "")).strip().lower()

    if cmd == "show":
      return self.show()
    if cmd == "hide":
      return self.hide()
    if cmd == "lock":
      return self.lock()
    if cmd == "reload":
      return self.reload()
    if cmd == "status":
      return self.status()

    return {
      "ok": False,
      "state": self._get_state(),
      "details": f"Comando no soportado: {cmd or '<vacio>'}",
    }


Response = dict[str, Any]


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="lifesuspend daemon")
  parser.add_argument(
    "--config",
    default=str(DEFAULT_CONFIG_PATH),
    help="Ruta al config TOML",
  )
  parser.add_argument(
    "--socket",
    default=str(resolve_socket_path(None)),
    help="Ruta del socket Unix IPC",
  )
  parser.add_argument(
    "--verbose",
    action="store_true",
    help="Habilita logs debug",
  )
  return parser


def setup_logging(verbose: bool) -> logging.Logger:
  level = logging.DEBUG if verbose else logging.INFO
  logging.basicConfig(
    level=level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
  )
  return logging.getLogger("lifesuspend")


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)

  logger = setup_logging(args.verbose)

  daemon = LifesuspendDaemon(
    config_path=args.config,
    socket_path=args.socket,
    logger=logger,
  )

  def _on_signal(signum: int, _frame: object) -> None:
    logger.info("signal recibido: %s", signum)
    daemon.stop()

  signal.signal(signal.SIGINT, _on_signal)
  signal.signal(signal.SIGTERM, _on_signal)

  daemon.run()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
