# Arbeta med batterimodellen

## Öppna projektet
Öppna denna mapp i VS Code: `/Users/rpersson03/ChatGPT/Energisystemplanering/battery-simulation-master`.
Använd denna som arbetskopia. Kopian i Downloads är separat.

## Starta modellen
1. Välj Terminal → Run Task → Starta batterisimuleringen.
2. I simuleringens fönster: välj kapacitet, laddeffekt, bytestid och scenario.
3. Klicka Kör simulering.

Alternativt: Run and Debug → Batterisimulering → F5.

## Kör tester
Terminal → Run Task → Kör tester. Alla tester finns också i Testing-panelen.

## Arbeta med Codex
Klicka på Codex-ikonen och logga in med ditt ChatGPT-konto om du blir ombedd.
Om ikonen saknas: Cmd+Shift+P → Codex: Open Codex Sidebar.
Be först om en tydligt avgränsad ändring, exempelvis: “Undersök hur vi kan införa slumpmässiga starttider. Läs AGENTS.md och MODELLKONTEXT.md. Föreslå upplägg utan att ändra kod ännu.”
För implementation: ange vilket upplägg du vill ha och be om tester och beskrivning av resultaten.
Öppna Source Control-panelen för att granska ändringar innan du sparar en ny Git-version.
Nya Codex-chattar får projektkontext från filerna men har inte automatiskt hela historiken från den här chatten.

## Pythonmiljön
Projektets paket ligger separat i `.venv`. VS Code är inställt att använda den.
Om fel Python är vald: Cmd+Shift+P → Python: Select Interpreter → välj `.venv/bin/python` i denna mapp.
Terminalkommandon från projektroten:
```
.venv/bin/python gui.py
.venv/bin/python -m unittest -v
```

## Versionshistorik
Projektet är kopplat till `https://github.com/josefinnordeno/battery-simulation.git` som `origin`. Den gemensamma huvudbranchen heter `master`.
Arbetsbranchen för denna setup heter `codex/robin`. Den bevarar den befintliga lokala kopian, inklusive skillnader mot GitHubs modellversion. Den ursprungliga lokala versionen finns kvar på `main`; den är inte den gemensamma huvudbranchen.
Setup-commits använder den tekniska identiteten “Battery simulation setup” (setup@localhost). Ange ditt eget namn och din e-post lokalt i projektet före personliga commits.

## Samarbeta via GitHub
Arbeta i en egen branch och granska ändringar före varje commit. Efter att arbetsbranchen publicerats används:
```
git fetch origin
git status
git add <filer-du-vill-spara>
git commit -m "Beskriv ändringen"
git push
```
Skapa sedan en pull request på GitHub från arbetsbranchen till `master`. Kör testerna och låt en gruppmedlem granska innan ändringarna slås ihop. Setup-branchen innehåller även tidigare lokala skillnader i `gui.py`, `simulation.py` och `visualization.py`; granska dem särskilt före sammanslagning.
Hämta framtida uppdateringar från `origin/master` och granska hur de passar med dina ändringar innan du slår ihop dem. Varje gruppmedlem använder sin egen Pythonmiljö; `.venv` och `__pycache__` ska inte versionshanteras.

## Modellens begränsningar
Se MODELLKONTEXT.md. Installation och passerande tester innebär inte att samtliga modellantaganden är validerade eller att bristerna är åtgärdade.

## Verifierad setup
Den 14 oktober 2026 passerade alla 12 befintliga tester i projektets egen Python-miljö. Tkinter-fönstret skapades och standardkörningens fyra diagram renderades. Status: 692 kW topplast och 27 byten. Paketversionerna finns i requirements-lock.txt.
