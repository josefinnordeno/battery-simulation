# Battery simulation – arbetskontext

Detta är den lokala arbetskopian av batterimodellen för Hovgården i Energisystemplanering.
Svara på svenska när användaren skriver svenska.

## Körning
- Projektets Python finns i `.venv/bin/python`.
- Starta från projektroten: `.venv/bin/python gui.py`.
- Kör befintliga tester: `.venv/bin/python -m unittest -v`.
- CSV-inläsningen använder aktuell arbetsmapp. Kör därför alltid från projektroten.

## Modell och ändringar
- Läs `MODELLKONTEXT.md` för arkitektur, nuvarande antaganden och verifierade begränsningar.
- Skilj planerat arbete, faktiskt utfört arbete, raster, batteribyten och laddning.
- Håll energi (kWh), effekt (kW), lagrad laddenergi och nätenergi åtskilda.
- Vid stokastiska utökningar: använd reproducerbart slumpfrö och redovisa antaganden. Minska inte arbetstimmar utan att redovisa det.
- CSV-filen innehåller både indata och gamla kalkylresultat. Presentera inte sparade CSV-resultat som aktuell Python-simulering.
- Ändra modellen endast inom användarens begärda scope. Setup innebär inte att de kända modellbristerna redan är åtgärdade.
- Bevara CSV-underlaget om användaren inte uttryckligen ber att ändra det.
- Kör relevanta tester efter kodändringar och beskriv vad som verifierats.
- Publicera eller skicka inga filer till externa tjänster utan användarens instruktion.
