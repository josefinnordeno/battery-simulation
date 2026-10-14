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
En lokal Git-historik har skapats med en första version av projektet.
Ingen personlig commit-identitet var inställd vid setup. Den första versionen använder den tekniska identiteten “Battery simulation setup” (setup@localhost), enbart för denna commit. Ange ditt eget namn och din e-post lokalt i projektet före personliga commits.
GitHub är inte anslutet. Inget publiceras av denna setup.

## Modellens begränsningar
Se MODELLKONTEXT.md. Installation och passerande tester innebär inte att samtliga modellantaganden är validerade eller att bristerna är åtgärdade.

## Verifierad setup
Den 14 oktober 2026 passerade alla 12 befintliga tester i projektets egen Python-miljö. Tkinter-fönstret skapades och standardkörningens fyra diagram renderades. Status: 692 kW topplast och 27 byten. Paketversionerna finns i requirements-lock.txt.
