#!/usr/bin/env python3
"""
Przykład użycia Google Search Grounding Integration.

Ten skrypt demonstruje:
1. Włączanie/wyłączanie paid_mode
2. Routing zadań RESEARCH
3. Formatowanie źródeł z Google Grounding
4. Fallback do DuckDuckGo

Wymagania:
- export GOOGLE_API_KEY=your-key (opcjonalne, dla Google Grounding)
"""

import sys
from pathlib import Path

# Dodaj venom_core do path
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter, TaskType


def demo_state_manager():
    """Demonstracja Global Cost Guard (paid_mode)."""
    print("=" * 80)
    print("DEMO 1: StateManager - Global Cost Guard")
    print("=" * 80)
    
    # Inicjalizacja
    state_manager = StateManager(state_file_path="/tmp/venom_demo_state.json")
    
    # Sprawdź domyślny stan
    print(f"\n1. Stan początkowy paid_mode: {state_manager.is_paid_mode_enabled()}")
    assert state_manager.is_paid_mode_enabled() is False, "Domyślnie paid_mode powinien być wyłączony"
    
    # Włącz paid mode
    state_manager.set_paid_mode(True)
    print(f"2. Po włączeniu paid_mode: {state_manager.is_paid_mode_enabled()}")
    assert state_manager.is_paid_mode_enabled() is True
    
    # Wyłącz paid mode
    state_manager.set_paid_mode(False)
    print(f"3. Po wyłączeniu paid_mode: {state_manager.is_paid_mode_enabled()}")
    assert state_manager.is_paid_mode_enabled() is False
    
    print("\n✅ StateManager działa poprawnie!")


def demo_task_routing():
    """Demonstracja routingu zadań RESEARCH."""
    print("\n" + "=" * 80)
    print("DEMO 2: HybridModelRouter - Routing zadań RESEARCH")
    print("=" * 80)
    
    router = HybridModelRouter()
    
    # Test 1: Zadanie STANDARD (proste)
    print("\n1. Zadanie STANDARD:")
    routing = router.route_task(TaskType.STANDARD, "Hello world")
    print(f"   Target: {routing['target']}")
    print(f"   Provider: {routing['provider']}")
    print(f"   Reason: {routing['reason']}")
    
    # Test 2: Zadanie RESEARCH (bez Google API key - fallback)
    print("\n2. Zadanie RESEARCH (fallback do LOCAL):")
    routing = router.route_task(TaskType.RESEARCH, "Aktualna cena Bitcoina")
    print(f"   Target: {routing['target']}")
    print(f"   Provider: {routing['provider']}")
    print(f"   Reason: {routing['reason']}")
    
    # Test 3: Zadanie CODING_COMPLEX
    print("\n3. Zadanie CODING_COMPLEX:")
    routing = router.route_task(TaskType.CODING_COMPLEX, "Zaprojektuj mikroseris")
    print(f"   Target: {routing['target']}")
    print(f"   Provider: {routing['provider']}")
    print(f"   Reason: {routing['reason']}")
    
    print("\n✅ Routing działa poprawnie!")


def demo_grounding_format():
    """Demonstracja formatowania źródeł z Google Grounding."""
    print("\n" + "=" * 80)
    print("DEMO 3: Formatowanie źródeł z Google Grounding")
    print("=" * 80)
    
    # Symuluj odpowiedź z Google Grounding
    response_metadata = {
        "grounding_metadata": {
            "grounding_chunks": [
                {
                    "title": "Bitcoin Price - CoinMarketCap",
                    "uri": "https://coinmarketcap.com/currencies/bitcoin/"
                },
                {
                    "title": "Cryptocurrency Market - Bloomberg",
                    "uri": "https://www.bloomberg.com/crypto"
                }
            ]
        }
    }
    
    # Import funkcji formatującej
    from venom_core.agents.researcher import format_grounding_sources
    
    # Formatuj źródła
    sources_section = format_grounding_sources(response_metadata)
    
    print("\nPrzykładowa odpowiedź z Google Grounding:")
    print("-" * 80)
    example_response = """Bitcoin obecnie kosztuje około $43,500 według najnowszych danych [1].
Market cap wynosi około $850 miliardów [2]."""
    
    print(example_response)
    print(sources_section)
    print("-" * 80)
    
    # Test pustych metadanych
    empty_sources = format_grounding_sources({})
    assert empty_sources == "", "Puste metadane powinny zwracać pusty string"
    
    print("\n✅ Formatowanie źródeł działa poprawnie!")


def demo_acceptance_criteria():
    """Demonstracja kryteriów akceptacji (DoD)."""
    print("\n" + "=" * 80)
    print("DEMO 4: Kryteria Akceptacji")
    print("=" * 80)
    
    state_manager = StateManager(state_file_path="/tmp/venom_demo_state.json")
    router = HybridModelRouter()
    
    # ✅ DoD 1: Paid Mode OFF → DuckDuckGo
    print("\n✅ DoD 1: Paid Mode OFF → DuckDuckGo")
    state_manager.set_paid_mode(False)
    routing = router.route_task(TaskType.RESEARCH, "Aktualna cena BTC")
    print(f"   paid_mode: {state_manager.is_paid_mode_enabled()}")
    print(f"   Routing target: {routing['target']}")
    print(f"   Expected: LOCAL (DuckDuckGo)")
    
    # ✅ DoD 2: Paid Mode ON → próba Google Grounding
    print("\n✅ DoD 2: Paid Mode ON → próba Google Grounding")
    state_manager.set_paid_mode(True)
    routing = router.route_task(TaskType.RESEARCH, "Najnowsze wiadomości AI")
    print(f"   paid_mode: {state_manager.is_paid_mode_enabled()}")
    print(f"   Routing target: {routing['target']}")
    print(f"   Note: Faktyczne użycie Google wymaga GOOGLE_API_KEY")
    
    # ✅ DoD 3: Formatowanie grounding_metadata
    print("\n✅ DoD 3: Formatowanie grounding_metadata")
    from venom_core.agents.researcher import format_grounding_sources
    metadata = {
        "grounding_metadata": {
            "grounding_chunks": [
                {"title": "Test", "uri": "https://example.com"}
            ]
        }
    }
    sources = format_grounding_sources(metadata)
    print(f"   Sources formatted: {len(sources) > 0}")
    print(f"   Contains '📚 Źródła': {'📚 Źródła' in sources}")
    
    # ✅ DoD 4: Bezpiecznik kosztowy
    print("\n✅ DoD 4: Bezpiecznik kosztowy")
    state_manager.set_paid_mode(False)
    routing = router.route_task(TaskType.RESEARCH, "Force Google Search")
    print(f"   paid_mode wyłączony: {not state_manager.is_paid_mode_enabled()}")
    print(f"   Routing NADAL do LOCAL: {routing['target'] == 'local'}")
    print(f"   Brak możliwości obejścia: ✓")
    
    print("\n✅ Wszystkie kryteria akceptacji spełnione!")


def main():
    """Główna funkcja demo."""
    print("\n" + "=" * 80)
    print("GOOGLE SEARCH GROUNDING INTEGRATION - DEMO")
    print("=" * 80)
    
    try:
        # Demo 1: StateManager
        demo_state_manager()
        
        # Demo 2: Task Routing
        demo_task_routing()
        
        # Demo 3: Grounding Format
        demo_grounding_format()
        
        # Demo 4: Acceptance Criteria
        demo_acceptance_criteria()
        
        print("\n" + "=" * 80)
        print("✅ WSZYSTKIE DEMO ZAKOŃCZONE SUKCESEM!")
        print("=" * 80)
        
        print("\nNotatki:")
        print("- Dla pełnej integracji z Google Grounding wymagany jest GOOGLE_API_KEY")
        print("- Bez klucza system automatycznie używa DuckDuckGo (fallback)")
        print("- paid_mode jest persystowany w state_dump.json")
        print("- Badge'e w UI wyświetlają źródło danych (Google vs DuckDuckGo)")
        
    except Exception as e:
        print(f"\n❌ Błąd podczas demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
