"""Flow and helper routines for Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.flows.code_review import CodeReviewLoop
from venom_core.core.flows.council import CouncilFlow
from venom_core.core.flows.forge import ForgeFlow
from venom_core.core.flows.healing import HealingFlow
from venom_core.core.flows.issue_handler import IssueHandlerFlow
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from uuid import UUID

    from .orchestrator_core import Orchestrator

logger = get_logger(__name__)


async def code_generation_with_review(
    orch: "Orchestrator", task_id: "UUID", user_request: str
) -> str:
    coder = getattr(orch.task_dispatcher, "coder_agent", None)
    critic = getattr(orch.task_dispatcher, "critic_agent", None)

    if coder is None or critic is None:
        logger.warning(
            "TaskDispatcher nie ma zainicjalizowanych agentów coder/critic - używam prostego dispatch"
        )
        return await orch.task_dispatcher.dispatch("CODE_GENERATION", user_request)

    if orch._code_review_loop is None:
        orch._code_review_loop = CodeReviewLoop(
            state_manager=orch.state_manager,
            coder_agent=coder,
            critic_agent=critic,
        )

    return await orch._code_review_loop.execute(task_id, user_request)


def should_use_council(
    orch: "Orchestrator",
    content: str | None = None,
    intent: str = "",
    context: str | None = None,
) -> bool:
    if content is None and context is not None:
        content = context
    content = content or ""

    if orch._council_flow is None:
        orch._council_flow = CouncilFlow(
            state_manager=orch.state_manager,
            task_dispatcher=orch.task_dispatcher,
            event_broadcaster=orch.event_broadcaster,
        )
        orch.flow_router.set_council_flow(orch._council_flow)

    return orch.flow_router.should_use_council(content, intent)


async def run_council(orch: "Orchestrator", task_id: "UUID", context: str) -> str:
    orch.state_manager.add_log(
        task_id, "🏛️ THE COUNCIL: Rozpoczynam tryb Group Chat (Swarm Intelligence)"
    )

    await orch._broadcast_event(
        event_type="COUNCIL_STARTED",
        message="The Council rozpoczyna dyskusję nad zadaniem",
        data={"task_id": str(task_id)},
    )

    try:
        if orch._council_config is None:
            from venom_core.agents.guardian import GuardianAgent
            from venom_core.core.council import CouncilConfig, create_local_llm_config

            coder = getattr(orch.task_dispatcher, "coder_agent", None)
            critic = getattr(orch.task_dispatcher, "critic_agent", None)
            architect = getattr(orch.task_dispatcher, "architect_agent", None)

            guardian = GuardianAgent(kernel=orch.task_dispatcher.kernel)
            try:
                llm_config = create_local_llm_config()
            except Exception as exc:
                # Nie blokuj całego Council przy brakującej konfiguracji endpointu
                # (szczególnie w środowiskach testowych, gdzie sesja jest mockowana).
                logger.warning(
                    "Nie udało się zbudować lokalnej konfiguracji LLM dla Council (%s). "
                    "Używam konfiguracji awaryjnej.",
                    exc,
                )
                llm_config = {
                    "config_list": [
                        {
                            "model": "council-fallback",
                            "base_url": "http://localhost:11434",
                            "api_key": "EMPTY",
                        }
                    ],
                    "temperature": 0.7,
                    "timeout": 120,
                }

            if coder is None or critic is None or architect is None:
                raise RuntimeError(
                    "Brak wymaganych agentów Council (coder/critic/architect)"
                )

            orch._council_config = CouncilConfig(
                coder_agent=coder,
                critic_agent=critic,
                architect_agent=architect,
                guardian_agent=guardian,
                llm_config=llm_config,
            )

        from venom_core.core.council import CouncilSession

        council_tuple = orch._council_config.create_council()
        user_proxy, group_chat, manager = orch._normalize_council_tuple(council_tuple)

        session = CouncilSession(user_proxy, group_chat, manager)

        members = []
        if group_chat is not None and getattr(group_chat, "agents", None):
            members = [
                getattr(agent, "name", str(agent)) for agent in group_chat.agents
            ]

        await orch._broadcast_event(
            event_type="COUNCIL_MEMBERS",
            message=f"Council składa się z {len(members)} członków",
            data={"task_id": str(task_id), "members": members},
        )

        result = await session.run(context)

        get_message_count = getattr(session, "get_message_count", lambda: 0)
        get_speakers = getattr(session, "get_speakers", lambda: members)
        message_count = get_message_count()
        speakers = get_speakers() or members

        orch.state_manager.add_log(
            task_id,
            (
                "🏛️ THE COUNCIL: Dyskusja zakończona - "
                f"{message_count} wiadomości, uczestnicy: {', '.join(speakers)}"
            ),
        )

        await orch._broadcast_event(
            event_type="COUNCIL_COMPLETED",
            message=f"Council zakończył dyskusję po {message_count} wiadomościach",
            data={
                "task_id": str(task_id),
                "message_count": message_count,
                "speakers": speakers,
            },
        )

        logger.info("Council zakończył zadanie %s", task_id)
        return result

    except Exception as exc:
        error_msg = f"❌ Błąd podczas działania Council: {exc}"
        logger.error(error_msg)

        orch.state_manager.add_log(task_id, error_msg)

        await orch._broadcast_event(
            event_type="COUNCIL_ERROR",
            message=error_msg,
            data={"task_id": str(task_id), "error": str(exc)},
        )

        logger.warning("Council zawiódł - powrót do standardowego flow")
        return f"Council mode nie powiódł się: {exc}"


async def execute_healing_cycle(
    orch: "Orchestrator", task_id: "UUID", test_path: str = "."
) -> dict:
    if orch._healing_flow is None:
        orch._healing_flow = HealingFlow(
            state_manager=orch.state_manager,
            task_dispatcher=orch.task_dispatcher,
            event_broadcaster=orch.event_broadcaster,
        )

    return await orch._healing_flow.execute(task_id, test_path)


async def execute_forge_workflow(
    orch: "Orchestrator", task_id: "UUID", tool_specification: str, tool_name: str
) -> dict:
    if orch._forge_flow is None:
        orch._forge_flow = ForgeFlow(
            state_manager=orch.state_manager,
            task_dispatcher=orch.task_dispatcher,
            event_broadcaster=orch.event_broadcaster,
        )

    return await orch._forge_flow.execute(task_id, tool_specification, tool_name)


async def handle_remote_issue(orch: "Orchestrator", issue_number: int) -> dict:
    if orch._issue_handler_flow is None:
        orch._issue_handler_flow = IssueHandlerFlow(
            state_manager=orch.state_manager,
            task_dispatcher=orch.task_dispatcher,
            event_broadcaster=orch.event_broadcaster,
        )

    return await orch._issue_handler_flow.execute(issue_number)


async def execute_campaign_mode(
    orch: "Orchestrator", goal_store=None, max_iterations: int = 10
) -> dict:
    if orch._campaign_flow is None:
        orch._campaign_flow = CampaignFlow(
            state_manager=orch.state_manager,
            orchestrator_submit_task=orch.submit_task,
            event_broadcaster=orch.event_broadcaster,
        )

    return await orch._campaign_flow.execute(goal_store, max_iterations)


async def generate_help_response(orch: "Orchestrator", task_id: "UUID") -> str:
    try:
        agent_map = orch.task_dispatcher.agent_map
        kernel = orch.task_dispatcher.kernel
        plugins = getattr(kernel, "plugins", None)

        help_text = """# 🕷️ Venom - System Pomocy

## Dostępne Możliwości

Jestem Venom - wieloagentowy system AI wspierający rozwój oprogramowania. Oto co mogę dla Ciebie zrobić:

### 🤖 Dostępni Agenci

"""

        agent_descriptions = {
            "CODE_GENERATION": "💻 **Coder** - Generowanie, refaktoryzacja i naprawa kodu",
            "RESEARCH": "🔍 **Researcher** - Wyszukiwanie aktualnych informacji w Internecie",
            "KNOWLEDGE_SEARCH": "📚 **Professor** - Odpowiedzi na pytania o wiedzę i technologie",
            "COMPLEX_PLANNING": "🏗️ **Architect** - Projektowanie złożonych systemów i aplikacji",
            "VERSION_CONTROL": "🌿 **Git Master** - Zarządzanie gałęziami, commitami i synchronizacją",
            "E2E_TESTING": "🧪 **Tester** - Testowanie aplikacji webowych end-to-end",
            "DOCUMENTATION": "📖 **Publisher** - Generowanie i publikacja dokumentacji",
            "RELEASE_PROJECT": "🚀 **Release Manager** - Zarządzanie wydaniami i changelog",
            "STATUS_REPORT": "📊 **Executive** - Raportowanie statusu i postępu projektu",
            "GENERAL_CHAT": "💬 **Assistant** - Ogólna konwersacja i wsparcie",
        }

        for intent, description in agent_descriptions.items():
            if intent in agent_map:
                help_text += f"- {description}\n"

        help_text += """
### 🎯 Tryby Pracy

- **🏛️ The Council** - Autonomiczna współpraca agentów dla złożonych projektów
- **🚀 Tryb Kampanii** - Automatyczna realizacja roadmapy projektu
- **🔄 Pętla Samonaprawy** - Automatyczne testowanie i naprawianie kodu

### 🛠️ Umiejętności (Skills)

"""

        if plugins is not None:
            skill_count = 0
            for plugin_name in plugins:
                if is_public_plugin(plugin_name):
                    skill_count += 1
                    help_text += f"- **{plugin_name}**\n"

            if skill_count == 0:
                help_text += "- Trwa ładowanie umiejętności...\n"
        else:
            help_text += "- Podstawowe umiejętności: manipulacja plikami, Git, shell, research, renderowanie\n"

        help_text += """
### 💡 Przykłady Użycia

**Generowanie kodu:**
```
Napisz funkcję w Pythonie do sortowania listy
```

**Research:**
```
Znajdź najnowsze informacje o FastAPI 0.100
```

**Projekt aplikacji:**
```
Stwórz aplikację webową z FastAPI i React
```

**Git:**
```
Utwórz nowy branch feat/new-feature
```

**Dokumentacja:**
```
Wygeneruj dokumentację projektu
```

### ℹ️ Dodatkowe Informacje

- Wspieramy lokalne modele (Ollama) oraz API chmurowe (OpenAI, Azure)
- Automatyczne zarządzanie pamięcią i uczenie się z błędów
- Integracja z GitHub, Docker i systemami CI/CD
- Voice interface (gdy włączony)
- Distributed execution (tryb Nexus)

**Potrzebujesz pomocy?** Zapytaj o konkretną funkcjonalność lub wyślij zadanie do wykonania!
"""

        if orch.event_broadcaster:
            await orch._broadcast_event(
                event_type="RENDER_WIDGET",
                message="Wyświetlam system pomocy",
                data={
                    "widget": {
                        "id": f"help-{task_id}",
                        "type": "markdown",
                        "data": {"content": help_text},
                    }
                },
            )

        return help_text

    except Exception as exc:
        logger.error("Błąd podczas generowania pomocy: %s", exc)
        return (
            "Wystąpił błąd podczas generowania pomocy. "
            "Spróbuj ponownie lub skontaktuj się z administratorem."
        )


def is_public_plugin(plugin_name: str) -> bool:
    return not (plugin_name.startswith("_") or "internal" in plugin_name.lower())
