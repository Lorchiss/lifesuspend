from __future__ import annotations

import random
import unittest

from lifesuspend.life import GLIDER_PATTERN, PATTERN_LIBRARY, LifeWorld


class LifeWorldTests(unittest.TestCase):
  def test_block_pattern_is_stable(self) -> None:
    world = LifeWorld(8, 8, max_alive=100)
    block = {(2, 2), (2, 3), (3, 2), (3, 3)}
    world.set_alive(block)

    world.step()

    self.assertEqual(world.alive, block)

  def test_blinker_has_period_two(self) -> None:
    world = LifeWorld(9, 9, max_alive=100)
    start = {(4, 3), (4, 4), (4, 5)}
    expected_after_one = {(3, 4), (4, 4), (5, 4)}
    world.set_alive(start)

    world.step()
    self.assertEqual(world.alive, expected_after_one)

    world.step()
    self.assertEqual(world.alive, start)

  def test_glider_moves_one_diagonal_every_four_steps(self) -> None:
    world = LifeWorld(20, 20, max_alive=100)
    shifted = {(x + 5, y + 5) for x, y in GLIDER_PATTERN}
    world.set_alive(shifted)

    for _ in range(4):
      world.step()

    expected = {((x + 6) % 20, (y + 6) % 20) for x, y in GLIDER_PATTERN}
    self.assertEqual(world.alive, expected)

  def test_toroidal_edges_interact(self) -> None:
    world = LifeWorld(5, 5, max_alive=100)
    world.set_alive({(0, 0), (4, 0), (0, 4)})

    world.step()

    self.assertIn((4, 4), world.alive)

  def test_density_cap_is_enforced(self) -> None:
    world = LifeWorld(10, 10, max_alive=5)
    all_cells = {(x, y) for x in range(10) for y in range(10)}
    world.set_alive(all_cells)
    self.assertLessEqual(len(world.alive), 5)

    world.seed_random(random.Random(1), density=0.8)
    self.assertLessEqual(len(world.alive), 5)

  def test_spawn_named_prebuilt_pattern(self) -> None:
    world = LifeWorld(40, 40, max_alive=1000)
    rng = random.Random(7)

    name = world.spawn_pattern(rng, name="blinker", x=10, y=10, orientation=0, mirror=False)

    self.assertEqual(name, "blinker")
    self.assertEqual(len(world.alive), len(PATTERN_LIBRARY["blinker"].cells))

  def test_spawn_random_pattern_returns_known_name(self) -> None:
    world = LifeWorld(40, 40, max_alive=1000)
    rng = random.Random(9)

    name = world.spawn_pattern(rng)

    self.assertIn(name, PATTERN_LIBRARY)
    self.assertGreater(len(world.alive), 0)


if __name__ == "__main__":
  unittest.main()
