"""Spreadsheet regression, deliberately separate from the operational model."""

from dataclasses import dataclass
from pathlib import Path

from data_loader import load_machine_rows, load_reference_calculations


def time_minutes(value: str) -> float:
    hour, minute, second = (float(part) for part in value.split("."))
    return hour * 60 + minute + second / 60


@dataclass
class ReferenceResult:
    hourly: list[dict]
    swaps: list[dict]
    grid_charging_energy_kwh: float
    stored_charging_energy_kwh: float
    charge_time_hours: float
    discrepancies: list[str]

    @property
    def kpis(self) -> dict:
        return {
            "swaps": sum(row["swaps"] for row in self.hourly),
            "max_simultaneous_charging": max(row["modules_charging"] for row in self.hourly),
            "peak_charging_kw": max(row["charging_kw"] for row in self.hourly),
            "peak_total_kw": max(row["total_kw"] for row in self.hourly),
            "minimum_reserve": min(row["reserve_batteries"] for row in self.hourly),
        }


def run_reference_validation(csv_path: str | Path | None = None) -> ReferenceResult:
    """Replay source snapshots and validate their internal accounting.

    These are spreadsheet-derived KPIs, not a physical validation of the swap
    schedule. Mismatches between its two time tables are reported explicitly.
    """
    data = load_reference_calculations(csv_path)
    rows = load_machine_rows(csv_path)
    parameters = data["parameters"]
    efficiency = parameters["Laddningsverkningsgrad"]
    power = parameters["Laddningseffekt per batteri [kW]"]
    capacity = parameters["Batteri storlek"]
    usable = capacity * (parameters["SOC max"] - parameters["SOC min"])
    hourly = data["hourly"]
    if not hourly or not 0 < efficiency <= 1 or power <= 0 or usable <= 0:
        raise ValueError("Invalid reference charging inputs")
    events_by_name: dict[str, list[dict]] = {}
    for event in data["swap_events"]:
        events_by_name.setdefault(event["machine"], []).append(event)
    swaps = []
    for index, row in enumerate(rows):
        candidates = events_by_name.get(row["name"], [])
        if not candidates:
            raise ValueError(f"Missing reference events for {row['name']}")
        event = candidates.pop(0)
        if len(event["times"]) != row["reference_swap_count"] or len(
            event["finished_times"]
        ) != len(event["times"]):
            raise ValueError(f"Reference swap count mismatch for machine {index}")
        for start, finish in zip(event["times"], event["finished_times"]):
            # Source completion times assume an immediate full-window refill;
            # this validates the source arithmetic, not physical swap logistics.
            expected_minutes = usable / (power * efficiency) * 60
            if abs(time_minutes(finish) - time_minutes(start) - expected_minutes) > 1 / 30:
                raise ValueError(f"Reference completion time mismatch for machine {index}")
        swaps.extend(
            {"machine_index": index, "machine": row["name"], "time": time}
            for time in event["times"]
        )
    if len(swaps) != sum(row["swaps"] for row in hourly):
        raise ValueError("Reference event and aggregate swap counts differ")
    if any(
        event["times"] or event["finished_times"]
        for events in events_by_name.values()
        for event in events
    ):
        raise ValueError("Unmatched nonempty reference event rows")

    reserve = hourly[0]["reserve_batteries"] - hourly[0]["finished_batteries"] + hourly[0]["swaps"]
    charging = 0
    grid_energy = 0.0
    for index, row in enumerate(hourly):
        charging += row["swaps"] - row["finished_batteries"]
        reserve += row["finished_batteries"] - row["swaps"]
        if row["modules_to_charge"] != row["swaps"]:
            raise ValueError(f"Reference returned-module mismatch at {row['time']}")
        if charging != row["modules_charging"] or reserve != row["reserve_batteries"]:
            raise ValueError(f"Reference inventory mismatch at {row['time']}")
        if abs(row["charging_kw"] - charging * power) > 1e-6:
            raise ValueError(f"Reference charging power mismatch at {row['time']}")
        if abs(row["total_kw"] - row["background_kw"] - row["charging_kw"]) > 1e-6:
            raise ValueError(f"Reference site power mismatch at {row['time']}")
        if index + 1 < len(hourly):
            hours = (time_minutes(hourly[index + 1]["time"]) - time_minutes(row["time"])) / 60
            grid_energy += row["charging_kw"] * hours

    discrepancies = []
    for row in hourly:
        snapshot_time = time_minutes(row["time"])
        aggregate_swaps = sum(
            r["swaps"] for r in hourly if time_minutes(r["time"]) <= snapshot_time
        )
        timed_swaps = sum(time_minutes(event["time"]) <= snapshot_time for event in swaps)
        if aggregate_swaps != timed_swaps:
            discrepancies.append(
                f"{row['time']}: aggregate swaps={aggregate_swaps}, timed swaps={timed_swaps}"
            )
        aggregate_finished = sum(
            r["finished_batteries"] for r in hourly if time_minutes(r["time"]) <= snapshot_time
        )
        timed_finished = sum(
            time_minutes(time) <= snapshot_time
            for event in data["swap_events"]
            for time in event["finished_times"]
        )
        if aggregate_finished != timed_finished:
            discrepancies.append(
                f"{row['time']}: aggregate completions={aggregate_finished}, timed completions={timed_finished}"
            )
    return ReferenceResult(
        hourly,
        swaps,
        grid_energy,
        grid_energy * efficiency,
        usable / (power * efficiency),
        discrepancies,
    )
