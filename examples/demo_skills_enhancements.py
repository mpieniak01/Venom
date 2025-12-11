"""
Demonstracja ulepszeń narzędzi (Skills Enhancements) - Venom v2.0

Ten skrypt pokazuje nowe funkcjonalności:
1. FileSkill - rekurencyjne listowanie katalogów
2. BrowserSkill - automatyczne screenshoty po akcjach
3. PlatformSkill - raport konfiguracji
4. WebSkill - integracja z Tavily AI Search
"""

import asyncio
import tempfile


async def demo_file_skill_recursive():
    """Demonstracja rekurencyjnego listowania w FileSkill."""
    print("\n" + "=" * 70)
    print("1. FileSkill - Rekurencyjne listowanie katalogów")
    print("=" * 70)
    
    from venom_core.execution.skills.file_skill import FileSkill
    
    # Utwórz tymczasowy workspace z zagnieżdżoną strukturą
    with tempfile.TemporaryDirectory() as tmpdir:
        skill = FileSkill(workspace_root=tmpdir)
        
        # Utwórz przykładową strukturę
        await skill.write_file("root_file.txt", "Plik w root")
        await skill.write_file("dir1/file1.txt", "Plik w dir1")
        await skill.write_file("dir1/dir2/file2.txt", "Plik w dir2")
        await skill.write_file("dir1/dir2/dir3/file3.txt", "Plik w dir3")
        
        print("\n📁 Listowanie płaskie (recursive=False):")
        print("-" * 70)
        result = skill.list_files(".", recursive=False)
        print(result)
        
        print("\n📁 Listowanie rekurencyjne (recursive=True, max 3 poziomy):")
        print("-" * 70)
        result = skill.list_files(".", recursive=True)
        print(result)


async def demo_browser_skill_screenshots():
    """Demonstracja automatycznych screenshotów w BrowserSkill."""
    print("\n" + "=" * 70)
    print("2. BrowserSkill - Automatyczne screenshoty po akcjach")
    print("=" * 70)
    
    from venom_core.execution.skills.browser_skill import BrowserSkill
    
    skill = BrowserSkill()
    
    print("\n📸 Nowa funkcjonalność:")
    print("- click_element() automatycznie wykonuje screenshot po kliknięciu")
    print("- fill_form() automatycznie wykonuje screenshot po wypełnieniu")
    print("- Screenshoty służą do weryfikacji czy akcja zadziałała (React, Vue, etc.)")
    print("\n⚠️  W środowisku bez przeglądarki pokazujemy tylko interfejs:")
    print(f"   Przykładowy katalog screenshotów: {skill.screenshots_dir}")
    
    # Przykładowe wywołanie (wymaga działającej przeglądarki)
    print("\n💡 Przykład użycia:")
    print("""
    # Kliknięcie w przycisk
    result = await skill.click_element("#submit-button")
    # Zwróci: "✅ Kliknięto w element: #submit-button"
    #         "Zrzut ekranu weryfikacyjny: /path/to/click_verification_1234567890.png"
    
    # Wypełnienie formularza
    result = await skill.fill_form("#email", "user@example.com")
    # Zwróci: "✅ Wypełniono pole: #email"
    #         "Zrzut ekranu weryfikacyjny: /path/to/fill_verification_1234567890.png"
    """)


def demo_platform_skill_config_status():
    """Demonstracja raportu konfiguracji w PlatformSkill."""
    print("\n" + "=" * 70)
    print("3. PlatformSkill - Raport konfiguracji")
    print("=" * 70)
    
    from venom_core.execution.skills.platform_skill import PlatformSkill
    
    skill = PlatformSkill()
    
    print("\n🔧 Raport dostępnych integracji:")
    print("-" * 70)
    
    # Wywołaj nową metodę
    result = skill.get_configuration_status()
    print(result)
    
    print("\n💡 Agent może teraz sprawdzić co jest skonfigurowane przed użyciem!")


def demo_web_skill_tavily():
    """Demonstracja integracji Tavily w WebSkill."""
    print("\n" + "=" * 70)
    print("4. WebSkill - Integracja z Tavily AI Search")
    print("=" * 70)
    
    from venom_core.execution.skills.web_skill import WebSearchSkill
    
    skill = WebSearchSkill()
    
    if skill.tavily_client:
        print("\n✅ Tavily AI Search jest AKTYWNY")
        print("   - Wyszukiwanie zwraca gotową odpowiedź AI")
        print("   - Brak śmieci HTML")
        print("   - Wyższa jakość kontekstu dla LLM")
    else:
        print("\n⚠️  Tavily nie jest skonfigurowany (brak TAVILY_API_KEY)")
        print("   - Używam DuckDuckGo jako fallback")
        print("   - Aby włączyć Tavily: dodaj TAVILY_API_KEY do .env")
    
    print("\n💡 Przykład użycia:")
    print("""
    # Z Tavily (gdy skonfigurowany):
    result = skill.search("What is Python?")
    # Zwróci:
    # - 📋 Podsumowanie AI: "Python is a high-level programming language..."
    # - 🔍 Źródła (5): lista czystych, przetworzonych wyników
    
    # Z DuckDuckGo (fallback):
    result = skill.search("What is Python?")
    # Zwróci: tradycyjne wyniki wyszukiwania z tytułami i snippetami
    """)
    
    print("\n🎯 Konfiguracja:")
    print("   1. Utwórz konto na https://tavily.com")
    print("   2. Dodaj do .env: TAVILY_API_KEY=tvly-xxx...")
    print("   3. Restart Venoma")


async def main():
    """Główna funkcja demonstracyjna."""
    print("\n" + "=" * 70)
    print("🐍 VENOM v2.0 - Demonstracja Ulepszeń Narzędzi")
    print("=" * 70)
    
    # Demonstracje
    await demo_file_skill_recursive()
    await demo_browser_skill_screenshots()
    demo_platform_skill_config_status()
    demo_web_skill_tavily()
    
    print("\n" + "=" * 70)
    print("✅ Demonstracja zakończona!")
    print("=" * 70)
    print("\n💡 Wszystkie nowe funkcje są dostępne dla agentów przez Semantic Kernel")
    print("   i mogą być automatycznie używane przez LLM przy wykonywaniu zadań.\n")


if __name__ == "__main__":
    asyncio.run(main())
