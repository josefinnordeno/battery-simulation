# Model V2 contract and audit findings

## What was confirmed

The repository at `d3b494c` contains committed conflict markers in `simulation.py`
and README, an undefined `grid_energy` in `Battery.charge`, and a schedule helper
that calls `rng.integers` even when `rng=None`. It cannot execute as checked in.
The audit's older stochastic implementation is visible in the conflicting code,
but its reported 17 swaps / 547 kW cannot be independently reproduced from HEAD.

The CSV already contains the intended inputs: fifteen valid electric replacements,
nine Class A machines (8 high-load hours), three B (4 hours), three C (2 hours),
10–80% SoC, 92% efficiency, 25-minute swaps, 140 kWh modules, 40 total modules,
22 kW per charging module, a 250 kW winter site load, and a 1,000 kW connection.
The 22 **charging positions** are a baseline infrastructure choice matching the
reference maximum, not an explicitly specified installed-charger count in the CSV.
Low-load hours are read directly, including fractional hours such as 4.9.
Mean consumption (including 40.3, 30, and 61.2 kWh/h) is unchanged.

## 1. Spreadsheet regression — `reference.py`

`run_reference_validation()` reads and checks the exported half-hour inventory
and charging snapshots. It computes, rather than copies from the summary:

| KPI | Source replay |
| --- | ---: |
| Swaps | 27 |
| Maximum charging modules | 22 |
| Charging peak | 484 kW |
| Site peak | 734 kW |
| Minimum full reserve | 3 |
| Grid charging energy, 08:00–16:00 | 2,134 kWh |

Inventory transitions and charging/site power must balance. All per-machine event
rows must match their machine's CSV swap count, including repeated machine names;
completion times must match the source's immediate-refill arithmetic, and extra
nonempty event rows are rejected. Returned-module counts must match swap counts.
Charging energy integrates snapshots as left-held intervals; the 16:00 row is the
endpoint, not another interval. Stored energy equals grid energy × efficiency.

**These checks do not validate a physical charging/swapping timeline.** The CSV's
two timelines disagree. At 09:30 the aggregate table has already registered three
swaps, while the first machine-level swaps are at 09:36:05. The aggregate table
reports three completed charges at 14:00, but those batteries' machine-level
completion times are 14:26:36. Machine-level subsequent swap times simply add
`98 / mean_power` hours, without adding the 25-minute swap delay. The replay
exposes cumulative swap/completion-time discrepancies instead of fabricating batteries,
SoC traces, or a physical explanation for the source KPIs.

The unit suite asserts the requested five exact regression values. Changing the
spreadsheet legitimately can require reviewing/updating these regression tests.

## 2. Operational simulation — `simulation.py`, `models.py`

`run_simulation()` is the physical, deterministic default used by the GUI. Its
first six positional parameters on upstream `master` remain available, including
the positional seed. `operator_count` is keyword-only. Changes in default behavior:

- All fifteen selected CSV machines receive schedules; `operator_count=None`
  replaces the unpublished local implementation's implicit cap of ten (upstream
  already schedules all rows). An explicit count schedules the
  first N CSV rows reproducibly; unscheduled machines retain their installed pack.
- Schedules start at 08:00 in both scenarios. No break calendar is encoded in the
  CSV, so none is invented. High-load 8/4/2 hours and fractional low-load hours are
  planned working time inside 08:00–16:00. Downtime reduces delivered work; jobs
  are not extended past their scheduled end.
- Every module, installed and spare, uses `capacity_kwh`. The 140 kWh shared swap
  module is a **system-design assumption**, distinct from the OEM batteries in
  the `Batteri [kWh]` column. The pool is `15 + reserve_count`; the default 25
  spares therefore represent forty total batteries, not forty spares.
- Usable energy is `capacity * (soc_max - soc_min)`: 98 kWh at baseline. Consumption
  is clipped at 10%, charging stops at 80%; there is no uncalibrated CV taper.
- Charger power is grid-side. A full refill requires `98 / 0.92` grid kWh and
  `98 / (22 * 0.92) = 4.841897233` hours. Finishing a charge partway through a
  substep uses only the required grid energy.
- Depleted scheduled machines request a swap. A full spare is taken immediately;
  the machine cannot work for the configured swap duration. Its removed pack is
  available to chargers only after the swap. There is no random break-swap rule.
- With no full spare, machines wait. Failures are counted as shortage episodes,
  aggregate machine-minutes of shortage, lost work/downtime, and unmet energy.
  SoC cannot fall below its minimum and no replacement batteries are created.
- Charging is limited by ports, per-port power, and `max(0, grid_limit - site_load)`.
  If background load alone exceeds the grid limit, the overload is reported and
  charging stops; existing site load is never silently clipped.

Internal steps are one minute, preserving a 25-minute swap rather than rounding
it to 30 minutes. Exhaustion may be detected up to one minute after reaching the
SoC floor. Fractional working minutes and delivered energy are retained. The
trace contains 96 quarter-hour intervals: charging/site power are interval means,
charging counts are interval maxima, reserve counts are interval minima, SoC is
end-of-interval, active-machine counts are start-of-interval working snapshots.
`peak_total_kw` and `peak_charging_kw` use the one-minute power trace and can exceed
the quarter-hour averages plotted in the GUI.

`swap_downtime_minutes` sums nominal swap durations; `downtime_minutes` counts
only unavailable **scheduled** machine-minutes, including shortages and the
sub-minute loss when a battery depletes. Multiple machines' downtime is additive.
`grid_exceedance_minutes` measures minutes above the configured connection limit.
Requested charging is also dispatched without the grid cap for diagnostics only:
`peak_requested_total_kw` and `requested_grid_exceedance_minutes` expose policy
demand that the grid controller suppresses. `charging_curtailment_minutes` and
`curtailed_charging_energy_kwh` integrate suppressed requests on the actual state
trajectory. This is delayed charge demand, not necessarily permanently lost work
or a separate counterfactual unconstrained simulation.
Inventory snapshots include installed, full reserves, swap-transit and charge
queue modules. `batteries` exposes the conserved final pool for energy auditing.
`unreplenished_grid_energy_kwh` is the grid energy still needed at midnight to
restore the entire pool to its initial SoC, including packs left in machines.

Measured deterministic defaults (not regression targets): **25 swaps, 21 charging
modules, 462 kW charging peak, 712 kW site peak, minimum reserve 4**, no reserve
shortage, about 619 scheduled machine-minutes lost. The difference from the source
replay is expected: the source's machine schedule omits swap downtime and its
aggregate charge timeline is separately binned.

The model simulates one initially charged day, including charging after work.
Installed batteries stay installed at shift end. It does not yet model steady-state
multi-day replenishment, shared swap crews/bays, travel logistics, temperature,
price-responsive dispatch, or electrochemistry. Swap crews are implicitly available
per machine. These are model assumptions, not measured operational guarantees.

## 3. Charging policy — `charging.py`

- `immediate`: FIFO queue, fill available ports at full rate within grid headroom.
- `deadline`: predict future shared-module demands from schedules and mean power;
  assign earliest uncovered deadlines to the quickest-to-refill returned modules.
  Spread power over time to those deadlines, with maximum-rate recovery below
  `reserve_target` (default 3). Recompute/preempt each minute. Surplus packs are
  gradually replenished by midnight.

This is a deadline-based heuristic, not a MILP, electricity-price optimizer, or
guaranteed peak reduction. Forecasts ignore future stochastic activity and future
swap delays, so they are intentionally conservative about upcoming demand.
Comparisons must include shortages and downtime, not only peaks. On the current
deterministic default day, deadline dispatch actually raises the peak to 734 kW
and reduces minimum reserve to zero without a shortage: **the published 46%
reduction is not assumed to apply to this site**.

## 4. Uncertainty and infrastructure — `duty_cycle.py`, `scenario_analysis.py`

The optional `DutyCycle` replaces independent Gaussian noise with persistent
idle/light/normal/heavy/travel states. State probabilities, multipliers, and an
80% per-quarter persistence are **illustrative assumptions**, configurable via
the dataclass and not fitted to any cited field dataset. Planned mean consumption
is normalized back to each CSV value for each machine/day. Idle is included in
the planned active schedule; normalization is over fractional scheduled hours.
Consequently Monte Carlo varies activity timing, not planned total daily energy
or attendance. Actual delivered energy changes when downtime interrupts work.

`run_monte_carlo(days=500, seed=42, ...)` generates reproducible independent child
seeds and reports P50/P95/P99 one-minute site peaks, reserve-shortage probability,
grid-limit-exceedance probability, probability of **any individual machine** losing
over 30 scheduled minutes, and mean grid energy/downtime. A grid-constrained model
normally has zero grid-exceedance probability unless background load exceeds the
connection; it does not estimate unconstrained grid demand risk.
The separate requested-peak percentiles, requested-exceedance probability and
charging-curtailment probability expose grid sizing pressure before that cap.
Mean nominal swap durations are reported separately from mean scheduled downtime.

`run_sensitivity()` compares the six audit configurations (70/60/22, 100/45/22,
140/40/22, 200/30/22, 140/40/50, 140/40/100: kWh / total pool / kW per charger).
Common seeds across configurations reduce sampling noise. Charger count defaults
to 22 and is configurable per design. It reports shortage feasibility with a
strict `< 1%` default threshold. No costs or optimal design are invented:
`CostAssumptions` must be supplied to rank feasible designs. Dailyized capital,
mean charging energy plus terminal replenishment, a P95 design-peak tariff, and
machine-hour downtime cost
are summed in the user's consistent currency. This is finite design comparison,
not continuous mathematical optimization. The reliability rule excludes planned
swap downtime; downtime is still reported and priced.

The modeled sample shortage frequency is not a confidence bound. Zero observed
shortages in a small sample is not proof of sub-1% operational failure risk.

### Executed 500-day comparison (seed 42)

| Policy / design | P50 / P95 / P99 site peak (kW) | Days with reserve shortage |
| --- | --- | ---: |
| Immediate, 140 kWh / 40 pool / 22 kW | 668 / 712 / 712 | 0% |
| Deadline, same design | 734 / 734 / 734 | 3.8% |
| Immediate, 70 kWh / 60 pool / 22 kW | 734 / 734 / 734 | 0% |
| Immediate, 100 kWh / 45 pool / 22 kW | 701.2 / 734 / 734 | 0% |
| Immediate, 200 kWh / 30 pool / 22 kW | 580 / 580 / 580 | 72.4% |
| Immediate, 140 kWh / 40 pool / 50 kW | 850 / 950 / 991.4 | 0% |
| Immediate, 140 kWh / 40 pool / 100 kW | 1000 / 1000 / 1000 | 0% |

All designs used 22 charging positions and the 1 MW grid constraint. Every sampled
day had at least one machine lose more than 30 scheduled minutes, including planned
swaps. With the baseline design, the two policies had identical mean downtime
(609.43 machine-minutes): the deadline shortages occurred near job completion,
when an immediate swap would also have interrupted the remaining scheduled work.
Shortage reporting therefore reveals failures that downtime alone can miss.
The smaller 30-module pool's low peak must not be mistaken for adequate service.

## Research interpretation

The audit's research supports leaving mean powers unchanged and investigating
correlated workloads, inventory, and controlled charging. The Volvo L120 product
page was independently checked on 2026-10-08: 282 kWh installed, 268 kWh usable,
5–9 h indicative runtime. That implies roughly 30–54 kWh/h, consistent with
40.3 kWh/h. Its installed battery is not our shared 140 kWh module.

- [Volvo L120 Electric specifications](https://www.volvoce.com/europe/en/products/electric-machines/l120-electric/)
- [Christiaens et al., field-testing electric excavators (audit source)](https://www.mdpi.com/2032-6653/17/2/62)
- [Kuipers & Wolbertus, smart construction-site charging (audit source)](https://evs38-program.org/images/Proceedings/D%20Charging%20Infrastructure%20and%20grid%20integration/148_Smart%20charging%20of%20battery-electric%20construction%20machinery%20at%20construction%20sites%3B%20A%20case%20study%20in%20the%20municipality%20of%20The%20Hague.pdf)
- [Wallander & Márquez-Fernández, swapping research (audit source)](https://www.sciencedirect.com/science/article/pii/S0360544225046237)

The field-study page returned HTTP 403 during this investigation. Its quoted
dataset sizes and the other audit research statistics were not used as calibration
data or numerical guarantees in this implementation.
