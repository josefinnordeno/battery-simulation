import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from charging import allocate_charging
from data_loader import MODEL_PATH, create_schedule, load_machine_rows
from duty_cycle import DutyCycle
from models import Battery
from reference import run_reference_validation
from scenario_analysis import CostAssumptions, Infrastructure, run_monte_carlo, run_sensitivity
from simulation import run_simulation


def machine_row(power: float = 98, hours: float = 2) -> dict:
    return {
        "name": "Test",
        "type": "Loader",
        "average_power_kw": power,
        "high_daily_hours": hours,
        "low_daily_hours": hours,
        "annual_hours": 1,
    }


class ReferenceTests(unittest.TestCase):
    def test_source_kpis_and_energy(self):
        result = run_reference_validation()
        self.assertEqual(
            result.kpis,
            {
                "swaps": 27,
                "max_simultaneous_charging": 22,
                "peak_charging_kw": 484,
                "peak_total_kw": 734,
                "minimum_reserve": 3,
            },
        )
        self.assertEqual(len(result.swaps), 27)
        self.assertAlmostEqual(result.grid_charging_energy_kwh, 2134)
        self.assertAlmostEqual(result.stored_charging_energy_kwh, 2134 * 0.92)
        self.assertAlmostEqual(result.charge_time_hours, 4.841897233, places=8)
        # These are two distinct tables, not interchangeable physical timelines.
        self.assertIn("09.30.00: aggregate swaps=3, timed swaps=0", result.discrepancies)

    def test_duplicate_machine_names_have_distinct_event_rows(self):
        result = run_reference_validation()
        counts = {
            index: sum(event["machine_index"] == index for event in result.swaps)
            for index in range(15)
        }
        self.assertEqual(list(counts.values()), [3, 2, 2, 2, 2, 2, 3, 4, 2, 2, 1, 1, 0, 0, 1])

    def test_inconsistent_reference_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.csv"
            path.write_text(
                MODEL_PATH.read_text().replace("14.30.00,5,0,5,22,484", "14.30.00,5,0,5,21,484")
            )
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                run_reference_validation(path)

    def test_inconsistent_reference_completion_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.csv"
            path.write_text(MODEL_PATH.read_text().replace("15.16.25", "15.15.25", 1))
            with self.assertRaisesRegex(ValueError, "completion time mismatch"):
                run_reference_validation(path)


class InputTests(unittest.TestCase):
    def test_csv_scenario_hours_and_unchanged_mean_powers(self):
        rows = load_machine_rows()
        self.assertEqual(len(rows), 15)
        for row in rows:
            self.assertEqual(row["high_daily_hours"], {"A": 8, "B": 4, "C": 2}[row["class_code"]])
            self.assertAlmostEqual(
                sum(create_schedule(row["low_daily_hours"], "low")) / 4, row["low_daily_hours"]
            )
        self.assertEqual(rows[0]["average_power_kw"], 40.3)
        self.assertEqual(rows[1]["average_power_kw"], 30)
        self.assertEqual(rows[7]["average_power_kw"], 61.2)

    def test_explicit_daily_hours_no_rng_required(self):
        for hours in (0, 2, 4, 8, 4.9, 0.5):
            schedule = create_schedule(hours, "high")
            self.assertEqual(len(schedule), 96)
            self.assertAlmostEqual(sum(schedule) * 0.25, hours)
            self.assertFalse(any(schedule[:32]))
            self.assertFalse(any(schedule[64:]))

    def test_invalid_inputs(self):
        invalid_options: list[dict] = [
            {"capacity_kwh": float("nan")},
            {"charging_power_kw": 0},
            {"reserve_count": -1},
            {"charger_count": 1.5},
            {"swap_time_minutes": -1},
            {"charging_efficiency": 0},
            {"soc_max": 0.05},
            {"site_load_kw": [250]},
            {"site_load_kw": float("inf")},
            {"scenario": "unknown"},
            {"charging_policy": "unknown"},
        ]
        for options in invalid_options:
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_simulation(**options)


class BatteryTests(unittest.TestCase):
    def test_operating_window_and_grid_efficiency(self):
        battery = Battery(0, 140)
        self.assertAlmostEqual(battery.consume(200), 98)
        self.assertAlmostEqual(battery.soc, 0.1)
        self.assertAlmostEqual(battery.charge(22, 1), 20.24)
        self.assertAlmostEqual(battery.last_grid_energy_kwh, 22)
        self.assertAlmostEqual(battery.soc, 0.1 + 20.24 / 140)
        self.assertAlmostEqual(battery.charge(22, 10), 77.76)
        self.assertAlmostEqual(battery.last_grid_energy_kwh, 77.76 / 0.92)
        self.assertEqual(battery.soc, 0.8)
        self.assertEqual(battery.charge(22, 1), 0)
        self.assertEqual(battery.last_grid_energy_kwh, 0)

    def test_full_recharge_time(self):
        battery = Battery(0, 140, soc=0.1)
        duration = 98 / (22 * 0.92)
        self.assertAlmostEqual(battery.charge(22, duration), 98)
        self.assertAlmostEqual(battery.last_grid_energy_kwh, 98 / 0.92)
        self.assertEqual(battery.soc, 0.8)


class OperationalTests(unittest.TestCase):
    def simulate_one(self, row=None, **options):
        with patch("simulation.load_machine_rows", return_value=[row or machine_row()]):
            return run_simulation(**options)

    def test_exact_25_minute_swap_and_energy_balance(self):
        result = self.simulate_one(reserve_count=1)
        self.assertEqual(len(result.swaps), 1)
        self.assertEqual(result.swaps[0]["time"], "09:00")
        self.assertEqual(result.swap_downtime_minutes, 25)
        self.assertAlmostEqual(result.downtime_minutes, 25)
        self.assertAlmostEqual(result.delivered_energy_kwh, 98 * (2 - 25 / 60))
        self.assertAlmostEqual(result.unmet_energy_kwh, 98 * 25 / 60)
        self.assertEqual(result.active_machine_count[36:39], [0, 0, 1])
        self.assertAlmostEqual(result.grid_charging_energy_kwh, 98 / 0.92)
        self.assertEqual(result.charging_kw[36], 0)  # Removed module is in transit.
        initial_energy = 2 * 140 * 0.8
        final_energy = sum(b.soc * b.capacity_kwh for b in result.batteries)
        self.assertAlmostEqual(
            initial_energy + result.stored_charging_energy_kwh - result.delivered_energy_kwh,
            final_energy,
        )
        self.assertAlmostEqual(sum(result.charging_kw) * 0.25, result.grid_charging_energy_kwh)
        self.assertAlmostEqual(
            result.grid_charging_energy_kwh + result.unreplenished_grid_energy_kwh,
            result.delivered_energy_kwh / 0.92,
        )

    def test_shortage_blocks_work_without_phantom_batteries(self):
        result = self.simulate_one(reserve_count=0)
        self.assertEqual(len(result.swaps), 0)
        self.assertEqual(result.reserve_shortage_events, 1)
        self.assertAlmostEqual(result.reserve_shortage_minutes, 60)
        self.assertAlmostEqual(result.downtime_minutes, 60)
        self.assertAlmostEqual(result.delivered_energy_kwh, 98)
        self.assertEqual(len(result.batteries), 1)
        self.assertEqual(result.grid_charging_energy_kwh, 0)

    def test_no_chargers_and_zero_duration_swaps(self):
        result = self.simulate_one(
            machine_row(hours=4), reserve_count=1, charger_count=0, swap_time_minutes=0
        )
        self.assertEqual(len(result.swaps), 1)
        self.assertAlmostEqual(result.reserve_shortage_minutes, 120)
        self.assertEqual(result.grid_charging_energy_kwh, 0)
        self.assertEqual(result.swap_downtime_minutes, 0)

    def test_fractional_work_and_current_step_count(self):
        result = self.simulate_one(machine_row(hours=1.1), capacity_kwh=1000, reserve_count=0)
        self.assertEqual(result.active_machine_count[31:34], [0, 1, 1])
        self.assertEqual(result.active_machine_count[36:38], [1, 0])
        self.assertAlmostEqual(result.delivered_energy_kwh, 98 * 1.1)
        self.assertAlmostEqual(result.downtime_minutes, 0)

    def test_capacity_parameter_changes_all_modules_and_results(self):
        small = self.simulate_one(capacity_kwh=140, swap_time_minutes=0)
        large = self.simulate_one(capacity_kwh=280, swap_time_minutes=0)
        self.assertEqual(len(small.swaps), 1)
        self.assertEqual(len(large.swaps), 0)
        self.assertTrue(all(b.capacity_kwh == 280 for b in large.batteries))

    def test_fleet_inventory_ports_grid_and_energy(self):
        result = run_simulation(charger_count=2, grid_limit_kw=275)
        self.assertEqual(len(result.machines), 15)
        self.assertTrue(all(sum(snapshot.values()) == 40 for snapshot in result.inventory_history))
        self.assertEqual(len({b.battery_id for b in result.batteries}), 40)
        self.assertLessEqual(max(result.charging_battery_count), 2)
        self.assertLessEqual(result.peak_charging_kw, 25 + 1e-6)
        self.assertLessEqual(result.peak_total_kw, 275 + 1e-6)
        self.assertEqual(result.grid_exceedance_minutes, 0)
        self.assertAlmostEqual(
            result.stored_charging_energy_kwh, result.grid_charging_energy_kwh * 0.92
        )
        self.assertAlmostEqual(
            40 * 140 * 0.8 + result.stored_charging_energy_kwh - result.delivered_energy_kwh,
            sum(b.soc * b.capacity_kwh for b in result.batteries),
        )
        for history in result.soc_history.values():
            self.assertTrue(all(10 - 1e-8 <= value <= 80 + 1e-8 for value in history))

    def test_site_overload_is_reported_not_hidden(self):
        result = self.simulate_one(site_load_kw=1100)
        self.assertEqual(result.grid_charging_energy_kwh, 0)
        self.assertEqual(result.grid_exceedance_minutes, 1440)
        self.assertEqual(result.peak_total_kw, 1100)

    def test_deterministic_seed_independence_and_low_scenario(self):
        first, second = run_simulation(seed=1), run_simulation(seed=999)
        self.assertEqual(first.kpis, second.kpis)
        self.assertEqual(first.swaps, second.swaps)
        low = run_simulation(scenario="low")
        self.assertGreater(low.grid_charging_energy_kwh, 0)
        self.assertLess(low.delivered_energy_kwh, first.delivered_energy_kwh)

    def test_grid_curtailment_exposes_requested_demand_without_overloading(self):
        result = run_simulation(charger_count=22, grid_limit_kw=275)
        self.assertLessEqual(result.peak_total_kw, 275 + 1e-6)
        self.assertGreater(result.peak_requested_total_kw, 275)
        self.assertGreater(result.charging_curtailment_minutes, 0)
        self.assertGreater(result.curtailed_charging_energy_kwh, 0)
        self.assertGreater(result.requested_grid_exceedance_minutes, 0)
        self.assertEqual(result.grid_exceedance_minutes, 0)

    def test_deadline_shortage_at_shift_end_is_reported_even_if_work_loss_matches(self):
        options: dict = {"seed": 168388230, "duty_cycle": DutyCycle()}
        immediate = run_simulation(**options)
        deadline = run_simulation(**options, charging_policy="deadline")
        self.assertGreater(deadline.reserve_shortage_minutes, 0)
        self.assertEqual(immediate.reserve_shortage_minutes, 0)
        # An unavailable reserve can replace time that would already be lost to
        # a late swap. Downtime alone must not hide the operational failure.
        self.assertAlmostEqual(deadline.downtime_minutes, immediate.downtime_minutes)
        self.assertTrue(
            all(sum(snapshot.values()) == 40 for snapshot in deadline.inventory_history)
        )

    def test_upstream_positional_seed_is_preserved(self):
        positional = run_simulation(140, 22, 25, "high", 25, 123, duty_cycle=DutyCycle())
        keyword = run_simulation(seed=123, duty_cycle=DutyCycle())
        self.assertEqual(positional.kpis, keyword.kpis)
        self.assertEqual(positional.swaps, keyword.swaps)


class ChargingTests(unittest.TestCase):
    def test_ports_and_grid_are_hard_limits(self):
        batteries = [Battery(i, 140, soc=0.1) for i in range(4)]
        allocation = allocate_charging(batteries, 2, 22, 30)
        self.assertEqual([power for _, power in allocation], [22, 8])
        self.assertEqual(allocate_charging(batteries, 2, 22, -10), [])

    def test_deadline_smoothing_and_low_reserve_recovery(self):
        empty = Battery(0, 140, soc=0.1)
        partly = Battery(1, 140, soc=0.7)
        allocation = allocate_charging(
            [empty, partly],
            1,
            22,
            750,
            policy="deadline",
            deadlines=[600],
            current_minutes=0,
            reserve_count=0,
            reserve_target=0,
        )
        self.assertIs(allocation[0][0], partly)
        self.assertAlmostEqual(allocation[0][1], 14 / 0.92 / 10)
        urgent = allocate_charging(
            [empty], 1, 22, 750, policy="deadline", reserve_count=0, reserve_target=3
        )
        self.assertEqual(urgent[0][1], 22)


class AnalysisTests(unittest.TestCase):
    def test_correlated_profile_preserves_csv_mean_and_is_seeded(self):
        schedule = create_schedule(8, "high")
        cycle = DutyCycle()
        profile = cycle.profile(schedule, np.random.default_rng(42))
        self.assertEqual(profile, cycle.profile(schedule, np.random.default_rng(42)))
        self.assertAlmostEqual(
            sum(p * active for p, active in zip(profile, schedule)) / sum(schedule), 1
        )
        self.assertGreater(len(set(profile[32:64])), 1)
        self.assertTrue(any(a == b for a, b in zip(profile[32:63], profile[33:64])))

    def test_monte_carlo_is_reproducible_and_has_ordered_quantiles(self):
        first = run_monte_carlo(days=5, seed=123)
        self.assertEqual(first, run_monte_carlo(days=5, seed=123))
        peaks = first["peak_total_kw"]
        self.assertLessEqual(peaks["p50"], peaks["p95"])
        self.assertLessEqual(peaks["p95"], peaks["p99"])
        self.assertEqual(first["probability_grid_exceedance"], 0)
        constrained = run_monte_carlo(days=2, grid_limit_kw=275)
        self.assertEqual(constrained["probability_requested_grid_exceedance"], 1)
        self.assertEqual(constrained["probability_charging_curtailment"], 1)
        self.assertEqual(constrained["probability_grid_exceedance"], 0)
        shortage = run_monte_carlo(days=2, reserve_count=0)
        self.assertEqual(shortage["probability_reserve_shortage"], 1)

    def test_sweep_pool_accounting_and_optional_cost_ranking(self):
        configs = [Infrastructure(140, 40, 22), Infrastructure(200, 30, 22)]
        summary = run_sensitivity(configs, days=2, seed=12)
        self.assertEqual(len(summary["comparisons"]), 2)
        self.assertIsNone(summary["best_configuration"])
        costs = CostAssumptions(1, 1, 0.01, 0.2, 0.1, 10)
        priced = run_sensitivity(configs, days=2, seed=12, costs=costs)
        feasible = [row for row in priced["comparisons"] if row["feasible"]]
        cheapest = min(feasible, key=lambda row: row["daily_cost"])
        self.assertEqual(priced["best_configuration"], cheapest["configuration"])
        with self.assertRaises(ValueError):
            run_sensitivity([Infrastructure(140, 14, 22)], days=1)

    def test_costs_include_energy_left_in_installed_batteries(self):
        costs = CostAssumptions(0, 0, 0, 1, 0, 0)
        summary = {
            "mean_grid_charging_energy_kwh": 100,
            "mean_unreplenished_grid_energy_kwh": 200,
            "peak_total_kw": {"p95": 500},
            "mean_downtime_minutes": 0,
        }
        self.assertEqual(costs.daily_cost(Infrastructure(140, 40, 22), summary), 300)


if __name__ == "__main__":
    unittest.main()
