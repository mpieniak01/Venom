# Test zero dostawcy — wyłącznie na żądanie operatora

Zasada dotyczy VAST (`trial-zero`) i OpenRouter (`scripts/cloud/openrouter/test_zero.py`). Rzeczywisty test zero jest ręczną czynnością odbiorową uruchamianą wyłącznie na wyraźne żądanie operatora dotyczące danego wykonania.

Klucz API, zatwierdzony budżet, podłączone modele, wcześniejszy udany przebieg ani zakończenie prac nie upoważniają do kolejnego testu. Nadal obowiązują istniejące zasady zatwierdzania budżetów oraz operacji na infrastrukturze VAST.

Nie uruchamia się rzeczywistego testu zero w polityce automatycznych testów lokalnych/PR, `make pr-fast`, regresjach, GitHub Actions, Sonarze, harmonogramach, starcie stosu, wdrożeniu ani automatycznym sprawdzaniu po zmianach. Włączenie dostawcy lub podłączenie modelu nie może go wyzwalać. Brak ręcznego wyniku i niedostępność zewnętrznego API nie blokują startu Venoma ani bramek jakości kodu.

Automatyczne testy jednostkowe/kontraktowe mogą sprawdzać kod testu zero wyłącznie na atrapach transportu i dostawcy. Nie są wykonaniem rzeczywistego testu zero. Obecne `tests/test_openrouter_test_zero.py` oraz testy zero/cleanup VAST wykorzystują takie atrapy; wpis w katalogu testów nie jest zgodą na prawdziwe wywołania, generacje lub wynajem.

Zwykły odczyt statusu, wyszukiwanie modeli i przycisk sprawdzania połączenia są odrębnymi operacjami produktu. Sprawdzenie metadanych nie może być prezentowane jako udany test zero obejmujący odpowiedź modelu ani automatycznie rozszerzane o generację.

Po zleceniu operatora zapisuje się osobno zakres, rewizję/konfigurację, dostawcę/model lub plan VAST, wynik i zgłoszony koszt. Zielony test z atrapą nie dowodzi rzeczywistej odpowiedzi. Nie rozszerza się zakresu o wynajem hosta, zmianę aktywnego modelu lub ponowienie niejednoznacznej generacji bez odpowiedniego zlecenia.
