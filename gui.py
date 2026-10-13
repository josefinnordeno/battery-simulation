from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from data_loader import load_machine_rows
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
        ttk.Label(controls, text="Fordon").pack(anchor="w", pady=(0, 5))
        vehicle_frame = ttk.Frame(controls)
        vehicle_frame.pack(anchor="w", fill="x")
        self.vehicles = tk.Listbox(vehicle_frame, selectmode=tk.MULTIPLE, height=5, width=27, exportselection=False)
        scrollbar = ttk.Scrollbar(vehicle_frame, orient="vertical", command=self.vehicles.yview)
        self.vehicles.configure(yscrollcommand=scrollbar.set)
        self.vehicle_names = [row["name"] for row in load_machine_rows()]
        for name in self.vehicle_names:
            self.vehicles.insert(tk.END, name)
        self.vehicles.selection_set(0, tk.END)
        self.vehicles.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.season = self._choice(controls, "Säsong för baslast", ("Vinter", "Sommar"), "Vinter")
        self.scenario = self._choice(controls, "Belastningsnivå", ("Hög", "Låg"), "Hög")
        self.capacity = self._field(controls, "Batterikapacitet (kWh)", "140")
        self.min_soc = self._field(controls, "Min SOC (%)", "10")
        self.max_soc = self._field(controls, "Max SOC (%)", "80")
        self.power = self._field(controls, "Laddningseffekt per batteri (kW)", "22")
        self.efficiency = self._field(controls, "Laddningsverkningsgrad (%)", "92")
        self.swap_time = self._field(controls, "Bytestid (minuter)", "25")
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

    @staticmethod
    def _choice(parent, label, values, default):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 4))
        value = tk.StringVar(value=default)
        ttk.Combobox(parent, textvariable=value, values=values, state="readonly", width=19).pack(anchor="w")
        return value

    def _run(self):
        try:
            selected = [self.vehicle_names[index] for index in self.vehicles.curselection()]
            result = run_simulation(
                capacity_kwh=float(self.capacity.get()),
                charging_power_kw=float(self.power.get()),
                swap_time_minutes=int(self.swap_time.get()),
                scenario={"Hög": "high", "Låg": "low"}[self.scenario.get()],
                season=self.season.get(),
                vehicle_names=selected,
                min_soc_percent=float(self.min_soc.get()),
                max_soc_percent=float(self.max_soc.get()),
                charging_efficiency_percent=float(self.efficiency.get()),
            )
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
