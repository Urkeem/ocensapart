import os
import sys
import unittest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT_DIR, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from world.weather import GameTime, REAL_SECONDS_PER_GAME_DAY


class GameTimeTests(unittest.TestCase):
    def test_full_game_day_lasts_fifteen_real_minutes(self):
        game_time = GameTime()
        starting_time = game_time.time

        game_time.update(REAL_SECONDS_PER_GAME_DAY)

        self.assertEqual(game_time.day, 2)
        self.assertEqual(game_time.time, starting_time)
        self.assertEqual((game_time.hours, game_time.minutes), (6, 0))

    def test_game_hour_lasts_thirty_seven_and_a_half_seconds(self):
        game_time = GameTime()

        game_time.update(game_time.real_seconds_per_game_hour)

        self.assertEqual((game_time.hours, game_time.minutes), (7, 0))

    def test_large_time_step_rolls_over_every_elapsed_day(self):
        game_time = GameTime()

        game_time.update(REAL_SECONDS_PER_GAME_DAY * 3)

        self.assertEqual(game_time.day, 4)
        self.assertEqual((game_time.hours, game_time.minutes), (6, 0))


if __name__ == "__main__":
    unittest.main()
