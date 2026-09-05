---
task: T-001
status: done
percent: 100
touched: [docs/social/graphic-wide.html, docs/social/graphic-square.html, docs/social/council-facebook-1200x630.png, docs/social/council-instagram-1080.png]
verify: ["PowerShell PNG signature/IHDR check: council-facebook-1200x630.png = 1200x630 and 354329 bytes; council-instagram-1080.png = 1080x1080 and 518122 bytes", "PowerShell content check: each HTML contains each requested command exactly once and marketplace add precedes plugin install", "Visual inspection of both final PNGs: no canvas overflow or command/brand/perk overlap; both brand blocks remain fully visible"]
dissent: false
---
Zaktualizowano oba bloki instalacyjne i ponownie wyrenderowano oba PNG za pomocą headless Edge. Wariant szeroki używa tekstu poleceń 20 px obok brandu; wariant kwadratowy zachowuje 24 px, układając blok poleceń nad prawostronnym brandem. Końcowe oględziny potwierdzają brak przepełnienia i kolizji. README.md oraz docs/social/posts.md już opisywały poprawną dwuetapową instalację, więc pozostały bez zmian. Nie ma plików stanu projektu wymagających aktualizacji; .gitignore przejrzano i nie wymaga zmiany, ponieważ PNG są docelowymi artefaktami w scope, a w repozytorium nie utworzono plików tymczasowych.
