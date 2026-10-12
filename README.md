# Battery simulation

A modular 15-minute battery fleet simulation with a Tkinter GUI and Matplotlib charts.

## Run

```powershell
python -m pip install -r requirements.txt
python gui.py
```

The app reads `Beräkningar - Modell.csv` first. It uses rows marked `TRUE`, ignores machines without an electric replacement, and reads each machine's energy consumption and swap-battery size. If that file is absent, it falls back to `Beräkningar_Driftschema.csv` and then to a built-in sample fleet. The source data can use Swedish decimal commas.

The simulation covers 24 hours in 96 consistent 15-minute steps and models:

- explicit Class A/B/C reference work hours for high and low load scenarios;
- individual deterministic daily shifts inside the 07:00-16:00 operating window;
- productive time separate from elapsed shift time, with breaks at 09:00-09:30 and 12:00-12:30;
- a 10% to 80% battery operating window;
- 92% charging efficiency, with grid energy separated from stored energy;
- 25-minute swaps that remove the machine from productive work;
- a finite reserve and charging pool, with 22 kW per occupied charger;
- deterministic baseline behavior controlled by the `seed` argument.

## Scheduling policy

The reference productive-hour definitions are unchanged: Class A requires 8 hours
in the high scenario and 6 hours in the low scenario; Class B requires 4 hours;
and Class C requires 2 hours. Productive slots never overlap either break. A
shift's elapsed window may span a break, but the break does not count toward its
productive-hour total. Every boundary is aligned to the 15-minute simulation
grid and every shift ends by 16:00.

The default `centered` policy chooses the valid shift window whose midpoint is
closest to 11:30. This deterministic policy gives shorter shifts individual
start and end times without introducing probabilistic assumptions. Alternative
policies can be added through `create_daily_schedule(..., policy=...)`.

Because the input data does not provide auxiliary break-load measurements,
`run_simulation` defaults to 15 kW per machine during the elapsed shift window's
break slots. Set `break_idle_power_kw=0` to explicitly model zero break demand,
or provide another value for comparison. Break idle demand never counts as
productive work and does not reduce the remaining productive-step count.

`SimulationResult.schedule_table` contains each machine's start, end, and
productive hours, and the GUI includes a productive schedule plot.

## Build an executable

```powershell
pyinstaller --noconsole --onefile --add-data "Beräkningar_Driftschema.csv;." --name battery-simulation gui.py
```

If the CSV is not present, omit the `--add-data` argument. The executable will still run with the built-in sample fleet.
