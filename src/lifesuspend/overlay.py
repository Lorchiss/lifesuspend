from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell  # type: ignore

from .config import AppConfig
from .life import LifeWorld


@dataclass
class MonitorContext:
  monitor: Gdk.Monitor
  window: Gtk.Window
  area: Gtk.DrawingArea
  width_px: int
  height_px: int
  x_px: int
  y_px: int
  cell_offset_x: int
  cell_offset_y: int
  cell_span_x: int
  cell_span_y: int


class OverlayRenderer:
  def __init__(self, config: AppConfig, *, logger: logging.Logger | None = None) -> None:
    self._config = config
    self._logger = logger or logging.getLogger("lifesuspend.overlay")
    self._rng = random.Random()

    self._ui_thread = threading.current_thread()
    self._loop_ready = threading.Event()
    self._main_loop: GLib.MainLoop | None = None

    self._contexts: list[MonitorContext] = []
    self._world: LifeWorld | None = None
    self._world_origin_x_px = 0
    self._world_origin_y_px = 0

    self._visible = False
    self._render_timer_id: int | None = None
    self._step_timer_id: int | None = None
    self._pattern_timer_id: int | None = None

    self._css_provider: Gtk.CssProvider | None = None

  def run(self) -> None:
    self._ui_thread = threading.current_thread()
    self._install_css()
    self._ensure_windows(force_recreate=True)
    self._install_timers()

    self._main_loop = GLib.MainLoop()
    self._loop_ready.set()

    try:
      self._main_loop.run()
    finally:
      self._remove_timers()
      self._destroy_windows()
      self._loop_ready.clear()

  def stop(self) -> None:
    self._call_ui(self._stop_ui)

  def show(self) -> None:
    self._call_ui(self._show_ui)

  def hide(self) -> None:
    self._call_ui(self._hide_ui)

  def is_visible(self) -> bool:
    return bool(self._call_ui(lambda: self._visible))

  def reload_config(self, config: AppConfig) -> None:
    self._config = config
    self._call_ui(lambda: self._reload_ui(config))

  def _stop_ui(self) -> None:
    self._hide_ui()
    if self._main_loop is not None and self._main_loop.is_running():
      self._main_loop.quit()

  def _reload_ui(self, config: AppConfig) -> None:
    self._config = config
    self._install_timers(recreate=True)
    self._ensure_windows(force_recreate=True)

  def _show_ui(self) -> None:
    self._ensure_windows(force_recreate=False)

    if self._world is None:
      return

    if self._config.visual.seed_style == "mixed":
      self._world.seed_mixed(self._rng)
    else:
      self._world.seed_random(self._rng)

    for ctx in self._contexts:
      ctx.area.queue_draw()
      ctx.window.present()

    self._visible = True

  def _hide_ui(self) -> None:
    for ctx in self._contexts:
      ctx.window.hide()
    self._visible = False

  def _install_css(self) -> None:
    display = Gdk.Display.get_default()
    if display is None:
      raise RuntimeError("No se detecto display GTK")

    if self._css_provider is None:
      self._css_provider = Gtk.CssProvider()
      self._css_provider.load_from_data(
        b"window.lifesuspend-overlay { background-color: transparent; }"
      )
      Gtk.StyleContext.add_provider_for_display(
        display,
        self._css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
      )

  def _install_timers(self, *, recreate: bool = False) -> None:
    if recreate:
      self._remove_timers()

    if self._render_timer_id is None:
      render_ms = max(16, int(1000 / max(1, self._config.visual.fps)))
      self._render_timer_id = GLib.timeout_add(render_ms, self._on_render_tick)

    if self._step_timer_id is None:
      step_ms = max(16, int(1000 / max(1, self._config.simulation.step_hz)))
      self._step_timer_id = GLib.timeout_add(step_ms, self._on_step_tick)

    if self._pattern_timer_id is None:
      pattern_ms = max(250, int(self._config.simulation.spawn_pattern_every_sec * 1000))
      self._pattern_timer_id = GLib.timeout_add(pattern_ms, self._on_pattern_tick)

  def _remove_timers(self) -> None:
    for timer_id in (self._render_timer_id, self._step_timer_id, self._pattern_timer_id):
      if timer_id is not None:
        GLib.source_remove(timer_id)

    self._render_timer_id = None
    self._step_timer_id = None
    self._pattern_timer_id = None

  def _monitor_snapshots(self) -> list[tuple[Gdk.Monitor, int, int, int, int]]:
    display = Gdk.Display.get_default()
    if display is None:
      raise RuntimeError("Display GTK no disponible")

    model = display.get_monitors()
    snapshots: list[tuple[Gdk.Monitor, int, int, int, int]] = []

    count = model.get_n_items()
    for index in range(count):
      monitor = model.get_item(index)
      if monitor is None:
        continue
      geometry = monitor.get_geometry()
      snapshots.append(
        (monitor, geometry.x, geometry.y, geometry.width, geometry.height)
      )

    if not snapshots:
      raise RuntimeError("No hay monitores detectados")

    return snapshots

  def _ensure_windows(self, *, force_recreate: bool) -> None:
    snapshots = self._monitor_snapshots()
    needs_recreate = force_recreate

    if len(snapshots) != len(self._contexts):
      needs_recreate = True

    if not needs_recreate:
      for ctx, (_, x, y, width, height) in zip(self._contexts, snapshots, strict=True):
        if (
          ctx.width_px != width
          or ctx.height_px != height
          or ctx.x_px != x
          or ctx.y_px != y
        ):
          needs_recreate = True
          break

    if needs_recreate:
      self._destroy_windows()

      cell_size = max(1, self._config.visual.cell_size_px)
      origin_x = min(x for _, x, _, _, _ in snapshots)
      origin_y = min(y for _, _, y, _, _ in snapshots)
      max_x = max(x + width for _, x, _, width, _ in snapshots)
      max_y = max(y + height for _, _, y, _, height in snapshots)

      world_cells_w = max(6, (max_x - origin_x + cell_size - 1) // cell_size)
      world_cells_h = max(6, (max_y - origin_y + cell_size - 1) // cell_size)

      self._world_origin_x_px = origin_x
      self._world_origin_y_px = origin_y
      self._world = LifeWorld(
        world_cells_w,
        world_cells_h,
        max_alive=self._config.simulation.max_alive_cells,
      )

      self._contexts = [
        self._create_context(
          monitor=monitor,
          x=x,
          y=y,
          width=width,
          height=height,
          origin_x=origin_x,
          origin_y=origin_y,
          cell_size=cell_size,
        )
        for monitor, x, y, width, height in snapshots
      ]

  def _destroy_windows(self) -> None:
    for ctx in self._contexts:
      try:
        ctx.window.hide()
        ctx.window.destroy()
      except Exception:
        self._logger.exception("Error destruyendo ventana overlay")

    self._contexts = []
    self._world = None

  def _create_context(
    self,
    *,
    monitor: Gdk.Monitor,
    x: int,
    y: int,
    width: int,
    height: int,
    origin_x: int,
    origin_y: int,
    cell_size: int,
  ) -> MonitorContext:
    window = Gtk.Window()
    window.add_css_class("lifesuspend-overlay")
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_focusable(False)

    Gtk4LayerShell.init_for_window(window)
    Gtk4LayerShell.set_namespace(window, "lifesuspend")
    Gtk4LayerShell.set_monitor(window, monitor)
    Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.OVERLAY)
    Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.NONE)

    for edge in (
      Gtk4LayerShell.Edge.TOP,
      Gtk4LayerShell.Edge.RIGHT,
      Gtk4LayerShell.Edge.BOTTOM,
      Gtk4LayerShell.Edge.LEFT,
    ):
      Gtk4LayerShell.set_anchor(window, edge, True)

    area = Gtk.DrawingArea()
    area.set_hexpand(True)
    area.set_vexpand(True)
    area.set_content_width(width)
    area.set_content_height(height)

    cell_offset_x = max(0, (x - origin_x) // cell_size)
    cell_offset_y = max(0, (y - origin_y) // cell_size)
    cell_span_x = max(1, (width + cell_size - 1) // cell_size)
    cell_span_y = max(1, (height + cell_size - 1) // cell_size)

    area.set_draw_func(
      lambda _area, cr, draw_width, draw_height: self._draw_world(
        cr,
        draw_width,
        draw_height,
        cell_offset_x,
        cell_offset_y,
        cell_span_x,
        cell_span_y,
      )
    )

    window.set_child(area)
    window.hide()

    return MonitorContext(
      monitor=monitor,
      window=window,
      area=area,
      width_px=width,
      height_px=height,
      x_px=x,
      y_px=y,
      cell_offset_x=cell_offset_x,
      cell_offset_y=cell_offset_y,
      cell_span_x=cell_span_x,
      cell_span_y=cell_span_y,
    )

  def _draw_world(
    self,
    cr: object,
    width: int,
    height: int,
    cell_offset_x: int,
    cell_offset_y: int,
    cell_span_x: int,
    cell_span_y: int,
  ) -> None:
    cell_size = max(1, self._config.visual.cell_size_px)

    # Cairo context provisto por Gtk.DrawingArea
    cr.set_source_rgba(0.01, 0.02, 0.03, self._config.visual.overlay_opacity)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    world = self._world
    if world is None or not world.alive:
      return

    cr.set_source_rgba(0.82, 0.94, 1.0, 0.82)

    for global_x, global_y in world.alive:
      local_x = global_x - cell_offset_x
      local_y = global_y - cell_offset_y

      if local_x < 0 or local_y < 0:
        continue
      if local_x >= cell_span_x or local_y >= cell_span_y:
        continue

      cr.rectangle(local_x * cell_size, local_y * cell_size, cell_size, cell_size)

    cr.fill()

  def _on_render_tick(self) -> bool:
    if self._visible:
      for ctx in self._contexts:
        ctx.area.queue_draw()
    return True

  def _on_step_tick(self) -> bool:
    if self._visible and self._world is not None:
      self._world.step()
    return True

  def _on_pattern_tick(self) -> bool:
    if self._visible and self._world is not None:
      self._world.spawn_pattern(self._rng)
    return True

  def _call_ui(self, fn: Callable[[], Any]) -> Any:
    if threading.current_thread() is self._ui_thread:
      return fn()

    if not self._loop_ready.wait(timeout=3):
      raise RuntimeError("UI loop no disponible")

    done = threading.Event()
    out: dict[str, object] = {}

    def _runner() -> bool:
      try:
        out["value"] = fn()
      except Exception as exc:
        out["error"] = exc
      finally:
        done.set()
      return False

    GLib.idle_add(_runner, priority=GLib.PRIORITY_HIGH)

    if not done.wait(timeout=3):
      raise RuntimeError("Timeout esperando thread UI")

    error = out.get("error")
    if isinstance(error, Exception):
      raise error

    return out.get("value")
