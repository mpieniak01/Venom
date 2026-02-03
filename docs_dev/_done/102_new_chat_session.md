# Zadanie 102: Dodanie funkcji "Nowy Czat" w Cockpit AI

## Cel
Umożliwienie użytkownikowi szybkiego rozpoczęcia nowej sesji czatu bezpośrednio z konsoli Cockpit AI. Funkcja ta ma czyścić okno czatu i resetować kontekst (session_id), co jest analogiczne do efektu restartu serwera lub ręcznego resetowania sesji w panelu operacyjnym.

## Analiza stanu obecnego
Obecnie mechanizm resetowania sesji istnieje, ale jest ukryty w panelu "Serwery LLM" w sidebarze pod przyciskami "Resetuj sesję" oraz "Nowa sesja serwera".
- **`resetSession` (lib/session.tsx)**: Generuje nowe `session_id` i zapisuje je w `localStorage`.
- **`handleServerSessionReset` (cockpit-session-actions.ts)**: Czyści pamięć sesji na backendzie i wywołuje `resetSession`.
- **UI**: Użytkownik musi otworzyć sidebar, przejść do sekcji modeli i tam kliknąć mały przycisk, co nie jest intuicyjne dla funkcji "nowy czat".

## Zakres zmian

### 1. Frontend (`web-next`)

#### Rozbudowa `CockpitChatConsole`
- Dodanie przycisku "Nowy czat" w nagłówku konsoli (`SectionHeading` -> `rightSlot`).
- Przycisk powinien być wyraźnie widoczny, np. w kolorze bursztynowym (`amber-300`) lub fioletowym, z odpowiednią ikoną (np. `PlusCircle` lub `RefreshCw`).
- Powinien wywoływać logikę `onServerSessionReset`, która:
    1. Czyści wektory pamięci dla aktualnej sesji.
    2. Generuje nowy identyfikator sesji.
    3. Czyści lokalną historię wiadomości.

#### Przekazywanie akcji (Props)
- Aktualizacja `useCockpitSectionProps` i `CockpitPrimarySection`, aby przekazać funkcję resetu sesji do komponentu konsoli.

### 2. Testy backendowe
- Dodanie testu API `tests/test_new_chat_session_api.py`, który weryfikuje:
    1. Czyszczenie wpisów w wektorowej bazie danych for specific `session_id`.
    2. Czyszczenie historii kontekstu w `StateManager`.
- Rejestracja nowego testu w grupie `config/pytest-groups/light.txt`.

### 3. UX i Komunikacja
- Po kliknięciu przycisku powinno pojawić się potwierdzenie (np. Toast) z informacją o nowej sesji: "Rozpoczęto nową sesję czatu".
- Okno czatu powinno natychmiast stać się puste (poza ewentualnym komunikatem powitalnym).

## Plan wdrożenia
- [x] Modyfikacja `web-next/components/cockpit/cockpit-chat-console.tsx` - dodanie przycisku.
- [x] Modyfikacja `web-next/components/cockpit/cockpit-section-props.ts` - wystawienie akcji resetu.
- [x] Modyfikacja `web-next/components/cockpit/cockpit-primary-section.tsx` - przekazanie propsów.
- [x] Dodanie testu backendowego `tests/test_new_chat_session_api.py`.
- [x] Rejestracja testu w `config/pytest-groups/light.txt`.
- [x] Weryfikacja działania mechanizmu czyszczenia okna i zmiany `session_id`.

## Status realizacji
- **Analiza**: Zakończona. Wykryto istniejący mechanizm w `useCockpitSessionActions`.
- **Dokumentacja**: Przygotowana (Zadanie 102).
- **Implementacja**: Zrealizowana. Przycisk dodany do nagłówka konsoli, pomyślnie zintegrowany z resetem sesji.
- **Testy**: Dodano i zweryfikowano test API `tests/test_new_chat_session_api.py`.
