import unittest

from data_loader import BREAKS, background_load, create_daily_schedule, create_fleet_schedule, create_reference_schedule, create_schedule, load_machine_rows
from simulation import run_simulation


class SimulationReferenceTests(unittest.TestCase):
    def test_reference_working_hours_are_class_based(self):
        self.assertEqual(sum(create_schedule(100, "high", machine_class="A")), 32)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="A")), 24)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="B")), 16)
        self.assertEqual(sum(create_schedule(100, "high", machine_class="C")), 8)
        self.assertEqual(sum(create_schedule(100, "low", machine_class="C")), 8)

    def test_fleet_schedule_preserves_all_class_scenario_hours(self):
        expected = {
            ("A", "high"): 8,
            ("A", "low"): 6,
            ("B", "high"): 4,
            ("B", "low"): 4,
            ("C", "high"): 2,
            ("C", "low"): 2,
        }
        for (machine_class, scenario), hours in expected.items():
            rows = [{"machine_id": "test-1", "name": "test", "annual_hours": 100, "machine_class": machine_class}]
            schedule = create_fleet_schedule(rows, scenario, "staggered")["test-1"]
            self.assertEqual(sum(schedule.productive), hours * 4)
            self.assertLessEqual(schedule.end_step, 64)
            self.assertGreaterEqual(schedule.start_step, 28)
            self.assertFalse(any(schedule.productive[BREAKS[0][0]:BREAKS[0][1]]))
            self.assertFalse(any(schedule.productive[BREAKS[1][0]:BREAKS[1][1]]))
            self.assertFalse(any(schedule.productive[:28]))
            self.assertFalse(any(schedule.productive[64:]))

    def test_staggered_fleet_assigns_distinct_short_shift_starts(self):
        rows = [
            {"machine_id": "b-01", "name": "B1", "annual_hours": 100, "machine_class": "B"},
            {"machine_id": "b-02", "name": "B2", "annual_hours": 100, "machine_class": "B"},
            {"machine_id": "b-03", "name": "B3", "annual_hours": 100, "machine_class": "B"},
        ]
        schedules = create_fleet_schedule(rows, "high", "staggered")

        self.assertEqual(len({schedule.start_step for schedule in schedules.values()}), 3)

    def test_fleet_schedule_is_deterministic_and_centered_remains_available(self):
        rows = [
            {"machine_id": "c-02", "name": "C2", "annual_hours": 100, "machine_class": "C"},
            {"machine_id": "c-01", "name": "C1", "annual_hours": 100, "machine_class": "C"},
        ]
        first = create_fleet_schedule(rows, "low", "staggered")
        repeat = create_fleet_schedule(rows, "low", "staggered")
        centered = create_fleet_schedule(rows, "low", "centered")

        self.assertEqual(first, repeat)
        self.assertEqual(len({schedule.start_step for schedule in centered.values()}), 1)

    def test_create_schedule_preserves_original_reference_block(self):
        reference = create_reference_schedule(100, "high", "A")
        compatibility = create_schedule(100, "high", machine_class="A")

        self.assertEqual(reference, compatibility)
        self.assertTrue(all(reference[32:64]))
        self.assertFalse(any(reference[:32]))
        self.assertTrue(any(reference[36:38]))

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
        self.assertEqual(
            {machine.machine_id for machine in result.machines},
            {row["machine_id"] for row in result.schedule_table},
        )

    def test_low_load_uses_vehicle_values_from_model_csv(self):
        rows = load_machine_rows("Beräkningar - Modell.csv")
        schedules = create_fleet_schedule(rows, "low", "centered")

        self.assertEqual(rows[0]["low_load_hours"], 6.0)
        self.assertEqual(rows[1]["low_load_hours"], 5.0)
        for row in rows:
            expected_steps = round(row["low_load_hours"] * 4)
            self.assertEqual(sum(schedules[row["machine_id"]].productive), expected_steps)

    def test_seasonal_baseload_profiles_vary_over_the_day(self):
        winter = background_load("high", "winter")
        summer = background_load("low", "summer")

        self.assertEqual(len(winter), 96)
        self.assertEqual(len(summer), 96)
        self.assertEqual(min(winter), 150.0)
        self.assertEqual(max(winter), 250.0)
        self.assertEqual(min(summer), 40.0)
        self.assertEqual(max(summer), 100.0)
        self.assertEqual(winter[0], winter[3])
        self.assertEqual(winter[9 * 4], 250.0)
        self.assertEqual(summer[0], 40.0)
        self.assertEqual(summer[10 * 4], 100.0)
        self.assertEqual(background_load("high").tolist(), winter.tolist())
        self.assertEqual(background_load("low").tolist(), summer.tolist())

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