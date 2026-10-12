import unittest

from data_loader import BREAKS, create_daily_schedule, create_schedule
from simulation import run_simulation


class SimulationReferenceTests(unittest.TestCase):
    def test_reference_working_hours_are_class_based(self):
        self.assertEqual(sum(create_schedule(100, "high", machine_class="A")), 32)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="A")), 24)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="C")), 8)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="C")), 8)

    def test_daily_schedules_fit_the_operating_window_and_breaks(self):
        cases = [("A", "high", 8), ("A", "low", 6), ("B", "high", 4), ("C", "high", 2)]

        for machine_class, scenario, expected_hours in cases:
            with self.subTest(machine_class=machine_class, scenario=scenario):
                schedule = create_daily_schedule(100, scenario, machine_class)
                self.assertEqual(sum(schedule.productive), expected_hours * 4)
                self.assertLessEqual(schedule.end_step, 64)
                self.assertGreaterEqual(schedule.start_step, 28)
                self.assertTrue(any(schedule.shift_window))
                for break_start, break_end in BREAKS:
                    self.assertFalse(any(schedule.productive[break_start:break_end]))

    def test_daily_schedule_is_reproducible_and_short_shifts_are_staggered(self):
        first = create_daily_schedule(100, "high", "B")
        repeat = create_daily_schedule(100, "high", "B")

        self.assertEqual(first, repeat)
        self.assertNotEqual(first.start_label, "07:00")
        self.assertNotEqual(first.start_step, repeat.end_step)

    def test_simulation_exposes_machine_schedule_table(self):
        result = run_simulation()

        self.assertEqual(len(result.schedule_table), len(result.machines))
        self.assertTrue(all(row["end"] <= "16:00" for row in result.schedule_table))

    def test_baseline_is_deterministic_and_respects_reference_limits(self):
        result = run_simulation()
        repeat = run_simulation()

        self.assertEqual(result.soc_history, repeat.soc_history)
        self.assertEqual(len(result.swaps), 27)
        self.assertTrue(all(10.0 <= soc <= 80.0 for values in result.soc_history.values() for soc in values))
        self.assertTrue(all(swap["duration_minutes"] == 25 for swap in result.swaps))
        self.assertLessEqual(result.max_simultaneously_charging, 40)
        self.assertEqual(result.peak_charging_load_kw, result.max_simultaneously_charging * 22.0)
        self.assertEqual(result.peak_total_site_load_kw, max(result.total_kw))

    def test_charging_efficiency_distinguishes_grid_and_stored_energy(self):
        result = run_simulation()
        stored = sum(result.charging_energy_kwh)
        grid = sum(result.grid_energy_kwh)

        self.assertAlmostEqual(grid * result.charging_efficiency, stored)
        self.assertEqual(result.charging_efficiency, 0.92)


if __name__ == "__main__":
    unittest.main()