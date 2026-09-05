---
task: T-001
status: progress
percent: 70
touched: []
needs: []
verify: []
dissent: false
---
Sprawdzono aktualną bazę. Oba HTML mają wymagane dwie linie w poprawnej kolejności i minimalne ustawienia układu zgodne z poprzednią zaakceptowaną wersją roboczą: 20 px w grafice szerokiej oraz pionową stopkę z tekstem 24 px w grafice kwadratowej. Pierwsze wywołania Edge nie odświeżyły plików z powodu awarii procesu GPU; renderowanie powiodło się po uruchomieniu sekwencyjnym przez Start-Process -Wait, z osobnym świeżym profilem tymczasowym i --no-sandbox. Oba procesy zakończyły się kodem 0. Przechodzę do kontroli wymiarów, rozmiarów, treści i oględzin.
