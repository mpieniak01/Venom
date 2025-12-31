# 083: Wizualizacja wektorów 2D (Embeddingi / Tok rozumowania)
Status: zakończone (flow mode, preset z PCA, topic filter/kolory, czyszczenie pamięci; pozostałe usprawnienia opcjonalne)

## Cel
Zbudować drugi etap wizualizacji pamięci: pokazać wektory (embeddingi) w 2D wraz z przepływem rozmowy (tok rozumowania) i tematami, aby łatwiej analizować kontekst sesji i podobieństwa treści.

## Założenia
- Pozostajemy w 2D (Cytoscape w trybie layoutu preset/stałych koordynatów).
- Wektory (embeddingi) już są w LanceDB; dodajemy redukcję wymiarów (PCA/UMAP) i zapis (x, y) + prosty temat/intencję per wpis.
- Obliczenia mogą być wykonywane w tle, nie blokują odpowiedzi czatu. Frontend dostaje gotowe (x, y, topic) i renderuje bez ciężkiego layoutu.

## Plan (etap 2)
1) **Enrich dane w LanceDB**
   - Dodać pola `x`, `y`, `topic` do wpisów pamięci/lekcji (przechowywane w LanceDB).
   - Prefiksowanie tekstu metadanymi (np. typ/rola) w embed, jeśli chcemy temat w wektorze (opcjonalne, konfiguracja).
   - Prosty klasyfikator tematów (kilkanaście kategorii; fallback „other”), zapis w meta.

2) **Batch redukcji wektorów**
   - ✅ Dodano endpoint `/api/v1/memory/embedding-project` (PCA 2D, zapis `x,y` do meta).
   - Pipeline w tle: pobierz embeddingi -> PCA/UMAP -> zapisz `x, y` do meta.
   - Przy dużej liczbie rekordów: limit/sampling lub klastrowanie (k-means) i zapis centroidów (do zrobienia).

3) **Endpoint grafu w trybie „flow”**
   - ✅ `/api/v1/memory/graph?mode=flow` dodaje krawędzie sekwencyjne; nodes niosą topic i opcjonalne `position` (x,y).
   - TODO: filtrowanie po topic/role/time window i krawędzie podobieństwa (top-N).

4) **Frontend /brain – tryb „Tok 2D”**
   - ✅ Auto-layout `preset` gdy węzły mają `position`; toggle flow w UI; przyciski czyszczenia pamięci i projekcji; filtr topic (ukrywa węzły bez dopasowania); kolory po topic; opacity według świeżości (timestamp).
   - Opcjonalne: krawędzie podobieństwa, cluster/sampling >500 (pozostawione jako przyszłe usprawnienia).

5) **Performance i UX** ✅
   - Cache/przycisk „Odśwież projekcję” w panelu (batch, nie na żywo).
   - Domyślnie etykiety węzłów skrócone, pełne w tooltipie/hover; edge labels off domyślnie.

6) **Testy** ✅
   - Unit API: `/api/v1/memory/graph` (flow) i `/api/v1/knowledge/graph` (limit/mock).
   - Smoke/lint/build OK; e2e opcjonalne.

## Dodatkowo: czyszczenie pamięci (na potrzeby testów) ✅
1) Reset sesji / tok rozumowania
   - UI przycisk „Wyczyść tok sesji” → `DELETE /api/v1/memory/session/{session_id}` + refresh grafu; StateManager czyszczony.

2) Wipe globalny (dev/test) ✅
   - UI przycisk „Wyczyść całą pamięć” (potwierdzenie).
   - API: `DELETE /api/v1/memory/global`; dev wipe LanceDB/Lessons opcjonalny (nie wymagany).

3) UX ✅
   - Toastery z liczbą usuniętych rekordów; odświeżenie grafu/lekcji po operacjach.
