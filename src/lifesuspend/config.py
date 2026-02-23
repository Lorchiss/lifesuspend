from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "lifesuspend" / "config.toml"
DEFAULT_SOCKET_PATH = Path.home() / ".cache" / "lifesuspend" / "socket"


def _as_dict(value: Any) -> dict[str, Any]:
  if isinstance(value, dict):
    return value
  return {}


def _coerce_int(value: Any, default: int, *, min_value: int = 1) -> int:
  try:
    parsed = int(value)
  except (TypeError, ValueError):
    return default
  if parsed < min_value:
    return min_value
  return parsed


def _coerce_float(
  value: Any,
  default: float,
  *,
  min_value: float,
  max_value: float,
) -> float:
  try:
    parsed = float(value)
  except (TypeError, ValueError):
    return default
  if parsed < min_value:
    return min_value
  if parsed > max_value:
    return max_value
  return parsed


def _coerce_str(value: Any, default: str) -> str:
  if isinstance(value, str):
    cleaned = value.strip()
    if cleaned:
      return cleaned
  return default


@dataclass(frozen=True)
class IdleConfig:
  screensaver_timeout_sec: int = 10
  lock_timeout_sec: int = 300


@dataclass(frozen=True)
class VisualConfig:
  overlay_opacity: float = 0.72
  cell_size_px: int = 6
  fps: int = 30
  seed_style: str = "mixed"


@dataclass(frozen=True)
class SimulationConfig:
  step_hz: int = 12
  max_alive_cells: int = 90_000
  spawn_pattern_every_sec: int = 2


@dataclass(frozen=True)
class LockConfig:
  command: str = "hyprlock"
  fallback_command: str = "loginctl lock-session"


@dataclass(frozen=True)
class AppConfig:
  idle: IdleConfig = field(default_factory=IdleConfig)
  visual: VisualConfig = field(default_factory=VisualConfig)
  simulation: SimulationConfig = field(default_factory=SimulationConfig)
  lock: LockConfig = field(default_factory=LockConfig)

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> AppConfig:
    idle_data = _as_dict(data.get("idle"))
    visual_data = _as_dict(data.get("visual"))
    simulation_data = _as_dict(data.get("simulation"))
    lock_data = _as_dict(data.get("lock"))

    idle = IdleConfig(
      screensaver_timeout_sec=_coerce_int(
        idle_data.get("screensaver_timeout_sec"),
        IdleConfig.screensaver_timeout_sec,
        min_value=10,
      ),
      lock_timeout_sec=_coerce_int(
        idle_data.get("lock_timeout_sec"),
        IdleConfig.lock_timeout_sec,
        min_value=30,
      ),
    )

    if idle.lock_timeout_sec <= idle.screensaver_timeout_sec:
      idle = IdleConfig(
        screensaver_timeout_sec=idle.screensaver_timeout_sec,
        lock_timeout_sec=idle.screensaver_timeout_sec + 30,
      )

    visual = VisualConfig(
      overlay_opacity=_coerce_float(
        visual_data.get("overlay_opacity"),
        VisualConfig.overlay_opacity,
        min_value=0.05,
        max_value=0.98,
      ),
      cell_size_px=_coerce_int(
        visual_data.get("cell_size_px"),
        VisualConfig.cell_size_px,
        min_value=2,
      ),
      fps=_coerce_int(visual_data.get("fps"), VisualConfig.fps, min_value=1),
      seed_style=_coerce_str(visual_data.get("seed_style"), VisualConfig.seed_style),
    )

    spawn_every = simulation_data.get(
      "spawn_pattern_every_sec",
      simulation_data.get("spawn_glider_every_sec"),
    )

    simulation = SimulationConfig(
      step_hz=_coerce_int(
        simulation_data.get("step_hz"),
        SimulationConfig.step_hz,
        min_value=1,
      ),
      max_alive_cells=_coerce_int(
        simulation_data.get("max_alive_cells"),
        SimulationConfig.max_alive_cells,
        min_value=500,
      ),
      spawn_pattern_every_sec=_coerce_int(
        spawn_every,
        SimulationConfig.spawn_pattern_every_sec,
        min_value=1,
      ),
    )

    lock = LockConfig(
      command=_coerce_str(lock_data.get("command"), LockConfig.command),
      fallback_command=_coerce_str(
        lock_data.get("fallback_command"),
        LockConfig.fallback_command,
      ),
    )

    return cls(idle=idle, visual=visual, simulation=simulation, lock=lock)

  @classmethod
  def load(cls, path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
      return cls()

    with config_path.open("rb") as fh:
      data = tomllib.load(fh)

    return cls.from_dict(_as_dict(data))


def resolve_socket_path(path: str | Path | None = None) -> Path:
  if path is None:
    return DEFAULT_SOCKET_PATH
  return Path(path).expanduser()
