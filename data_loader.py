from __future__ import annotations

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
    """Create the fixed reference workday for machine classes A, B and C."""
    reference_hours = {
        "A": {"high": 8.0, "low": 6.0},
        "B": {"high": 4.0, "low": 4.0},
        "C": {"high": 2.0, "low": 2.0},
    }
    daily_hours = reference_hours.get(machine_class, reference_hours["A"]).get(scenario, 0.0)
    active_steps = round(daily_hours / 0.25)
    schedule = np.zeros(96, dtype=bool)
    start = 32
    schedule[start : start + active_steps] = True
    return schedule.tolist()


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
