"""
Demo: Oracle Agent z GraphRAG - Multi-Hop Reasoning & Deep Analysis

Ten demo pokazuje jak używać Oracle Agent do:
1. Ingestii dokumentów (PDF, DOCX, tekst, URL)
2. Budowania grafu wiedzy
3. Multi-hop reasoning (wyszukiwanie relacji między encjami)
4. Global search (odpowiedzi na pytania o ogólny obraz)
5. Local search (odpowiedzi na pytania o konkretne związki)
"""

import asyncio
from pathlib import Path

from semantic_kernel import Kernel

from venom_core.agents.oracle import OracleAgent
from venom_core.config import SETTINGS
from venom_core.core.model_router import ModelRouter
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_oracle_basic():
    """Demo 1: Podstawowe użycie Oracle Agent."""
    logger.info("=== DEMO 1: Podstawowe użycie Oracle Agent ===")

    # Inicjalizacja Kernel z Model Router
    kernel = Kernel()
    model_router = ModelRouter(kernel)
    await model_router.configure_kernel()

    # Inicjalizacja Oracle Agent
    oracle = OracleAgent(kernel)

    # Sprawdź statystyki grafu wiedzy
    logger.info("\nSprawdzanie statystyk grafu wiedzy...")
    result = await oracle.process("Pokaż statystyki grafu wiedzy")
    print(f"\n{result}\n")

    return oracle


async def demo_ingest_file(oracle: OracleAgent):
    """Demo 2: Ingestia pliku tekstowego."""
    logger.info("=== DEMO 2: Ingestia pliku tekstowego ===")

    # Utwórz testowy plik
    test_dir = Path("./workspace/oracle_demo")
    test_dir.mkdir(parents=True, exist_ok=True)

    test_file = test_dir / "python_info.txt"
    test_content = """Python jest językiem programowania wysokiego poziomu stworzonym przez Guido van Rossum.
    
Pierwsza wersja Pythona została wydana w 1991 roku. 

Python jest używany w:
- Data Science i Machine Learning
- Rozwój aplikacji webowych (Django, Flask)
- Automatyzacja i skrypty
- Aplikacje desktopowe

Python wspiera różne paradygmaty programowania:
- Programowanie obiektowe
- Programowanie funkcyjne
- Programowanie proceduralne

Popularne biblioteki Python:
- NumPy - obliczenia numeryczne
- Pandas - analiza danych
- TensorFlow - deep learning
- Django - framework webowy
"""
    test_file.write_text(test_content, encoding="utf-8")

    # Poproś Oracle o przetworzenie pliku
    logger.info(f"\nPrzetwarzanie pliku: {test_file}")
    result = await oracle.process(
        f"Przeczytaj i przeanalizuj plik: {test_file}. Dodaj go do grafu wiedzy."
    )
    print(f"\n{result}\n")


async def demo_ingest_url(oracle: OracleAgent):
    """Demo 3: Ingestia URL."""
    logger.info("=== DEMO 3: Ingestia URL ===")

    # Przykładowy URL (możesz zmienić na rzeczywisty)
    url = "https://docs.python.org/3/tutorial/index.html"

    try:
        logger.info(f"\nPobieranie i przetwarzanie URL: {url}")
        result = await oracle.process(
            f"Pobierz i przeanalizuj stronę: {url}. Dodaj ją do grafu wiedzy."
        )
        print(f"\n{result}\n")
    except Exception as e:
        logger.warning(f"Nie udało się przetworzyć URL {url}: {e}")
        logger.info("Pomijam demo ingestii URL")


async def demo_global_search(oracle: OracleAgent):
    """Demo 4: Global Search - pytania o ogólny obraz."""
    logger.info("=== DEMO 4: Global Search ===")

    questions = [
        "O czym jest wiedza zgromadzona w grafie?",
        "Jakie są główne tematy w grafie wiedzy?",
        "Podsumuj społeczności w grafie wiedzy",
    ]

    for question in questions:
        logger.info(f"\nPytanie: {question}")
        result = await oracle.process(question)
        print(f"\nOdpowiedź:\n{result}\n")
        print("-" * 80)


async def demo_local_search(oracle: OracleAgent):
    """Demo 5: Local Search - multi-hop reasoning."""
    logger.info("=== DEMO 5: Local Search - Multi-Hop Reasoning ===")

    questions = [
        "Jaki jest związek między Pythonem a Guido van Rossum?",
        "Jak Python jest powiązany z Data Science?",
        "Jaka jest ścieżka od Pythona do TensorFlow?",
    ]

    for question in questions:
        logger.info(f"\nPytanie: {question}")
        result = await oracle.process(question)
        print(f"\nOdpowiedź:\n{result}\n")
        print("-" * 80)


async def demo_complex_reasoning(oracle: OracleAgent):
    """Demo 6: Złożone pytanie wymagające multi-hop reasoning."""
    logger.info("=== DEMO 6: Złożone Pytanie ===")

    question = """Wyjaśnij krok po kroku:
    1. Kto stworzył Pythona?
    2. W jakim roku?
    3. Do czego Python jest używany?
    4. Jakie są najważniejsze biblioteki Pythona?
    
    Odpowiedz na podstawie grafu wiedzy, cytując źródła."""

    logger.info(f"\nPytanie złożone:")
    print(question)
    result = await oracle.process(question)
    print(f"\nOdpowiedź:\n{result}\n")


async def demo_graph_stats(oracle: OracleAgent):
    """Demo 7: Sprawdzenie statystyk grafu po wszystkich operacjach."""
    logger.info("=== DEMO 7: Statystyki Grafu ===")

    result = await oracle.process("Pokaż szczegółowe statystyki grafu wiedzy")
    print(f"\n{result}\n")

    # Zapisz graf
    logger.info("Zapisywanie grafu wiedzy...")
    oracle.graph_rag.save_graph()
    logger.info(f"Graf zapisany do: {oracle.graph_rag.graph_file}")


async def main():
    """Główna funkcja demo."""
    print("=" * 80)
    print("VENOM ORACLE AGENT - DEMO")
    print("GraphRAG + Multi-Hop Reasoning + Deep Analysis")
    print("=" * 80)
    print()

    try:
        # Demo 1: Inicjalizacja
        oracle = await demo_oracle_basic()

        # Demo 2: Ingestia pliku
        await demo_ingest_file(oracle)

        # Opcjonalnie: Demo 3 - Ingestia URL (wykomentuj jeśli nie masz internetu)
        # await demo_ingest_url(oracle)

        # Demo 4: Global Search
        await demo_global_search(oracle)

        # Demo 5: Local Search - Multi-Hop Reasoning
        await demo_local_search(oracle)

        # Demo 6: Złożone pytanie
        await demo_complex_reasoning(oracle)

        # Demo 7: Statystyki
        await demo_graph_stats(oracle)

        print("\n" + "=" * 80)
        print("DEMO ZAKOŃCZONE")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Błąd podczas demo: {e}", exc_info=True)
        print(f"\n❌ Błąd: {str(e)}")
        print("\nSprawdź czy:")
        print("1. Masz uruchomiony lokalny LLM (np. Ollama)")
        print("2. Zmienna LLM_LOCAL_ENDPOINT jest poprawnie skonfigurowana")
        print("3. Katalog workspace istnieje")


if __name__ == "__main__":
    asyncio.run(main())
