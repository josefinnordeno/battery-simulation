from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def render_result(parent, result) -> FigureCanvasTkAgg:
    for child in parent.winfo_children():
        child.destroy()

    figure, axes = plt.subplots(4, 1, figsize=(9, 10), sharex=True, constrained_layout=True)
    figure.patch.set_facecolor("#f6f3ed")
    for axis in axes:
        axis.set_facecolor("#f6f3ed")
        axis.grid(alpha=0.2)

    axes[0].step(result.labels, result.active_machine_count, where="mid", color="#0d6e6e", linewidth=2)
    axes[0].set_ylabel("Maskiner aktiva")
    axes[0].set_title("Driftschema och batteribyten")
    for swap in result.swaps:
        axes[0].axvline(swap["time"], color="#d96c4f", alpha=0.25)
    axes[0].text(0.01, 0.86, f"{len(result.swaps)} byten", transform=axes[0].transAxes, color="#d96c4f")

    for machine in result.machines:
        axes[1].step(result.labels, [int(active) for active in machine.schedule], where="post", linewidth=1.2, label=machine.name)
    axes[1].set_ylabel("Produktiv")
    axes[1].set_yticks([0, 1], ["Nej", "Ja"])
    axes[1].set_title("Maskinernas produktiva arbetsschema")
    if len(result.machines) <= 10:
        axes[1].legend(ncol=2, fontsize=7, loc="upper right")

    for machine_index, values in result.soc_history.items():
        axes[2].plot(result.labels, values, linewidth=1.3, alpha=0.75, label=f"Maskin {machine_index + 1}")
    axes[2].axhline(10, color="#d96c4f", linestyle="--", linewidth=1)
    axes[2].set_ylabel("SoC (%)")
    axes[2].set_ylim(0, 105)
    axes[2].set_title("Batteriernas laddnivå")
    if len(result.soc_history) <= 10:
        axes[2].legend(ncol=2, fontsize=8, loc="lower left")

    axes[3].stackplot(result.labels, result.background_kw, result.charging_kw, labels=["Baslast", "Laddning"], colors=["#244653", "#e2a33b"], alpha=0.9)
    axes[3].set_ylabel("kW")
    axes[3].set_title("Anläggningens totala effektbehov")
    axes[3].legend(loc="upper left")
    axes[3].tick_params(axis="x", rotation=45)

    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
    return canvas
