# Battery simulation

A modular 15-minute battery fleet simulation with a Tkinter GUI and Matplotlib charts.

## Run

```powershell
python -m pip install -r requirements.txt
python gui.py
```

The app reads `Beräkningar - Modell.csv` first. It uses rows marked `TRUE`, ignores machines without an electric replacement, and reads each machine's energy consumption and swap-battery size. If that file is absent, it falls back to `Beräkningar_Driftschema.csv` and then to a built-in sample fleet. The source data can use Swedish decimal commas.

The simulation covers 24 hours in 96 steps and models:

- variable machine demand using a seeded normal distribution;
- CC/CV charging, with tapering above 80% SoC;
- battery swaps at low SoC and during break windows;
- background load for winter/high and summer/low scenarios;
- 22 kW charging per battery, aggregated across simultaneously charging batteries.

## Build an executable

```powershell
pyinstaller --noconsole --onefile --add-data "Beräkningar_Driftschema.csv;." --name battery-simulation gui.py
```

If the CSV is not present, omit the `--add-data` argument. The executable will still run with the built-in sample fleet.
