from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable

Coord = tuple[int, int]

GLIDER_PATTERN: tuple[Coord, ...] = (
  (1, 0),
  (2, 1),
  (0, 2),
  (1, 2),
  (2, 2),
)

_NEIGHBOR_OFFSETS: tuple[Coord, ...] = tuple(
  (dx, dy)
  for dx in (-1, 0, 1)
  for dy in (-1, 0, 1)
  if not (dx == 0 and dy == 0)
)


@dataclass(frozen=True)
class PatternSpec:
  name: str
  cells: tuple[Coord, ...]
  behavior: str
  weight: float


PATTERN_LIBRARY: dict[str, PatternSpec] = {
  "glider": PatternSpec(
    name="glider",
    cells=GLIDER_PATTERN,
    behavior="spaceship",
    weight=4.0,
  ),
  "lwss": PatternSpec(
    name="lwss",
    cells=(
      (1, 0),
      (4, 0),
      (0, 1),
      (0, 2),
      (4, 2),
      (0, 3),
      (1, 3),
      (2, 3),
      (3, 3),
    ),
    behavior="spaceship",
    weight=2.0,
  ),
  "blinker": PatternSpec(
    name="blinker",
    cells=(
      (0, 1),
      (1, 1),
      (2, 1),
    ),
    behavior="oscillator",
    weight=1.8,
  ),
  "toad": PatternSpec(
    name="toad",
    cells=(
      (1, 0),
      (2, 0),
      (3, 0),
      (0, 1),
      (1, 1),
      (2, 1),
    ),
    behavior="oscillator",
    weight=1.5,
  ),
  "beacon": PatternSpec(
    name="beacon",
    cells=(
      (0, 0),
      (1, 0),
      (0, 1),
      (1, 1),
      (2, 2),
      (3, 2),
      (2, 3),
      (3, 3),
    ),
    behavior="oscillator",
    weight=1.2,
  ),
  "block": PatternSpec(
    name="block",
    cells=(
      (0, 0),
      (1, 0),
      (0, 1),
      (1, 1),
    ),
    behavior="still-life",
    weight=1.0,
  ),
  "r_pentomino": PatternSpec(
    name="r_pentomino",
    cells=(
      (1, 0),
      (2, 0),
      (0, 1),
      (1, 1),
      (1, 2),
    ),
    behavior="methuselah",
    weight=1.0,
  ),
}


@dataclass
class LifeWorld:
  width: int
  height: int
  max_alive: int = 90_000
  alive: set[Coord] = field(default_factory=set)

  def __post_init__(self) -> None:
    self.width = max(3, int(self.width))
    self.height = max(3, int(self.height))
    self.max_alive = max(1, int(self.max_alive))
    self._trim_to_limit()

  def normalize(self, x: int, y: int) -> Coord:
    return (x % self.width, y % self.height)

  def clear(self) -> None:
    self.alive.clear()

  def set_alive(self, cells: Iterable[Coord]) -> None:
    self.alive = {self.normalize(x, y) for x, y in cells}
    self._trim_to_limit()

  def add_cell(self, x: int, y: int) -> None:
    self.alive.add(self.normalize(x, y))
    self._trim_to_limit()

  def seed_random(self, rng: random.Random, *, density: float = 0.025) -> None:
    self.clear()
    density = max(0.001, min(density, 0.95))
    target = min(self.max_alive, max(1, int(self.width * self.height * density)))

    while len(self.alive) < target:
      self.alive.add((rng.randrange(self.width), rng.randrange(self.height)))

  def seed_mixed(
    self,
    rng: random.Random,
    *,
    glider_count: int = 12,
    cluster_count: int = 8,
  ) -> None:
    self.clear()

    for _ in range(max(1, cluster_count)):
      cx = rng.randrange(self.width)
      cy = rng.randrange(self.height)
      radius = rng.randint(2, 6)
      cluster_cells = rng.randint(18, 88)

      for _ in range(cluster_cells):
        if rng.random() > 0.78:
          continue
        x = (cx + rng.randint(-radius, radius)) % self.width
        y = (cy + rng.randint(-radius, radius)) % self.height
        self.alive.add((x, y))

    pattern_spawns = max(1, glider_count)
    for _ in range(pattern_spawns):
      self.spawn_pattern(rng)

    base_target = min(self.max_alive, max(64, (self.width * self.height) // 35))
    while len(self.alive) < base_target:
      self.alive.add((rng.randrange(self.width), rng.randrange(self.height)))

    self._trim_to_limit()

  def spawn_pattern(
    self,
    rng: random.Random,
    *,
    name: str | None = None,
    x: int | None = None,
    y: int | None = None,
    orientation: int | None = None,
    mirror: bool | None = None,
  ) -> str:
    spec = self._resolve_pattern_spec(rng, name)

    base_x = x if x is not None else rng.randrange(self.width)
    base_y = y if y is not None else rng.randrange(self.height)
    turns = orientation if orientation is not None else rng.randrange(4)

    shape = self._normalize_cells(spec.cells)
    for _ in range(turns % 4):
      shape = self._rotate_clockwise(shape)

    if mirror is None:
      mirror = rng.random() < 0.5
    if mirror:
      shape = self._mirror_horizontal(shape)

    for dx, dy in shape:
      self.alive.add(self.normalize(base_x + dx, base_y + dy))

    self._trim_to_limit()
    return spec.name

  def spawn_glider(
    self,
    rng: random.Random,
    *,
    x: int | None = None,
    y: int | None = None,
    orientation: int | None = None,
  ) -> None:
    self.spawn_pattern(
      rng,
      name="glider",
      x=x,
      y=y,
      orientation=orientation,
      mirror=None if orientation is None else False,
    )

  def step(self) -> None:
    neighbor_counts: dict[Coord, int] = {}

    for x, y in self.alive:
      for dx, dy in _NEIGHBOR_OFFSETS:
        nx = (x + dx) % self.width
        ny = (y + dy) % self.height
        key = (nx, ny)
        neighbor_counts[key] = neighbor_counts.get(key, 0) + 1

    next_alive: set[Coord] = set()
    for cell, count in neighbor_counts.items():
      if count == 3 or (count == 2 and cell in self.alive):
        next_alive.add(cell)

    self.alive = next_alive
    self._trim_to_limit()

  def _resolve_pattern_spec(self, rng: random.Random, name: str | None) -> PatternSpec:
    if name is not None:
      try:
        return PATTERN_LIBRARY[name]
      except KeyError as exc:
        raise ValueError(f"Pattern desconocido: {name}") from exc

    specs = tuple(PATTERN_LIBRARY.values())
    weights = tuple(max(0.01, spec.weight) for spec in specs)
    return rng.choices(specs, weights=weights, k=1)[0]

  def _normalize_cells(self, cells: Iterable[Coord]) -> list[Coord]:
    points = list(cells)
    if not points:
      return [(0, 0)]

    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    normalized = [(x - min_x, y - min_y) for x, y in points]
    normalized.sort()
    return normalized

  def _rotate_clockwise(self, cells: Iterable[Coord]) -> list[Coord]:
    points = self._normalize_cells(cells)
    width = max(x for x, _ in points) + 1
    rotated = [(y, width - 1 - x) for x, y in points]
    return self._normalize_cells(rotated)

  def _mirror_horizontal(self, cells: Iterable[Coord]) -> list[Coord]:
    points = self._normalize_cells(cells)
    width = max(x for x, _ in points) + 1
    mirrored = [(width - 1 - x, y) for x, y in points]
    return self._normalize_cells(mirrored)

  def _trim_to_limit(self) -> None:
    if len(self.alive) <= self.max_alive:
      return
    kept = sorted(self.alive)[: self.max_alive]
    self.alive = set(kept)
