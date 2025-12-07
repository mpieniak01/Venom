"""
Przykład użycia zewnętrznych integracji (GitHub + Discord).

Ten przykład pokazuje jak Venom może automatycznie obsługiwać Issues z GitHub
i tworzyć Pull Requesty z powiadomieniami na Discord.

UWAGA: Aby uruchomić ten przykład, potrzebujesz:
1. Skonfigurować .env z tokenami (GITHUB_TOKEN, DISCORD_WEBHOOK_URL)
2. Mieć zainstalowane wszystkie zależności z requirements.txt
3. Uruchomić lokalnie (nie w Docker - wymaga dostępu do SSH keys)
"""

import asyncio

from venom_core.config import SETTINGS
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.execution.skills.platform_skill import PlatformSkill


async def example_check_github_connection():
    """Przykład 1: Sprawdzenie połączenia z GitHub i Discord."""
    print("=" * 60)
    print("Przykład 1: Sprawdzenie połączenia z platformami")
    print("=" * 60)

    skill = PlatformSkill()
    status = skill.check_connection()

    print("\nStatus połączenia:")
    print(f"GitHub: {'✅' if status['github'].get('connected') else '❌'}")
    print(f"  - Configured: {'✅' if status['github']['configured'] else '❌'}")
    print(f"Discord: {'✅' if status['discord']['configured'] else '❌'}")
    print(f"Slack: {'✅' if status['slack']['configured'] else '❌'}")


async def example_list_issues():
    """Przykład 2: Pobieranie listy Issues z GitHub."""
    print("\n" + "=" * 60)
    print("Przykład 2: Pobieranie Issues z GitHub")
    print("=" * 60)

    skill = PlatformSkill()
    result = await skill.get_assigned_issues(state="open")

    print(f"\n{result}")


async def example_get_issue_details():
    """Przykład 3: Pobieranie szczegółów konkretnego Issue."""
    print("\n" + "=" * 60)
    print("Przykład 3: Szczegóły Issue")
    print("=" * 60)

    # Zmień numer na istniejący w Twoim repo
    issue_number = 1

    skill = PlatformSkill()
    result = await skill.get_issue_details(issue_number=issue_number)

    print(f"\n{result}")


async def example_send_notification():
    """Przykład 4: Wysłanie powiadomienia na Discord."""
    print("\n" + "=" * 60)
    print("Przykład 4: Wysłanie powiadomienia na Discord")
    print("=" * 60)

    skill = PlatformSkill()

    message = """
🤖 **Venom Status Update**

✅ System działa poprawnie
📊 Aktywne zadania: 0
🔧 Ostatnia synchronizacja: OK

---
*Wiadomość z Venom External Integrations Example*
    """.strip()

    result = await skill.send_notification(message=message, channel="discord")

    print(f"\n{result}")


async def example_handle_issue_workflow():
    """Przykład 5: Kompletny workflow obsługi Issue (wymaga skonfigurowanego Orchestratora)."""
    print("\n" + "=" * 60)
    print("Przykład 5: Workflow Issue-to-PR (ZAAWANSOWANE)")
    print("=" * 60)

    # UWAGA: Ten przykład wymaga pełnego setupu Orchestratora z wszystkimi agentami
    print("\nTen przykład wymaga pełnego setupu Venoma z wszystkimi agentami.")
    print("Poniżej pseudokod workflow:")

    print(
        """
    # 1. Inicjalizuj Orchestrator
    state_manager = StateManager()
    orchestrator = Orchestrator(state_manager)

    # 2. Obsłuż Issue
    result = await orchestrator.handle_remote_issue(issue_number=42)

    # 3. Sprawdź wynik
    if result["success"]:
        print(f"✅ Issue #{result['issue_number']} obsłużone!")
        print(f"Pull Request utworzony: {result['message']}")
    else:
        print(f"❌ Błąd: {result['message']}")
    """
    )


async def example_manual_pr_creation():
    """Przykład 6: Ręczne utworzenie Pull Requesta."""
    print("\n" + "=" * 60)
    print("Przykład 6: Ręczne utworzenie Pull Requesta")
    print("=" * 60)

    # UWAGA: Zmień na nazwę istniejącego brancha w Twoim repo
    branch_name = "example-branch"
    pr_title = "feat: add example feature"
    pr_body = """
## Opis zmian

To jest przykładowy Pull Request utworzony przez Venom PlatformSkill.

## Zmiany
- ✅ Dodano nową funkcjonalność
- ✅ Zaktualizowano dokumentację
- ✅ Dodano testy

## Testy
Wszystkie testy przeszły pomyślnie.

Closes #123
    """.strip()

    skill = PlatformSkill()

    print(f"\nTworzę PR z brancha '{branch_name}'...")
    print("(To tylko przykład - zamień na istniejący branch)")

    # Odkomentuj aby faktycznie utworzyć PR:
    # result = await skill.create_pull_request(
    #     branch=branch_name,
    #     title=pr_title,
    #     body=pr_body,
    #     base="main"
    # )
    # print(f"\n{result}")

    print("\n❌ Przykład wyłączony - odkomentuj kod aby utworzyć PR")


async def example_comment_on_issue():
    """Przykład 7: Dodanie komentarza do Issue."""
    print("\n" + "=" * 60)
    print("Przykład 7: Komentarz w Issue")
    print("=" * 60)

    # UWAGA: Zmień na numer istniejącego Issue
    issue_number = 1

    comment_text = """
🤖 **Venom Bot Update**

Issue zostało przeanalizowane i dodane do kolejki.

**Status:** W trakcie analizy
**Priorytet:** Normalny
**ETA:** 2-3 dni robocze

---
*Komentarz dodany automatycznie przez Venom*
    """.strip()

    skill = PlatformSkill()

    print(f"\nDodaję komentarz do Issue #{issue_number}...")
    print("(To tylko przykład - zamień na istniejący Issue)")

    # Odkomentuj aby faktycznie dodać komentarz:
    # result = await skill.comment_on_issue(
    #     issue_number=issue_number,
    #     text=comment_text
    # )
    # print(f"\n{result}")

    print("\n❌ Przykład wyłączony - odkomentuj kod aby dodać komentarz")


async def main():
    """Uruchamia wszystkie przykłady."""
    print("🤖 Venom External Integrations - Przykłady użycia\n")

    # Sprawdź konfigurację
    if not SETTINGS.GITHUB_TOKEN:
        print("⚠️  UWAGA: GITHUB_TOKEN nie jest skonfigurowany w .env")
        print("Niektóre przykłady mogą nie działać.\n")

    try:
        # Przykład 1: Sprawdzenie połączenia
        await example_check_github_connection()

        # Przykład 2: Lista Issues
        await example_list_issues()

        # Przykład 3: Szczegóły Issue (odkomentuj jeśli masz Issues)
        # await example_get_issue_details()

        # Przykład 4: Powiadomienie (odkomentuj jeśli masz DISCORD_WEBHOOK_URL)
        # await example_send_notification()

        # Przykład 5: Workflow Issue-to-PR
        await example_handle_issue_workflow()

        # Przykład 6: Ręczne PR
        await example_manual_pr_creation()

        # Przykład 7: Komentarz
        await example_comment_on_issue()

        print("\n" + "=" * 60)
        print("✅ Przykłady zakończone")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Błąd podczas wykonywania przykładów: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Uruchom przykłady
    asyncio.run(main())
