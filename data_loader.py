from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_MACHINES = [
    ("Volvo L120H", "Lastmaskin", 1512, 120.0),
    ("Volvo EWR150E", "Gravmaskin", 1261, 92.0),
    ("Volvo EWR150E", "Gravmaskin", 1218, 92.0),
    ("Volvo EC140DL", "Gravmaskin", 961, 72.0),
    ("Volvo EC300E", "Gravmaskin", 137, 145.0),
]

MODEL_PATH = Path(__file__).with_name("Beräkningar - Modell.csv")


def _number(value, default=0.0) -> float:
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
        return number if np.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def load_machine_rows(csv_path: str | Path | None = None) -> list[dict]:
    if csv_path is None:
        csv_path = (
            MODEL_PATH
            if MODEL_PATH.exists()
            else MODEL_PATH.with_name("Beräkningar_Driftschema.csv")
        )
    path = Path(csv_path)
    if not path.exists():
        return [
            {
                "name": name,
                "type": kind,
                "annual_hours": hours,
                "average_power_kw": power,
                "battery_capacity_kwh": 140.0,
                "class_code": "A",
                "low_daily_hours": 6.0,
                "high_daily_hours": 8.0,
            }
            for name, kind, hours, power in DEFAULT_MACHINES
        ]

    with path.open(encoding="utf-8-sig", newline="") as stream:
        first_rows = list(csv.reader(stream))[:4]
    skiprows = 3 if any("Valbara maskiner" in row for row in first_rows) else 0
    frame = pd.read_csv(path, encoding="utf-8-sig", skiprows=skiprows)
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
                "class_code": "A",
                "low_daily_hours": min(6.0, annual_hours / 250.0),
                "high_daily_hours": min(8.0, annual_hours / 250.0),
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
        class_code = str(row.get("klass", "A")).strip() or "A"
        low_daily_hours = _number(row.get("Låg belastning"), annual_hours / 250.0)
        high_daily_hours = _number(row.get("Hög belastning"), annual_hours / 250.0)
        reference_swap_count = int(_number(row.get("Batteribyten hög [st/dag]")))
        if not selected or annual_hours <= 0 or replacement in {"", "-", "nan"} or consumption <= 0:
            continue
        rows.append(
            {
                "name": str(row["Maskiner"]).strip(),
                "type": str(row["Typ"]).strip(),
                "annual_hours": annual_hours,
                "average_power_kw": consumption,
                "battery_capacity_kwh": battery_capacity,
                "class_code": class_code,
                "low_daily_hours": low_daily_hours,
                "high_daily_hours": high_daily_hours,
                "reference_swap_count": reference_swap_count,
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
    daily_hours: float, scenario: str, rng: np.random.Generator | None = None
) -> list[float]:
    """Work from 08:00; preserve fractional CSV hours in the final interval.

    The spreadsheet supplies no break calendar. Both scenarios use its 08:00
    start; daily_hours is a scenario input, never inferred here from annual hours.
    The unused rng argument is retained for callers of the previous API.
    """
    if scenario not in {"high", "low"} or not np.isfinite(daily_hours) or not 0 <= daily_hours <= 8:
        raise ValueError("Expected high/low scenario and daily_hours in [0, 8]")
    schedule = np.zeros(96, dtype=float)
    remaining = daily_hours * 4
    for step in range(32, 64):
        schedule[step] = min(1.0, max(0.0, remaining))
        remaining -= schedule[step]
    return schedule.tolist()


def load_reference_calculations(csv_path: str | Path | None = None) -> dict:
    """Read the deterministic reference blocks from the spreadsheet export."""
    path = Path(csv_path) if csv_path is not None else MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"Reference CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        raw_rows = list(csv.reader(stream))

    hourly_start = next(
        index for index, row in enumerate(raw_rows) if len(row) > 1 and row[1] == "Column 11"
    )
    hourly = []
    for row in raw_rows[hourly_start + 1 :]:
        if len(row) < 11 or not row[2].strip():
            if hourly:
                break
            continue
        hourly.append(
            {
                "time": row[2].strip(),
                "swaps": int(_number(row[3])),
                "finished_batteries": int(_number(row[4])),
                "modules_to_charge": int(_number(row[5])),
                "modules_charging": int(_number(row[6])),
                "charging_kw": _number(row[7]),
                "background_kw": _number(row[8]),
                "total_kw": _number(row[9]),
                "margin_kw": _number(row[10]),
                "reserve_batteries": int(_number(row[20])) if len(row) > 20 else 0,
            }
        )

    event_start = next(
        index for index, row in enumerate(raw_rows) if len(row) > 1 and row[1] == "Column 10"
    )
    swap_events = []
    for row in raw_rows[event_start + 1 :]:
        if len(row) < 4 or not row[2].strip():
            continue
        times = [value.strip() for value in row[5:11] if value.strip()]
        swap_events.append(
            {
                "machine": row[2].strip(),
                "times": times,
                "finished_times": [v.strip() for v in row[13:19] if v.strip()],
            }
        )

    parameters = {row[2].strip(): _number(row[3]) for row in raw_rows[26:39] if row[2].strip()}
    summary = {row[13].strip(): _number(row[14]) for row in raw_rows[42:59] if row[13].strip()}
    return {
        "hourly": hourly,
        "swap_events": swap_events,
        "parameters": parameters,
        "summary": summary,
    }


def background_load(scenario: str) -> np.ndarray:
    time = np.arange(96) / 4.0
    if scenario == "high":
        base, peak, center = 145.0, 105.0, 13.0
        morning = 24.0 * np.exp(-0.5 * ((time - 8.0) / 1.8) ** 2)
        afternoon = peak * np.exp(-0.5 * ((time - center) / 4.0) ** 2)
        return base + morning + afternoon
    base, peak, center = 48.0, 48.0, 13.0
    morning = 10.0 * np.exp(-0.5 * ((time - 8.0) / 2.0) ** 2)
    afternoon = peak * np.exp(-0.5 * ((time - center) / 4.5) ** 2)
    return base + morning + afternoon


def time_labels() -> list[str]:
    return [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)]
