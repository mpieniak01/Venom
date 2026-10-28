# Podgląd ofert Vast

W Ubuntu-Venom, z repozytorium `/home/ubuntu/venom`:

```bash
source .venv/bin/activate
python scripts/cloud/vast/offers_table.py
```

Domyślnie skrypt czyta istniejący profil
`.venom_runtime/vast/prepared/chat-gemma4-26b-q4-24gb.json` i poświadczenia
z `.env.dev`. Pokazuje do 10 ofert ocenionych jako `eligible`, posortowanych
numerycznie po cenie godzinowej USD (wraz z dyskiem z profilu, bez transferu).
Wyszukuje dowolny model GPU, pomijając listę gpu_names z profilu. Pozostałe
wymagania (m.in. NVIDIA/CUDA, VRAM, RAM, CPU) pozostają. Nie stosuje preferencji
kraju; ograniczenia krajów zapisane w profilu pozostają. Plik profilu nie jest zmieniany.

Kolumny: ID oferty, USD/h, opis techniczny (CUDA, sterownik NVIDIA, machine ID),
GPU, FLOPS (TFLOPS deklarowane przez Vast w total_flops), VRAM, RAM hosta, szacowany RAM instancji, procesor i efektywne rdzenie,
lokalizacja. Pamięć jest przeliczana z MB na GB (MB / 1000), do dwóch miejsc po przecinku. Cena USD/h ma cztery miejsca po przecinku; sortowanie używa pełnej precyzji.
RAM instancji to `cpu_ram * gpu_frac`, nie potwierdzony limit kontenera.
Ocena oferty nie potwierdza inferencji GPU ani gotowości modelu.

```bash
python scripts/cloud/vast/offers_table.py --limit 5 --locale en
python scripts/cloud/vast/offers_table.py --profile /path/to/profile.json
```

Dostępne opcje: `--profile`, `--env-file`, `--state-dir`, `--limit 1..100`,
`--locale pl|en|de`. Ścieżki domyślne są liczone od katalogu repozytorium,
więc skrypt można uruchomić także z innego katalogu.

Wyszukiwanie używa istniejącego klienta i filtrów Vast. API zwraca pulę do
100 ofert; dodatkowa ocena lokalna może ją zmniejszyć. Przy mniej niż 10
pasujących ofertach skrypt pokazuje dostępne wyniki bez poluzowania wymagań.
Błąd API kończy się kodem niezerowym i komunikatem JSON na stderr.

Skrypt wywołuje wyłącznie odczyt ofert. Nie tworzy planu ani instancji.
