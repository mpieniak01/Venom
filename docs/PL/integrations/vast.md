# Vast: Ollama w istniejącym czacie Venoma

Operator ręcznie tworzy i przygotowuje hosta istniejącym CLI Vast. Panel czatu
nie wynajmuje maszyn, nie instaluje silnika ani nie pobiera modeli.

Po podłączeniu gotowej instancji wybierz **Ollama · Vast**, następnie model
zainstalowany na zdalnym hoście. Pozycja jest niedostępna bez działającego hosta,
tunelu SSH i API Ollamy. Pusty katalog nie daje możliwości wyboru modelu.
Lokalne i zdalne modele o tej samej nazwie są osobnymi celami.

## Przygotowanie i połączenie

Przed utworzeniem hosta przygotuj profil Ollama z konkretnym modelem i digestem,
przypiętym obrazem, kontekstem oraz jawnym budżetem wynajmu i pobierania.
Dla testu zerowego wybierz recepturę Ollama z przypiętym obrazem zawierającym
Ollamę i curl, pustym modelem/digestem oraz download_gb=0. To przygotowuje sam
silnik, bez pobierania wag. Profil inspect pozostaje dostępny do samej inwentaryzacji.
Reużyj komend offers/assess/plan/create/wait/inspect/provision/ready.

Działające API Venoma jest właścicielem tunelu. Polecenia CLI:

    python scripts/cloud/vast/vast.py --json chat-attach --plan PLAN_ID --api-base http://127.0.0.1:8800
    python scripts/cloud/vast/vast.py --json chat-status --api-base http://127.0.0.1:8800
    python scripts/cloud/vast/vast.py --json chat-detach --api-base http://127.0.0.1:8800

Ollama jest dostępna przez prywatny tunel SSH; API silnika nie wymaga publicznego
portu. Odświeżenie strony nie zamyka połączenia należącego do API.
Czat Direct i Normal korzysta z wybranego celu i zachowuje jego tożsamość.
Awaria nie przenosi pytania na lokalny model. STOP generacji i odłączenie
tunelu nie kończą wynajmu.

## Zakończenie próby

Po próbie ręcznie wykonaj eksport i usunięcie instancji. cleanup-zero
potwierdza usunięcie konkretnego hosta i odczytuje pełną listę instancji konta,
także zatrzymanych. Kryterium sukcesu to zero. Błąd API ani nieznany stan
nie są zerem. Inne instancje są raportowane i nie są automatycznie usuwane.

    python scripts/cloud/vast/vast.py --json cleanup-zero --plan PLAN_ID --api-base http://127.0.0.1:8800 --timeout 120
    python scripts/cloud/vast/vast.py --json verify-zero

Test zerowy korzysta z komendy trial-zero i planu **Ollama bez modelu**:
create -> SSH/inspect -> provision -> ready (GET /api/version i /api/tags)
-> eksport -> destroy -> potwierdzenie zera. Pusty katalog jest poprawnym
wynikiem odbioru silnika; nie jest potwierdzeniem gotowego modelu czatu.
Każda awaria przygotowania lub API nadal prowadzi do cleanup.

    python scripts/cloud/vast/vast.py --json prepare --profile PROFIL_HOSTA.json --recipe ollama --download-gb 0 --output .venom_runtime/vast/ollama-zero.json
    python scripts/cloud/vast/vast.py --json trial-zero --plan PLAN_ID --timeout 120 --accept-new-host-key

PROFIL_HOSTA.json musi już wskazywać zweryfikowany obraz Ollamy, właściwą
architekturę i puste model/model_digest. Następnie wykonaj offers/assess/plan
dla utworzonego profilu, sprawdź koszty i dopiero jawnie uruchom trial-zero.
Nie używaj do testu zero planu inspect ani planu pobierającego model.
Test nie wykonuje generacji i nie potwierdza obliczeń modelu na GPU.
Dla rozmowy przygotuj osobny plan z konkretnym modelem i zgodnym digestem;
benchmark wymaga modelu. Testy automatyczne używają atrap i nie tworzą zasobów.

Pełny opis istniejącego CLI: [Vast environment operations](../../integrations/vast.md).

Direct zachowuje do 20 zakończonych wiadomości (50 000 znaków) dla konkretnego
celu, generacji połączenia, modelu i sesji w otwartym czacie. Odświeżenie strony
czyści ten kontekst Direct. Niepełne odpowiedzi nie są dopisywane do kontekstu.
Istniejący awaryjny STOP anuluje także aktywny strumień HTTP Direct.
