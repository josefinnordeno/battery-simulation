# Batterisimulering

Modellen jämför batterilager, laddinfrastruktur och produktionsbortfall för en
elektrifierad maskinpark. Den läser i första hand `Beräkningar - Modell.csv`,
väljer giltiga `TRUE`-markerade elersättare och hanterar svenska decimaler.
Indata hittas relativt programfilen, även när programmet startas från en annan
katalog. Om modellfilen saknas används `Beräkningar_Driftschema.csv`, därefter
ett inbyggt exempel. Referenskontrollen kräver själva modellfilen.

## Två tydliga beräkningslägen

**Kalkylbladsreferensen** återspelar och kontrollerar CSV-filens halvtimmesvärden.
Den reproducerar 27 byten, maximalt 22 laddande batterier, 484 kW laddeffekt,
734 kW nätlast och minst 3 reservbatterier. Kalkylbladets maskinvisa bytestider
och sammanlagda laddtidsserie stämmer inte helt överens; avvikelserna redovisas.
Referensen är därför inte ett bevis på en fysikaliskt korrekt simulering.

**Den operativa simuleringen** beräknar energi, tillgänglighet och laddning:

- alla 15 valda maskiner och uttryckliga hög-/lågbelastningstimmar från CSV;
- 8/4/2 timmar för klass A/B/C vid hög belastning, från 08:00;
- 10–80% SoC och 92% laddningsverkningsgrad;
- 25 minuters batteribyte med verkligt produktionsbortfall;
- 25 reservbatterier utöver 15 installerade, alltså 40 moduler totalt;
- 22 laddare à 22 kW, begränsade av 1 MW nätanslutning och befintlig last;
- brist på reserver, stillestånd och ej levererad arbetsenergi som separata KPI:er;
- valbar omedelbar eller deadline-baserad smart laddning.

140 kWh är en **antagen gemensam utbytbar modul**, inte Volvo-maskinernas
OEM-batterier. Kapacitetsfältet påverkar samtliga moduler i simuleringen.
Med 10–80% SoC ger en modul 98 kWh arbetsenergi och behöver
`98 / (22 × 0,92) = 4,8419` timmar för återladdning.

Standardkörningen är deterministisk. Med fysiska bytestider ger den 25 byten och
712 kW topplast; arbetstid förlorad vid byten förklarar att den inte har samma
resultat som kalkylbladsreferensen. Lastdiagrammet visar 15-minutersmedel, medan
topplast och bytestider beräknas med en minuts upplösning.

Se [modellkontraktet och auditresultaten](docs/model_v2.md) för exakta antaganden,
KPI-definitioner, referensavvikelser, laddstrategier och forskningskällor.

## Kör GUI

Python 3.11 eller senare och Tkinter behövs.

```sh
python -m pip install -r requirements.txt
python gui.py
```

GUI visar driftschema, maskinernas SoC och nätlast. Ange kapacitet, bytestid,
reservlager, laddarantal, nätgräns och laddstrategi. Knappen för kalkylbladsreferens
visar den separata återspelningens KPI:er.

## Monte Carlo och känslighetsanalys

```sh
python scenario_analysis.py --days 500 --seed 42
python scenario_analysis.py --days 500 --seed 42 --policy deadline
python scenario_analysis.py --days 500 --seed 42 --sweep
```

Resultat skrivs som JSON: P50/P95/P99 topplast, sannolikhet för reservbrist,
nätgränsöverskridande och mer än 30 minuters maskinstillestånd samt medelenergi
och stillestånd. Det korrelerade aktivitetsmönstret är ett konfigurerbart exempel,
inte telemetrikalibrerad statistik. Det bevarar CSV-värdenas planerade dagsmedel.

Känslighetsanalysen jämför sex modul-/pool-/laddarealternativ från auditen.
Python-API:t kan även rangordna alternativen med egna kostnadsantaganden:

```python
from scenario_analysis import CostAssumptions, run_sensitivity

# Ange egna priser i samma valuta; inga kostnadsvärden antas av modellen.
costs = CostAssumptions(
    module_capital_per_kwh=module_price,
    charger_capital_per_kw=charger_price,
    capital_daily_factor=daily_capital_factor,
    energy_per_kwh=energy_price,
    peak_per_kw_day=peak_price,
    downtime_per_machine_hour=downtime_price,
)
comparison = run_sensitivity(days=500, costs=costs)
```

## Kontroller

```sh
python -m unittest discover -v
python -m pip install ruff pyright
ruff check .
ruff format --check .
pyright
```

Tester verifierar referensens fem KPI:er, energibalans, SoC-gränser, bytestid,
reservbrist, ändrad kapacitet, laddar-/nätgränser och reproducerbara analyser.

## Bygg en körbar `.exe` på Windows

```powershell
pyinstaller --noconsole --onefile --add-data "Beräkningar - Modell.csv;." --name battery-simulation gui.py
```

Om CSV-filen inte ska skickas med kan `--add-data` utelämnas. Den operativa
simuleringen använder då fallback-data.
