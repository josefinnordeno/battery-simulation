from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd


STEPS_PER_HOUR = 4
DAY_START_STEP = 7 * STEPS_PER_HOUR
DAY_END_STEP = 16 * STEPS_PER_HOUR
BREAKS = ((9 * STEPS_PER_HOUR, 9 * STEPS_PER_HOUR + 2), (12 * STEPS_PER_HOUR, 12 * STEPS_PER_HOUR + 2))


@dataclass(frozen=True)
class DailySchedule:
    """A 15-minute schedule separating productive time from elapsed shift time."""

    productive: list[bool]
    shift_window: list[bool]
    start_step: int
    end_step: int
    required_productive_steps: int
    machine_id: str | None = None

    @property
    def start_label(self) -> str:
        return _step_label(self.start_step)

    @property
    def end_label(self) -> str:
        return _step_label(self.end_step)


DEFAULT_MACHINES = [
    ("Volvo L120H", "Lastmaskin", 1512, 120.0),
    ("Volvo EWR150E", "Gravmaskin", 1261, 92.0),
    ("Volvo EWR150E", "Gravmaskin", 1218, 92.0),
    ("Volvo EC140DL", "Gravmaskin", 961, 72.0),
    ("Volvo EC300E", "Gravmaskin", 137, 145.0),
]


def _number(value, default=0.0) -> float:
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def load_machine_rows(csv_path: str | Path | None = None) -> list[dict]:
    if csv_path is None:
        model_path = Path("Beräkningar - Modell.csv")
        csv_path = model_path if model_path.exists() else Path("Beräkningar_Driftschema.csv")
    path = Path(csv_path)
    if not path.exists():
        return [
            {
            "machine_id": f"machine-{index + 1}",
                "name": name,
                "type": kind,
                "annual_hours": hours,
                "average_power_kw": power,
                "battery_capacity_kwh": 140.0,
            }
            for index, (name, kind, hours, power) in enumerate(DEFAULT_MACHINES)
        ]

    read_options = {"skiprows": 3} if path.name == "Beräkningar - Modell.csv" else {}
    frame = pd.read_csv(path, encoding="utf-8-sig", **read_options)
    frame.columns = [str(column).strip() for column in frame.columns]
    if "Valbara maskiner" in frame.columns:
        return _load_model_rows(frame)

    required = {"Maskin", "Typ", "Drift/år (h)"}
    if not required.issubset(frame.columns):
        raise ValueError(f"CSV saknar kolumner: {', '.join(sorted(required - set(frame.columns)))}")

    rows = []
    for index, (_, row) in enumerate(frame.iterrows()):
        annual_hours = _number(row["Drift/år (h)"])
        if annual_hours <= 0:
            continue
        rows.append(
            {
                "name": str(row["Maskin"]),
                "machine_id": f"machine-{index + 1}",
                "type": str(row["Typ"]),
                "annual_hours": annual_hours,
                "average_power_kw": _estimate_power(str(row["Typ"])),
                "battery_capacity_kwh": 140.0,
            }
        )
    return rows or load_machine_rows(Path("missing.csv"))


def _load_model_rows(frame: pd.DataFrame) -> list[dict]:
    """Read the machine table in Beräkningar - Modell.csv."""
    rows = []
    for index, (_, row) in enumerate(frame.iterrows()):
        selected = str(row.get("Valbara maskiner", "")).strip().lower() in {"true", "1", "ja"}
        replacement = str(row.get("Elersättare", "")).strip()
        annual_hours = _number(row.get("Arbetstimmar"))
        consumption = _number(row.get("Energiförbruktning [kWh/h]"))
        battery_capacity = _number(row.get("Swap-Batteri [kWh]"), 140.0)
        if not selected or annual_hours <= 0 or replacement in {"", "-", "nan"} or consumption <= 0:
            continue
        rows.append(
            {
                "name": str(row["Maskiner"]).strip(),
                "machine_id": f"machine-{index + 1}",
                "type": str(row["Typ"]).strip(),
                "machine_class": str(row.get("klass", "A")).strip().upper(),
                "annual_hours": annual_hours,
                "low_load_hours": _number(row.get("Låg belastning")),
                "high_load_hours": _number(row.get("Hög belastning")),
                "average_power_kw": consumption,
                "battery_capacity_kwh": battery_capacity,
            }
        )
    return rows or load_machine_rows(Path("missing.csv"))


def _estimate_power(machine_type: str) -> float:
    normalized = machine_type.lower()
    if "last" in normalized:
        return 120.0
    if "truck" in normalized:
        return 180.0
    if "service" in normalized:
        return 45.0
    return 90.0


def create_schedule(
    annual_hours: float,
    scenario: str,
    rng: np.random.Generator | None = None,
    machine_class: str = "A",
) -> list[bool]:
    """Return the unchanged fixed-block reference mask.

    This compatibility function intentionally does not use the new operating
    schedule policies. The reference model starts at 08:00 and is retained so
    its outputs can be compared with the explicit daily schedules.
    """
    return create_reference_schedule(annual_hours, scenario, machine_class)


def create_reference_schedule(
    annual_hours: float,
    scenario: str,
    machine_class: str = "A",
) -> list[bool]:
    """Create the original reference workday: one fixed block from 08:00."""
    required_steps = _required_productive_steps(annual_hours, scenario, machine_class)
    schedule = np.zeros(96, dtype=bool)
    schedule[32 : 32 + required_steps] = True
    return schedule.tolist()


def create_daily_schedule(
    annual_hours: float,
    scenario: str,
    machine_class: str = "A",
    policy: str = "centered",
    machine_id: str | None = None,
    daily_hours: float | None = None,
) -> DailySchedule:
    """Create a deterministic shift within 07:00-16:00.

    The default ``centered`` policy chooses the valid 15-minute shift window
    whose midpoint is closest to 11:30. Breaks remain elapsed shift time but
    are excluded from productive slots. This avoids starting every short
    shift at 07:00 while remaining reproducible and configurable by policy.
    """
    required_steps = _required_productive_steps(annual_hours, scenario, machine_class, daily_hours)
    if policy == "reference":
        reference = create_reference_schedule(annual_hours, scenario, machine_class)
        end_step = 32 + required_steps
        return DailySchedule(reference, reference.copy(), 32, end_step, required_steps, machine_id)
    if policy not in {"centered", "staggered"}:
        raise ValueError(f"Unknown scheduling policy: {policy}")
    if required_steps == 0:
        empty = [False] * 96
        return DailySchedule(empty, empty.copy(), DAY_START_STEP, DAY_START_STEP, 0, machine_id)

    candidates = _schedule_candidates(required_steps)
    if not candidates:
        raise ValueError(f"{required_steps / STEPS_PER_HOUR} productive hours do not fit in the operating window")

    if policy == "centered":
        candidate = min(candidates, key=lambda item: (abs(item[0] - 46), item[1]))
    else:
        rank = _stable_identifier_rank(machine_id or "machine-1")
        ordered = sorted(candidates, key=lambda item: (abs(item[0] - 46), item[1]))
        candidate = ordered[rank % len(ordered)]
    return _schedule_from_candidate(candidate, required_steps, machine_id)


def create_fleet_schedule(
    machine_rows: list[dict],
    scenario: str,
    policy: str = "staggered",
) -> dict[str, DailySchedule]:
    """Assign deterministic schedules to a fleet by stable machine ID.

    ``staggered`` selects different centered candidate windows for machines
    with equal productive-hour requirements where enough valid windows exist.
    It is a modelling assumption for comparing fleet timing effects, not a
    claim about actual construction-site behavior. ``centered`` and
    ``reference`` remain available as comparison policies.
    """
    if policy not in {"reference", "centered", "staggered"}:
        raise ValueError(f"Unknown scheduling policy: {policy}")

    identified_rows = [(_machine_id(row, index), row) for index, row in enumerate(machine_rows)]
    if len({machine_id for machine_id, _ in identified_rows}) != len(identified_rows):
        raise ValueError("Machine identifiers must be unique within a fleet")
    schedules = {}
    if policy != "staggered":
        for machine_id, row in identified_rows:
            daily_hours = None if policy == "reference" else _row_daily_hours(row, scenario)
            schedules[machine_id] = create_daily_schedule(
                row["annual_hours"], scenario, row.get("machine_class", "A"), policy, machine_id, daily_hours
            )
        return schedules

    groups = {}
    for machine_id, row in identified_rows:
        required_steps = _row_required_productive_steps(row, scenario)
        groups.setdefault(required_steps, []).append((machine_id, row))
    used_starts = set()
    for required_steps, rows in groups.items():
        candidates = sorted(_schedule_candidates(required_steps), key=lambda item: (abs(item[0] - 46), item[1]))
        for machine_id, row in sorted(rows, key=lambda item: item[0]):
            candidate = next((item for item in candidates if item[1] not in used_starts), candidates[0])
            used_starts.add(candidate[1])
            schedules[machine_id] = _schedule_from_candidate(candidate, required_steps, machine_id)
    return schedules


def _required_productive_steps(
    annual_hours: float,
    scenario: str,
    machine_class: str,
    daily_hours: float | None = None,
) -> int:
    reference_hours = {
        "A": {"high": 8.0, "low": 6.0},
        "B": {"high": 4.0, "low": 4.0},
        "C": {"high": 2.0, "low": 2.0},
    }
    hours = daily_hours
    if hours is None:
        hours = reference_hours.get(machine_class, reference_hours["A"]).get(scenario, 0.0)
    return round(hours * STEPS_PER_HOUR)


def _row_daily_hours(row: dict, scenario: str) -> float | None:
    value = row.get(f"{scenario}_load_hours")
    return value if isinstance(value, (int, float)) and value > 0 else None


def _row_required_productive_steps(row: dict, scenario: str) -> int:
    return _required_productive_steps(
        row["annual_hours"], scenario, row.get("machine_class", "A"), _row_daily_hours(row, scenario)
    )


def _schedule_candidates(required_steps: int) -> list[tuple[float, int, int, list[int]]]:
    candidates = []
    for start_step in range(DAY_START_STEP, DAY_END_STEP):
        if _is_break_step(start_step):
            continue
        for end_step in range(start_step + 1, DAY_END_STEP + 1):
            productive_steps = [step for step in range(start_step, end_step) if not _is_break_step(step)]
            if len(productive_steps) == required_steps:
                candidates.append(((start_step + end_step) / 2, start_step, end_step, productive_steps))
                break
            if len(productive_steps) > required_steps:
                break
    return candidates


def _schedule_from_candidate(candidate, required_steps: int, machine_id: str | None) -> DailySchedule:
    _, start_step, end_step, productive_steps = candidate
    productive = [False] * 96
    for step in productive_steps:
        productive[step] = True
    shift_window = [False] * 96
    for step in range(start_step, end_step):
        shift_window[step] = True
    return DailySchedule(productive, shift_window, start_step, end_step, required_steps, machine_id)


def _machine_id(row: dict, index: int) -> str:
    return str(row.get("machine_id") or f"{row.get('name', 'machine')}-{index + 1}")


def _stable_identifier_rank(machine_id: str) -> int:
    return sum((index + 1) * ord(character) for index, character in enumerate(machine_id))


def _is_break_step(step: int) -> bool:
    return any(start <= step < end for start, end in BREAKS)


def _step_label(step: int) -> str:
    hour, quarter = divmod(step, STEPS_PER_HOUR)
    return f"{hour:02d}:{quarter * 15:02d}"


def background_load(scenario: str) -> np.ndarray:
    time = np.arange(96) / 4.0
    if scenario == "high":
        return np.full(96, 250.0)
    base, peak, center = 48.0, 48.0, 13.0
    morning = 10.0 * np.exp(-0.5 * ((time - 8.0) / 2.0) ** 2)
    afternoon = peak * np.exp(-0.5 * ((time - center) / 4.5) ** 2)
    return base + morning + afternoon


def time_labels() -> list[str]:
    return [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)]
