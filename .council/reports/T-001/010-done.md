---
task: T-001
status: done
percent: 100
touched: [docs/social/council-facebook-1200x630.png, docs/social/council-instagram-1080.png]
needs: []
verify: ["Headless Edge render: oba procesy zakonczyly sie kodem 0 po uruchomieniu przez Start-Process -Wait z osobnymi swiezymi profilami tymczasowymi i --no-sandbox", "PowerShell PNG signature/IHDR check: council-facebook-1200x630.png = 1200x630 i 354329 B; council-instagram-1080.png = 1080x1080 i 518122 B; oba maja poprawna sygnature PNG i przekraczaja 100 KB", "PowerShell content check: kazdy HTML zawiera kazda wymagana komende dokladnie raz, a marketplace add poprzedza plugin install", "Oględziny obu PNG: brak przepełnienia płótna i kolizji bloku komend z marką, perks lub kartami modeli; oba bloki marki są w pełni widoczne"]
dissent: false
---
Odtworzenie na aktualnej bazie zakończone. Pliki HTML już zawierały wymagany dwuwierszowy blok w poprawnej kolejności i właściwe ustawienia układu, więc pozostawiłem je bez dodatkowego zapisu. Ponownie wyrenderowałem oba PNG z tych źródeł i potwierdziłem ich wymiary, rozmiar, treść oraz poprawny wygląd. README.md i docs/social/posts.md już dokumentują oba polecenia w poprawnej kolejności; brak plików stanu projektu wymagających aktualizacji. .gitignore nie wymaga zmiany, ponieważ PNG są docelowymi artefaktami z zakresu zadania, a żaden plik tymczasowy nie powstał w repozytorium.
