# Modellkontext

Kontext överförd från genomgången i Codex den 13 oktober 2026. Kontrollera aktuella filer före framtida ändringar.

## Flöde
- `main.py` och `gui.py`: Tkinter-gränssnittet.
- `data_loader.py`: läser `Beräkningar - Modell.csv`, filtrerar valda maskiner med elersättare, positiva årsarbetstimmar och positiv energiförbrukning. Ger 15 maskiner i nuvarande indata. Fallback till äldre CSV eller exempelflotta.
- `data_loader.py`: 96 steg per dygn, arbetsfönster 07–16, raster 09–09:30 och 12–12:30. Policies `centered`, `staggered`, `reference`. Låg/hög belastning använder maskinernas CSV-timmar för de nya schemana; reference använder klassvärden.
- `models.py`: Battery och Machine, laddning, förbrukning och byte.
- `simulation.py`: drift, reservpool, laddningskö och resultat.
- `visualization.py`: planerat schema, antal aktiva maskiner, maskinens monterade batteris SoC, baslast och laddning.
- `test_simulation.py`: 12 befintliga tester vid ursprunglig genomgång.

## Standardantaganden
140 kWh per batteri, 15 monterade batterier och 25 reserver, initial SoC 80 %, bytesutlösare vid högst 10 %, 22 kW laddning per batteri, 92 % laddningsverkningsgrad, 25 min byte och 15 kW rastlast per maskin inom dess skift. Standardantal laddplatser är monterade batterier plus reserver. Vinterbaslast 150–250 kW; sommarbaslast 40–100 kW. Säsong kan anges separat i Python men är kopplad till belastningsscenario i GUI.

## Verifierat beteende i den ursprungliga koden
- Samtliga 12 tester passerade den 13 oktober 2026.
- Standard hög/vinter: 27 byten, 21 samtidigt laddande batterier, 462 kW högsta laddeffekt, 692 kW högsta nätlast, minsta reserv 4. Planerat arbete 90 maskintimmar, utfört 78,75.
- Standard låg/sommar: 12 byten, 12 samtidigt laddande, 264 kW högsta laddeffekt, 354 kW högsta nätlast, minsta reserv 13. Planerat arbete 48 maskintimmar, utfört 43,75.
- Detta är kodens utfall, inte validerade mätvärden från anläggningen.

## Kända begränsningar – ännu inte åtgärdade
1. Arbete som uteblir vid byte tas inte igen. Schematabell och schemadiagram visar planerad tid.
2. 25 min byte blockerar två 15-minuterssteg, medan rapporterad bytestid räknar 25 min.
3. SoC kan sjunka under 10 % före byte. SoC-historiken skrivs efter bytet och visar då ersättningsbatteriet. Lägsta återlämnade SoC i standardkörningen var cirka 0,82 %.
4. Om reservpoolen är tom kan arbete fortsätta räknas trots tomt batteri. `Battery.consume` begränsar energiuttaget, men arbetssteg räknas ändå.
5. Effektkurvan räknar full laddareffekt i sista, delvis utnyttjade laddsteget. Integrerad effektkurva skiljer sig därför från `grid_energy_kwh`.
6. `seed` och generatorn påverkar ännu inte schemat eller maskineffekten.
7. Batterikapacitet läses från CSV, men simuleringen använder argumentet `capacity_kwh` för alla batterier. CSV-parametertabellens nätgräns och framtida scenariofaktorer tillämpas inte av simuleringen.
8. Ett dygn startar med samtliga batterier på 80 %. Monterade batterier laddas inte upp för nästa dag efter avslutat arbete. Upprepade, sammanhängande dygn kräver ytterligare logik.

## Diskuterad stokastisk utökning – inte implementerad
Slumpa giltiga starttider eller sammanhängande arbetsblock på 15-minutersrutnätet, behåll planerade produktiva timmar och gör slumpen reproducerbar. Klass A hög behöver hela 07–16 inklusive raster, så senare starter kräver ett uttryckligt antagande om senare sluttid eller ändrat rast-/arbetsupplägg. Jämför många dagar och redovisa topplast, reservbehov samt faktiskt utfört arbete.
