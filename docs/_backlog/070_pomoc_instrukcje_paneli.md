# 070: Pliki pomocy i linki do instrukcji paneli

## Cel
Przygotować spójne instrukcje obsługi dla paneli w UI oraz dodać linki do tych instrukcji w odpowiednich miejscach aplikacji.

## Zakres
1. **Dokumentacja**
   - [ ] Stworzyć strony instrukcji dla kluczowych paneli (Cockpit, Serwery LLM, Konfiguracja, Modele).
   - [ ] Ustalić jednolity format instrukcji (nagłówek, zakres, kroki, najczęstsze problemy).
   - [ ] Dodać nawigację między instrukcjami (spis treści / sekcja "Zobacz też").

2. **UI**
   - [ ] Dodać linki "Instrukcja obsługi" w panelach, gdzie użytkownik potrzebuje wsparcia.
   - [ ] Ujednolicić styl linków pomocy (kolor, ikonka, hover, kursor).
   - [ ] Zapewnić stałą widoczność linku w wybranych panelach (nie tylko przy błędach).

3. **Spójność**
   - [ ] Powiązać linki z docelowymi stronami w `web-next/app/docs/*`.
   - [ ] Zweryfikować, że instrukcje nie zdradzają danych wrażliwych.

## Kryteria akceptacji
- Każdy wskazany panel ma link do instrukcji.
- Instrukcje są krótkie, praktyczne i spójne w formie.
- Linki mają spójny styl z paletą UI i wyraźny stan hover.

## Przykład (wdrożony wzór)
- **Panel**: Serwery LLM (Cockpit).
- **Co zawiera**: stały link "Instrukcja dodawania modeli" z ikoną pomocy, stylowany w barwie `--secondary`, z podkreśleniem i wyraźnym hover.
- **Docelowa instrukcja**: strona `/docs/llm-models` opisująca kroki dodawania modeli (Ollama/vLLM).
- **Cel wzorca**: pokazuje gdzie i jak osadzić link pomocy w panelu, żeby nie był zależny od stanu błędu.

## Proponowane pliki do zmiany
- `web-next/app/docs/*` (nowe strony instrukcji)
- `web-next/components/*` (linki w panelach)
- `web-next/app/globals.css` lub lokalne klasy (styl linków pomocy)
