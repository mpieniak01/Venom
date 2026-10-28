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
Profil inspect służy do odbioru infrastruktury i nie instaluje modelu czatu.
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

Test zerowy infrastruktury korzysta z komendy trial-zero i planu inspect:
create -> SSH/inspect -> eksport -> destroy -> potwierdzenie zera.
Nie pobiera modelu i nie uruchamia rozmowy. Test czatu po przygotowaniu modelu
jest osobną próbą. Testy automatyczne używają atrap i nie tworzą płatnych zasobów.

Pełny opis istniejącego CLI: [Vast environment operations](../../integrations/vast.md).

Direct zachowuje do 20 zakończonych wiadomości (50 000 znaków) dla konkretnego
celu, generacji połączenia, modelu i sesji w otwartym czacie. Odświeżenie strony
czyści ten kontekst Direct. Niepełne odpowiedzi nie są dopisywane do kontekstu.
Istniejący awaryjny STOP anuluje także aktywny strumień HTTP Direct.
