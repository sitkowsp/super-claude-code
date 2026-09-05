---
task: T-001
status: progress
percent: 45
touched: []
needs: []
verify: []
dissent: false
---
Sprawdzono aktualną bazę. Oba HTML mają wymagane dwie linie w poprawnej kolejności i minimalne ustawienia układu zgodne z poprzednią zaakceptowaną wersją roboczą: 20 px w grafice szerokiej oraz pionową stopkę z tekstem 24 px w grafice kwadratowej. Pierwsze wywołanie Edge nie odświeżyło plików, ponieważ dwa procesy współdzieliły profil i proces GPU zakończył się błędem; ponawiam renderowanie sekwencyjnie przez Start-Process -Wait z osobnymi profilami tymczasowymi.
