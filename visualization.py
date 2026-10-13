from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def render_result(parent, result) -> FigureCanvasTkAgg:
    for child in parent.winfo_children():
        child.destroy()

    figure = plt.figure(figsize=(10, 11), constrained_layout=True)
    grid = figure.add_gridspec(4, 1, height_ratios=[1.4, 1.2, 1.4, 0.9])
    axes = [figure.add_subplot(grid[index]) for index in range(4)]
    figure.patch.set_facecolor("#f6f3ed")
    for axis in axes:
        axis.set_facecolor("#f6f3ed")
        axis.grid(alpha=0.2)

    time = np.arange(len(result.labels))
    for row_index, machine in enumerate(result.machines):
        productive_steps = np.flatnonzero(machine.schedule)
        productive_groups = np.split(productive_steps, np.where(np.diff(productive_steps) > 1)[0] + 1)
        for group in productive_groups:
            if group.size:
                axes[0].barh(row_index, group.size, left=group[0], height=0.55, color="#0d6e6e", label="Produktiv tid" if row_index == 0 else None)
        shift_steps = np.flatnonzero(machine.shift_window)
        if shift_steps.size:
            axes[0].plot([shift_steps[0], shift_steps[-1] + 1], [row_index, row_index], color="#e2a33b", linewidth=7, alpha=0.35, solid_capstyle="butt", label="Skiftfönster" if row_index == 0 else None)
    axes[0].set_yticks(range(len(result.machines)), [machine.name for machine in result.machines])
    axes[0].set_ylabel("Fordon")
    axes[0].set_title("Körschema")
    axes[0].invert_yaxis()
    for swap in result.swaps:
        axes[0].axvline(result.labels.index(swap["time"]), color="#d96c4f", alpha=0.35, linewidth=1)
    axes[0].plot([], [], color="#d96c4f", label="Batteribyte")

    axes[1].stackplot(time, result.background_kw, result.charging_kw, labels=["Baslast", "Laddning"], colors=["#244653", "#e2a33b"], alpha=0.9)
    axes[1].set_ylabel("Effekt (kW)")
    axes[1].set_title("Total elförbrukning över tid")
    axes[1].legend(loc="upper left")

    for machine_index, values in result.soc_history.items():
        axes[2].plot(time, values, linewidth=1.3, alpha=0.8, label=result.machines[machine_index].name)
    axes[2].axhline(result.min_soc_percent, color="#d96c4f", linestyle="--", linewidth=1, label="Min SOC")
    axes[2].axhline(result.max_soc_percent, color="#e2a33b", linestyle="--", linewidth=1, label="Max SOC")
    axes[2].set_ylabel("SoC (%)")
    axes[2].set_ylim(0, 105)
    axes[2].set_title("Batteriernas laddnivå")

    total_energy_kwh = sum(result.total_kw) * 0.25
    axes[3].axis("off")
    axes[3].set_title("Nyckeltal", loc="left")
    kpis = [
        ("Total energiförbrukning", f"{total_energy_kwh:,.0f} kWh"),
        ("Högsta effekttopp", f"{result.peak_total_site_load_kw:,.0f} kW"),
        ("Antal batteribyten", f"{len(result.swaps)}"),
        ("Antal batterier totalt", f"{result.total_battery_count}"),
    ]
    axes[3].table(
        cellText=[[label, value] for label, value in kpis],
        colLabels=["Mått", "Värde"],
        colWidths=[0.55, 0.25],
        cellLoc="left",
        loc="center",
    ).scale(1, 1.35)

    for axis in axes[:3]:
        axis.set_xlim(0, len(result.labels) - 1)
        tick_positions = np.arange(0, len(result.labels), 4)
        axis.set_xticks(tick_positions)
        axis.set_xticklabels([result.labels[index] for index in tick_positions], rotation=45, ha="right")

    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
    return canvas
