from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class LockResult:
  ok: bool
  command: str
  details: str


def _command_exists(command: str) -> bool:
  parts = shlex.split(command)
  if not parts:
    return False
  return shutil.which(parts[0]) is not None


def _spawn_command(command: str) -> subprocess.Popen[str]:
  return subprocess.Popen(
    shlex.split(command),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )


def run_lock_command(
  command: str,
  fallback_command: str,
  *,
  logger: logging.Logger | None = None,
) -> LockResult:
  log = logger or logging.getLogger("lifesuspend.lock")

  tried: list[str] = []
  for candidate in (command, fallback_command):
    current = candidate.strip()
    if not current or current in tried:
      continue
    tried.append(current)

    if not _command_exists(current):
      log.warning("lock command no disponible: %s", current)
      continue

    try:
      proc = _spawn_command(current)
    except OSError as exc:
      log.warning("fallo lock command %s: %s", current, exc)
      continue

    details = f"Lock command lanzado: {current} (pid={proc.pid})"
    return LockResult(ok=True, command=current, details=details)

  return LockResult(
    ok=False,
    command="",
    details=f"No se pudo ejecutar lock command. Intentados: {', '.join(tried)}",
  )
