from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from simulation import run_simulation
from visualization import render_result


class SimulationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Battery simulation")
        self.geometry("1280x860")
        self.minsize(900, 650)
        self.configure(bg="#f6f3ed")
        self._build_ui()

    def _build_ui(self):
        controls = ttk.Frame(self, padding=18)
        controls.pack(side="left", fill="y")
        output = ttk.Frame(self, padding=(0, 18, 18, 18))
        output.pack(side="right", fill="both", expand=True)
        self.output = output

        ttk.Label(controls, text="BATTERY SIMULATION", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 22))
        self.capacity = self._field(controls, "Batterikapacitet (kWh)", "140")
        self.power = self._field(controls, "Laddningseffekt per batteri (kW)", "22")
        self.swap_time = self._field(controls, "Bytestid (minuter)", "15")
        ttk.Label(controls, text="Belastningsscenario").pack(anchor="w", pady=(18, 5))
        self.scenario = tk.StringVar(value="high")
        ttk.Radiobutton(controls, text="Hög belastning / vinter", variable=self.scenario, value="high").pack(anchor="w")
        ttk.Radiobutton(controls, text="Låg belastning / sommar", variable=self.scenario, value="low").pack(anchor="w")
        ttk.Button(controls, text="Kör simulering", command=self._run).pack(fill="x", pady=(28, 0))
        self.status = ttk.Label(controls, text="Redo", wraplength=190)
        self.status.pack(anchor="w", pady=16)
        ttk.Label(output, text="Resultat", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(output, text="Kör simuleringen för att visa schema, SoC och effektuttag.").pack(anchor="w", pady=(0, 8))

    @staticmethod
    def _field(parent, label, default):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 4))
        value = tk.StringVar(value=default)
        ttk.Entry(parent, textvariable=value, width=22).pack(anchor="w")
        return value

    def _run(self):
        try:
            result = run_simulation(float(self.capacity.get()), float(self.power.get()), int(self.swap_time.get()), self.scenario.get())
        except (TypeError, ValueError) as error:
            messagebox.showerror("Ogiltiga parametrar", str(error))
            return
        render_result(self.output, result)
        peak = max(result.total_kw)
        self.status.configure(text=f"Klar. Topp: {peak:.0f} kW | Byten: {len(result.swaps)}")


def main():
    SimulationApp().mainloop()


if __name__ == "__main__":
    main()
