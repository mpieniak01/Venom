# 74: Predykcja: szybkie odpowiedzi “sztampowe” (strategia do przemyślenia)


## Zalegle do zrobienia
- Tryb pełnoekranowego czatu: zostaje tylko lewy sidebar i górny pasek, a cała
  powierzchnia treści to chatbox; przełącznik względem obecnego widoku czatu.
- Podpięcie wyboru serwera i modelu na dole okna czatu jako selekty dopasowane
  do szerokości okna.
- Przewijana historia czatu (scroll z zachowaniem kontekstu).

## Cel
Zaprojektować strategię “predykcji” (szybkich, sztampowych odpowiedzi) tak, aby:
- poprawiać pierwsze wrażenie (“wow”) i time-to-first-token,
- nie psuć zaufania użytkownika,
- nie wykluczać działania pełnego LLM i streamingu.

## Problemy do rozwiązania
- Jak rozpoznać, kiedy odpowiedź sztampowa jest bezpieczna i oczekiwana?
- Jak uniknąć konfliktu z odpowiedzią generowaną przez LLM?
- Czy predykcja ma być zastępstwem, czy tylko “pierwszym kontaktem”?

## Pytania otwarte
- Czy predykcja powinna dotyczyć tylko powitań, czy też prostych pytań (np. “co to jest X”)?
- Czy predykcja ma być jawnie oznaczona w UI?
- Jak mierzyć efekt (TTFT, satysfakcja, odsetek rezygnacji)?
- Czy pierwszy krok powinien sprawdzać gotowość modelu (np. ukryty prompt systemowy)?

## Propozycje kierunków
- Tryb hybrydowy: predykcja jako szybki “pierwszy chunk”, potem LLM.
- Tylko lokalne reguły (bez dodatkowego LLM) + ścisły whitelist intents.
- Mechanizm anulowania predykcji, gdy LLM zwraca sprzeczny kontekst.
- Weryfikacja gotowości modelu jako pierwszy krok (ukryty prompt systemowy).
- Reguła warm-up: po restarcie web-next, gdy LLM działa i model jest załadowany,
  wyślij ukryty prompt systemowy: `Output exactly one character: "."` i nie pokazuj
  odpowiedzi użytkownikowi.

## PR 073: decyzje architektoniczne i wartość dodana
1) **Usunięcie „powitania jako pierwszego promptu”**
   - Powitanie jako pierwszy ruch nie wnosi wartości, psuje TTFT i bywa irytujące.
   - Warm-up powinien być techniczny i niewidoczny.
   - Pierwszy kontakt użytkownika ma dowodzić sensu, nie „grzeczności”.

2) **Jeśli intencja nieznana i brak toolsa → od razu do LLM**
   - To jest właściwy fallback: zero dodatkowych pętli klasyfikacji.
   - Zysk: krótszy TTFT, mniejsze ryzyko złej ścieżki, mniej szumu w logach.
   - Doprecyzowanie jakości:
     - Unknown + low-stakes (smalltalk / ogólne pytanie) → LLM od razu.
     - Unknown, ale tool-worthy (np. „sprawdź, policz, porównaj, wyciągnij dane z X”)
       → LLM od razu, ale z krótkim wrapperem systemowym:
       „Jeśli brakuje danych do wykonania zadania, zadaj jedno konkretne pytanie
       doprecyzowujące. Jeśli da się odpowiedzieć ogólnie — odpowiedz od razu.”

3) **Prosty schemat routingu**
   - intent znany + tool istnieje → tool route
   - intent znany + tool brak → LLM (z wrapperem „bez halu, poproś o dane”)
   - intent nieznany → LLM natychmiast (bez pętli)
   - hard stop: max 1 reroute, bez ping-ponga

4) **Metryki do weryfikacji**
   - % zapytań w LLM fallback
   - średni TTFT dla fallbacku
   - odsetek fallbacków kończących się dopytaniem (sygnał jakości, nie wada)

## Następne kroki
- Spisać listę bezpiecznych przypadków (use cases).
- Zdefiniować politykę “kiedy wolno” oraz “kiedy nie wolno”.
- Uzgodnić metryki i testy A/B (jeśli planowane).
