# PR — porównanie FunctionGemma 268M i 299M

W ostatnim porównaniu wąski kontrakt osiągnął 111/128, w tym 48/64 po polsku i 63/64 po angielsku. Wszystkie dziewięć nieoczekiwanych wywołań dotyczyło polskich intencji zapisu. Eksperyment sprawdza osobno wpływ nowych przykładów i wpływ poszerzenia modelu. Punktem startu jest zachowany checkpoint 128 wąskiego kontraktu.

## Ramiona i warunki

| Ramię | Parametry | Dane |
|---|---:|---|
| A | 268 098 176 | Dotychczasowe 2048 decyzji |
| B | 268 098 176 | 2048 decyzji z 512 zmienionymi polskimi przykładami |
| C | 299 063 936 | Identyczne rekordy i tokeny jak w B |

A–B mierzy wpływ korpusu. B–C mierzy wpływ poszerzenia wszystkich 18 MLP z 2048 do 2944. Wagi A i B są identyczne. C kopiuje ich wartości, dodaje kanały z zerowym wkładem na wyjściu i zachowuje tokenizer oraz kontrakt sześciu akcji. Oba seedy treningowe zaczynają od tych samych wag w obrębie ramienia i świeżego stanu AdamW.

Receptura zachowuje pełny SFT, parametry i momenty AdamW FP32, obliczenia BF16, batch 4 z akumulacją 4, kontekst 2048 i 128 aktualizacji na epokę. Wstępnie ustalony LR to 2e-6. Checkpointy są zapisywane po 32, 64, 96 i 128 krokach. Ocena kandydatów obejmuje 32, 64 i 128. Oba przebiegi porównawcze używają tego samego sprzętu i odpowiednio seedów 42 i 43.

## Materiał i ocena

- Zachować język, pozycje rekordów oraz etykiety akcji przy wymianie polskich przykładów. Przy jednej ścieżce rozdzielić odczyt, podgląd, zapis z treścią, pustą treść, brak treści i cofnięcie polecenia.
- Przygotować rozłączne rodziny parafraz i przestrzenie robocze dla treningu, rozwoju i zamrożonej oceny. Odtworzyć referencje w sandboxie. Raportować osobno surową akcję modelu, zweryfikowane argumenty i wynik wykonania. Zapisy testować w warstwie zgody operatora.
- Zweryfikować pełne generacje pilota przed treningiem z wag 268M i 299M. Kwalifikacja GPU na hoście obejmuje zmianę wag, zapis, odczyt i wznowienie każdej receptury. Przed oceną masową przejrzeć 16 surowych odpowiedzi każdego ocenianego checkpointu.
- Porównywać wynik PL i EN, akcje, argumenty, nieoczekiwane wywołania, błędy formatu, utracone poprawne odczyty oraz medianę i P95 na wspólnych poprawnych przypadkach. Grupować wnioski według rodzin parafraz. Mierzyć oddzielnie zużycie VRAM i opóźnienie w docelowej ścieżce Venoma.
- Do odbioru kierować jednego finalistę po obu powtórzeniach i przejściu retencji. Obowiązują 98% poprawnych zadań narzędziowych, 95% odpowiedzi bez wywołania oraz zero wywołań nieoczekiwanych lub niedozwolonych, deklaracji zapisu bez wykonania i utraconych poprawnych odczytów.

## Wykonanie

Lokalnie powstają narzędzie do poszerzenia, korpusy, pakiety z odciskami kodu i danych, testy, dowód równoważności inicjalizacji oraz procedura sesji zdalnej. Artefakty modelu, dane i surowe wyniki są prywatne. Używamy standardowej sesji FunctionGemma na Ubuntu VM z SSH direct, 100 GB dysku i kartą z co najmniej 24 GB VRAM. Przed treningiem host przechodzi kwalifikację. Uruchomienia treningowe są osobnym etapem operacyjnym.
