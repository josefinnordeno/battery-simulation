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
                "name": name,
                "type": kind,
                "annual_hours": hours,
                "average_power_kw": power,
                "battery_capacity_kwh": 140.0,
            }
            for name, kind, hours, power in DEFAULT_MACHINES
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
    for _, row in frame.iterrows():
        annual_hours = _number(row["Drift/år (h)"])
        if annual_hours <= 0:
            continue
        rows.append(
            {
                "name": str(row["Maskin"]),
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
    for _, row in frame.iterrows():
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
                "type": str(row["Typ"]).strip(),
                "machine_class": str(row.get("klass", "A")).strip().upper(),
                "annual_hours": annual_hours,
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
    """Return the productive mask for the reference workday."""
    return create_daily_schedule(annual_hours, scenario, machine_class).productive


def create_daily_schedule(
    annual_hours: float,
    scenario: str,
    machine_class: str = "A",
    policy: str = "centered",
) -> DailySchedule:
    """Create a deterministic shift within 07:00-16:00.

    The default ``centered`` policy chooses the valid 15-minute shift window
    whose midpoint is closest to 11:30. Breaks remain elapsed shift time but
    are excluded from productive slots. This avoids starting every short
    shift at 07:00 while remaining reproducible and configurable by policy.
    """
    reference_hours = {
        "A": {"high": 8.0, "low": 6.0},
        "B": {"high": 4.0, "low": 4.0},
        "C": {"high": 2.0, "low": 2.0},
    }
    daily_hours = reference_hours.get(machine_class, reference_hours["A"]).get(scenario, 0.0)
    required_steps = round(daily_hours * STEPS_PER_HOUR)
    if policy != "centered":
        raise ValueError(f"Unknown scheduling policy: {policy}")
    if required_steps == 0:
        empty = [False] * 96
        return DailySchedule(empty, empty.copy(), DAY_START_STEP, DAY_START_STEP, 0)

    candidates = []
    for start_step in range(DAY_START_STEP, DAY_END_STEP):
        if _is_break_step(start_step):
            continue
        for end_step in range(start_step + 1, DAY_END_STEP + 1):
            productive_steps = [
                step for step in range(start_step, end_step)
                if not _is_break_step(step)
            ]
            if len(productive_steps) == required_steps:
                midpoint = (start_step + end_step) / 2
                candidates.append((abs(midpoint - 46), start_step, end_step, productive_steps))
                break
            if len(productive_steps) > required_steps:
                break
    if not candidates:
        raise ValueError(f"{daily_hours} productive hours do not fit in the operating window")

    _, start_step, end_step, productive_steps = min(candidates, key=lambda item: (item[0], item[1]))
    productive = [False] * 96
    for step in productive_steps:
        productive[step] = True
    shift_window = [False] * 96
    for step in range(start_step, end_step):
        shift_window[step] = True
    return DailySchedule(productive, shift_window, start_step, end_step, required_steps)


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
