import unittest

from data_loader import create_schedule
from simulation import run_simulation


class SimulationReferenceTests(unittest.TestCase):
    def test_reference_working_hours_are_class_based(self):
        self.assertEqual(sum(create_schedule(100, "high", machine_class="A")), 32)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="A")), 24)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="C")), 8)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="C")), 8)

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