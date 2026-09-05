---
task: T-003
status: blocked
percent: 50
touched: [docs/social/graphic-wide.html]
needs: ["Uruchom ponownie render obu PNG w srodowisku, w ktorym dziala Chromium. Edge przy bezposredniej probie zakonczyl sie komunikatem: FATAL:content\\browser\\gpu\\gpu_data_manager_impl_private.cc:436 GPU process isn't usable. Goodbye. Kontrolowana proba Start-Process -Wait zwrocila Edge exit code -2147483645 (0x80000003) i nie zaktualizowala PNG. chrome.exe nie istnieje w PATH ani w standardowych lokalizacjach Program Files/AppData."]
verify: []
dissent: false
---
Poprawka HTML jest gotowa: w graphic-wide.html tylko .models zwezono z 330 do 270 px. Modele zaczynaja sie przy x=866, lewa kolumna konczy maksymalnie przy x=824, wiec gutter wynosi 42 px bez zmiany zawijania naglowka ani wysokosci lewej kolumny. graphic-square.html pozostawiono bez zmian po kontroli wizualnej. Oba istniejace PNG maja poprawne stare wymiary i rozmiary, ale ich timestamp 19:23:29 jest starszy niz edycja HTML 19:26:24, wiec nie spelniaja kryterium ponownego renderu. Profile tymczasowe zostaly usuniete. posts.md i README.md sprawdzono jako read-only; nie wymagaja aktualizacji. Brak trwalych nowych artefaktow, wiec .gitignore nie wymaga zmiany. Praca zatrzymana zgodnie z kontraktem po zapisaniu statusu blocked.
