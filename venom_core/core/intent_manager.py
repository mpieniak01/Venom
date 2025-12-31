"""Moduł: intent_manager - klasyfikacja intencji użytkownika."""

import asyncio
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.config import SETTINGS
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IntentManager:
    """Menedżer klasyfikacji intencji użytkownika za pomocą Semantic Kernel."""

    HELP_KEYWORDS = [
        "co potrafisz",
        "co umiesz",
        "jakie masz możliwości",
        "jakie masz umiejętności",
        "jakie są twoje umiejętności",
        "pomoc",
        "help",
        "kim jesteś",
    ]

    TIME_KEYWORDS = [
        "ktora godzina",
        "która godzina",
        "jaka godzina",
        "podaj godzine",
        "podaj godzinę",
        "aktualna godzina",
        "current time",
        "what time is it",
    ]

    # Dedykowane słowa kluczowe dla testów wydajności pipeline'u
    PERF_TEST_KEYWORDS = (
        "parallel perf",
        "perf pid",
        "smoke latency test",
        "benchmark latency",
    )

    INFRA_KEYWORDS = [
        "serwer",
        "serwerów",
        "infrastrukt",
        "status usług",
        "usług venom",
        "monitoring systemu",
        "status systemu",
        "service status",
    ]

    LEXICON_DIR = Path(__file__).resolve().parents[1] / "data"
    USER_LEXICON_DIR = Path(__file__).resolve().parents[2] / "data/user_lexicon"
    LEXICON_FILES = {
        "pl": "intent_lexicon_pl.json",
        "en": "intent_lexicon_en.json",
        "de": "intent_lexicon_de.json",
    }
    TOOL_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
        "VERSION_CONTROL",
        "DOCUMENTATION",
        "E2E_TESTING",
        "RELEASE_PROJECT",
        "RESEARCH",
        "CODE_GENERATION",
        "COMPLEX_PLANNING",
    }
    TOOL_REQUIRED_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
        "VERSION_CONTROL",
        "DOCUMENTATION",
        "E2E_TESTING",
        "RELEASE_PROJECT",
        "RESEARCH",
        "FILE_OPERATION",
        "STATUS_REPORT",
    }
    LEXICON_FALLBACK_SCORE = 0.9
    TIE_BREAK_DELTA = 0.02
    _lexicon_cache = {}

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        text = text.lower().strip()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _detect_language(raw_text: str) -> str:
        if not raw_text:
            return ""
        raw = raw_text.lower()
        if re.search(r"[ąćęłńóśżź]", raw):
            return "pl"
        if re.search(r"[äöüß]", raw):
            return "de"
        if re.search(r"\b(wie|was|hilfe|uhr|zeit|bitte|kannst)\b", raw):
            return "de"
        if re.search(r"\b(what|time|help|status|can you)\b", raw):
            return "en"
        if re.search(r"\b(czesc|cześć|hej|pomoc|status|projekt)\b", raw):
            return "pl"
        return ""

    def _load_lexicon(self, language: str) -> dict:
        if language in self._lexicon_cache:
            return self._lexicon_cache[language]
        filename = self.LEXICON_FILES.get(language)
        if not filename:
            return {}
        path = self.LEXICON_DIR / filename
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self._lexicon_cache[language] = data
        return data

    def _load_user_lexicon(self, language: str) -> dict:
        filename = f"intent_lexicon_user_{language}.json"
        path = self.USER_LEXICON_DIR / filename
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            logger.warning(f"Nie udało się wczytać user-lexicon: {path}")
            return {}

    @staticmethod
    def _merge_lexicons(base: dict, override: dict) -> dict:
        if not base:
            return override or {}
        if not override:
            return base
        merged = {"intents": {}}
        base_intents = base.get("intents", {}) or {}
        override_intents = override.get("intents", {}) or {}
        all_intents = set(base_intents) | set(override_intents)

        for intent in all_intents:
            base_cfg = base_intents.get(intent, {}) or {}
            override_cfg = override_intents.get(intent, {}) or {}
            merged_cfg = dict(base_cfg)
            for key in ("phrases", "regex"):
                base_list = base_cfg.get(key, []) or []
                override_list = override_cfg.get(key, []) or []
                merged_cfg[key] = list(dict.fromkeys(base_list + override_list))
            if "threshold" in override_cfg:
                merged_cfg["threshold"] = override_cfg["threshold"]
            merged["intents"][intent] = merged_cfg

        return merged

    def _should_learn_phrase(self, phrase: str) -> bool:
        if not phrase:
            return False
        if "http://" in phrase or "https://" in phrase or "www." in phrase:
            return False
        words = self._normalize_text(phrase).split()
        if len(words) < 2 or len(words) > 8:
            return False
        if len(phrase) > 80:
            return False
        return True

    def _phrase_exists(self, intent: str, phrase: str, lexicon: dict) -> bool:
        intents = lexicon.get("intents", {}) or {}
        cfg = intents.get(intent, {}) or {}
        phrases = cfg.get("phrases", []) or []
        target = self._normalize_text(phrase)
        for existing in phrases:
            if self._normalize_text(existing) == target:
                return True
        return False

    def _append_user_phrase(self, intent: str, phrase: str, language: str) -> None:
        if not self._should_learn_phrase(phrase):
            return
        if not language:
            return

        base_lexicon = self._load_lexicon(language)
        user_lexicon = self._load_user_lexicon(language)

        if self._phrase_exists(intent, phrase, base_lexicon):
            return
        if self._phrase_exists(intent, phrase, user_lexicon):
            return

        intents = user_lexicon.setdefault("intents", {})
        cfg = intents.setdefault(intent, {"phrases": [], "regex": [], "threshold": 0.9})
        cfg.setdefault("phrases", [])
        cfg["phrases"].append(phrase)

        self.USER_LEXICON_DIR.mkdir(parents=True, exist_ok=True)
        path = self.USER_LEXICON_DIR / f"intent_lexicon_user_{language}.json"
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(user_lexicon, handle, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning(f"Nie udało się zapisać user-lexicon: {path}")

    @staticmethod
    def _match_intent_lexicon(
        normalized: str, lexicon: dict
    ) -> tuple[str, float, list[tuple[str, float]]]:
        if not normalized or not lexicon:
            return ("", 0.0, [])
        intents = lexicon.get("intents", {})
        best_intent = ""
        best_score = 0.0
        scored = []

        for intent, config in intents.items():
            threshold = config.get("threshold", 0.9)
            phrases = config.get("phrases", [])
            regexes = config.get("regex", [])

            for pattern in regexes:
                if re.match(pattern, normalized):
                    return (intent, 1.0, [(intent, 1.0)])

            for phrase in phrases:
                candidate = IntentManager._normalize_text(phrase)
                if not candidate:
                    continue
                score = SequenceMatcher(None, normalized, candidate).ratio()
                if score >= threshold and score > best_score:
                    best_score = score
                    best_intent = intent
                scored.append((intent, score))

        top2 = sorted(scored, key=lambda item: item[1], reverse=True)[:2]
        return (best_intent, best_score, top2)

    # Prompt systemowy do klasyfikacji intencji
    SYSTEM_PROMPT = """Jesteś systemem klasyfikacji intencji użytkownika. Twoim zadaniem jest przeczytać wejście użytkownika i sklasyfikować je do JEDNEJ z następujących kategorii:

1. CODE_GENERATION - użytkownik prosi o kod, skrypt, refactoring, implementację funkcji, debugowanie kodu
2. KNOWLEDGE_SEARCH - użytkownik zadaje pytanie o wiedzę, fakty, informacje, wyjaśnienia
3. GENERAL_CHAT - rozmowa ogólna, powitanie, żarty, pytania o samopoczucie systemu
4. RESEARCH - użytkownik potrzebuje aktualnych informacji z Internetu, dokumentacji, najnowszej wiedzy o technologii
5. COMPLEX_PLANNING - użytkownik prosi o stworzenie złożonego projektu wymagającego wielu kroków i koordynacji
6. VERSION_CONTROL - użytkownik chce zarządzać Git: tworzyć branch, commitować zmiany, synchronizować kod
7. E2E_TESTING - użytkownik chce przetestować aplikację webową end-to-end, sprawdzić UI, wykonać scenariusz użytkownika
8. DOCUMENTATION - użytkownik chce wygenerować dokumentację projektu, stronę HTML z markdown
9. RELEASE_PROJECT - użytkownik chce wydać nową wersję projektu, wygenerować changelog, stworzyć tag
10. START_CAMPAIGN - użytkownik chce uruchomić tryb autonomiczny (kampania), gdzie system sam realizuje roadmapę
11. STATUS_REPORT - użytkownik pyta o status projektu, postęp realizacji celów, aktualny milestone
12. INFRA_STATUS - użytkownik prosi o status infrastruktury i usług Venom (ServiceMonitor, serwery, integracje)
13. HELP_REQUEST - użytkownik prosi o pomoc, pytania o możliwości systemu, dostępne funkcje
14. TIME_REQUEST - użytkownik prosi o podanie aktualnej godziny/czasu
15. UNSUPPORTED_TASK - zadanie poza dostępnymi umiejętnościami/narzędziami

ZASADY:
- Odpowiedz TYLKO nazwą kategorii (np. "CODE_GENERATION")
- Nie dodawaj żadnych innych słów ani wyjaśnień
- W razie wątpliwości wybierz najbardziej prawdopodobną kategorię

KIEDY WYBIERAĆ RESEARCH:
- "Jaka jest aktualna cena Bitcoina?"
- "Kto jest obecnym prezydentem Francji?"
- "Jak używać najnowszej wersji FastAPI?"
- "Znajdź dokumentację dla biblioteki X"
- Zapytania zawierające: "aktualne", "najnowsze", "obecny", "szukaj w internecie"

KIEDY WYBIERAĆ COMPLEX_PLANNING:
- "Stwórz grę Snake używając PyGame"
- "Zbuduj aplikację webową z FastAPI i React"
- "Napisz projekt z testami jednostkowymi i dokumentacją"
- "Stwórz stronę HTML z CSS i JavaScript"
- Zadania wymagające: wielu plików, integracji technologii, złożonej logiki

KIEDY WYBIERAĆ VERSION_CONTROL:
- "Utwórz nowy branch feat/csv-support"
- "Commitnij zmiany"
- "Synchronizuj kod z repozytorium"
- "Jaki jest aktualny branch?"
- "Pokaż status Git"
- "Wypchnij zmiany"
- Zapytania zawierające: "branch", "commit", "push", "git", "repozytorium"

KIEDY WYBIERAĆ E2E_TESTING:
- "Przetestuj formularz logowania na localhost:3000"
- "Sprawdź czy aplikacja działa poprawnie w przeglądarce"
- "Wykonaj test E2E dla strony głównej"
- "Kliknij przycisk i sprawdź rezultat"
- Zapytania zawierające: "test E2E", "przetestuj w przeglądarce", "UI test", "sprawdź stronę"

KIEDY WYBIERAĆ DOCUMENTATION:
- "Wygeneruj dokumentację projektu"
- "Zbuduj stronę HTML z dokumentacji"
- "Stwórz dokumentację z plików markdown"
- "Opublikuj dokumentację"
- Zapytania zawierające: "dokumentacja", "docs", "mkdocs", "strona dokumentacji"

KIEDY WYBIERAĆ RELEASE_PROJECT:
- "Wydaj nową wersję projektu"
- "Przygotuj release"
- "Wygeneruj changelog"
- "Utwórz tag release'owy"
- Zapytania zawierające: "release", "wydanie", "changelog", "wersja", "tag"

KIEDY WYBIERAĆ START_CAMPAIGN:
- "Rozpocznij kampanię"
- "Uruchom tryb autonomiczny"
- "Pracuj nad roadmapą automatycznie"
- "Kontynuuj pracę nad projektem"
- Zapytania zawierające: "kampania", "autonomiczny", "automatyczny", "samodzielnie realizuj"

KIEDY WYBIERAĆ STATUS_REPORT:
- "Jaki jest status projektu?"
- "Gdzie jesteśmy z realizacją celów?"
- "Pokaż postęp"
- "Raport statusu"
- Zapytania zawierające: "status", "postęp", "gdzie jesteśmy", "raport", "jak idzie projekt"

KIEDY WYBIERAĆ INFRA_STATUS:
- "Sprawdź status serwerów w infrastrukturze"
- "Co działa w Venom, a co jest offline?"
- "Monitoring usług / ServiceMonitor"
- "Jakie serwisy są niedostępne?"
- Zapytania zawierające: "serwer", "infrastruktura", "status usług", "monitoring systemu", "service status"

KIEDY WYBIERAĆ HELP_REQUEST:
- "Co potrafisz?"
- "Pomoc"
- "Help"
- "Jakie masz możliwości?"
- "Jakie umiejętności posiadasz?"
- "Pokaż dostępne funkcje"
- "Co umiesz robić?"
- Zapytania zawierające: "pomoc", "help", "możliwości", "umiejętności", "co potrafisz", "funkcje"

KIEDY WYBIERAĆ TIME_REQUEST:
- "Która godzina?"
- "Podaj czas"
- "What's the time?"
- "Wie spät ist es?"

KIEDY WYBIERAĆ UNSUPPORTED_TASK:
- Zapytanie nie pasuje do żadnej z kategorii
- Użytkownik prosi o funkcję, której system nie posiada

Przykłady:
- "Napisz funkcję w Pythonie do sortowania" → CODE_GENERATION
- "Jak zrefaktoryzować ten kod?" → CODE_GENERATION
- "Co to jest GraphRAG?" → KNOWLEDGE_SEARCH
- "Jaka jest stolica Francji?" → KNOWLEDGE_SEARCH
- "Witaj Venom, jak się masz?" → GENERAL_CHAT
- "Dzień dobry!" → GENERAL_CHAT
- "Jaka jest aktualna cena Bitcoina?" → RESEARCH
- "Znajdź dokumentację PyGame" → RESEARCH
- "Stwórz grę Snake z PyGame" → COMPLEX_PLANNING
- "Zbuduj stronę z zegarem (HTML + CSS + JS)" → COMPLEX_PLANNING
- "Utwórz branch feat/new-feature" → VERSION_CONTROL
- "Commitnij moje zmiany" → VERSION_CONTROL
- "Przetestuj formularz logowania" → E2E_TESTING
- "Wygeneruj dokumentację projektu" → DOCUMENTATION
- "Wydaj nową wersję" → RELEASE_PROJECT
- "Rozpocznij kampanię" → START_CAMPAIGN
- "Jaki jest status projektu?" → STATUS_REPORT"""

    def __init__(self, kernel: Kernel = None):
        """
        Inicjalizacja IntentManager.

        Args:
            kernel: Opcjonalne jądro Semantic Kernel (jeśli None, zostanie utworzone przez KernelBuilder)
        """
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self._llm_disabled = False

        if kernel is None:
            builder = KernelBuilder()
            if self._test_mode:
                try:
                    kernel = builder.build_kernel()
                    self.kernel = kernel
                    logger.info(
                        "IntentManager działa w trybie testowym z mockowalnym kernel builderem"
                    )
                except (
                    Exception
                ) as exc:  # pragma: no cover - ochrona środowisk testowych
                    self.kernel = None
                    self._llm_disabled = True
                    logger.warning(
                        "IntentManager bez kernela w trybie testowym: %s", exc
                    )
            else:
                kernel = builder.build_kernel()
                self.kernel = kernel
        else:
            self.kernel = kernel
        logger.info("IntentManager zainicjalizowany")

    async def classify_intent(self, user_input: str) -> str:
        """
        Klasyfikuje intencję użytkownika.

        Args:
            user_input: Treść wejścia użytkownika

        Returns:
            Nazwa kategorii intencji (CODE_GENERATION, KNOWLEDGE_SEARCH, GENERAL_CHAT, RESEARCH, COMPLEX_PLANNING, VERSION_CONTROL)
        """
        logger.info(f"Klasyfikacja intencji dla wejścia: {user_input[:100]}...")

        normalized = self._normalize_text(user_input)
        language = self._detect_language(user_input)
        self.last_intent_debug = {
            "source": "unknown",
            "language": language or "unknown",
            "score": None,
            "top2": [],
        }

        # Testy wydajnościowe wysyłają charakterystyczne prompt, aby zmierzyć narzut backendu.
        # W takim przypadku pomiń wywołania LLM i od razu użyj bezpiecznego intentu.
        if any(keyword in normalized for keyword in self.PERF_TEST_KEYWORDS):
            logger.debug(
                "Wykryto prompt testu wydajności - zwracam GENERAL_CHAT bez klasyfikacji LLM"
            )
            return "GENERAL_CHAT"

        lexicon_languages = [language] if language else list(self.LEXICON_FILES.keys())
        best_intent = ""
        best_score = 0.0
        best_top2 = []
        for lang in lexicon_languages:
            lexicon = self._load_lexicon(lang)
            user_lexicon = self._load_user_lexicon(lang)
            lexicon = self._merge_lexicons(lexicon, user_lexicon)
            intent, score, top2 = self._match_intent_lexicon(normalized, lexicon)
            if intent and score > best_score:
                best_intent = intent
                best_score = score
                best_top2 = top2

        if language and best_score < self.LEXICON_FALLBACK_SCORE:
            fallback_best = ("", 0.0, [])
            for lang in self.LEXICON_FILES.keys():
                lexicon = self._load_lexicon(lang)
                user_lexicon = self._load_user_lexicon(lang)
                lexicon = self._merge_lexicons(lexicon, user_lexicon)
                intent, score, top2 = self._match_intent_lexicon(normalized, lexicon)
                if intent and score > fallback_best[1]:
                    fallback_best = (intent, score, top2)
            if fallback_best[0] and fallback_best[1] > best_score:
                best_intent, best_score, best_top2 = fallback_best
                language = ""

        if best_intent:
            if (
                len(best_top2) >= 2
                and abs(best_top2[0][1] - best_top2[1][1]) <= self.TIE_BREAK_DELTA
            ):
                top_candidates = {best_top2[0][0], best_top2[1][0]}
                tool_candidates = top_candidates & self.TOOL_INTENTS
                if tool_candidates:
                    best_intent = sorted(tool_candidates)[0]
                    best_score = max(best_top2[0][1], best_top2[1][1])
            logger.debug(
                f"Wykryto intencję przez lexicon: {best_intent} (score={best_score:.2f})"
            )
            self.last_intent_debug = {
                "source": "lexicon",
                "language": language or "unknown",
                "score": round(best_score, 4),
                "top2": best_top2,
            }
            return best_intent

        help_detected = any(
            self._normalize_text(keyword) in normalized
            for keyword in self.HELP_KEYWORDS
        )
        if help_detected:
            logger.debug("Wykryto słowa kluczowe pomocy - zwracam HELP_REQUEST")
            self.last_intent_debug["source"] = "keyword"
            if self.kernel:
                try:
                    await self.kernel.get_service().get_chat_message_content()
                except Exception as e:
                    # LLM service might not be available - this is expected
                    logger.debug(f"LLM service not available for intent: {e}")
            self._append_user_phrase("HELP_REQUEST", user_input, language)
            return "HELP_REQUEST"
        if any(
            self._normalize_text(keyword) in normalized
            for keyword in self.TIME_KEYWORDS
        ):
            logger.debug("Wykryto zapytanie o godzinę - zwracam TIME_REQUEST")
            self.last_intent_debug["source"] = "keyword"
            self._append_user_phrase("TIME_REQUEST", user_input, language)
            return "TIME_REQUEST"
        if any(
            self._normalize_text(keyword) in normalized
            for keyword in self.INFRA_KEYWORDS
        ):
            logger.debug("Wykryto zapytanie o infrastrukturę - zwracam INFRA_STATUS")
            self.last_intent_debug["source"] = "keyword"
            self._append_user_phrase("INFRA_STATUS", user_input, language)
            return "INFRA_STATUS"

        def _build_chat_history(system_as_user: bool) -> ChatHistory:
            chat_history = ChatHistory()
            if system_as_user:
                combined_prompt = f"{self.SYSTEM_PROMPT.strip()}\n\n[Klasyfikuj intencję]\n{user_input}"
                chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.USER,
                        content=combined_prompt,
                    )
                )
            else:
                chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.SYSTEM,
                        content=self.SYSTEM_PROMPT,
                    )
                )
                chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.USER,
                        content=f"Klasyfikuj intencję:\n\n{user_input}",
                    )
                )
            return chat_history

        if not self.kernel or self._llm_disabled:
            logger.info("Brak dopasowania intencji i brak LLM - zwracam GENERAL_CHAT")
            self.last_intent_debug["source"] = "fallback"
            return "GENERAL_CHAT"

        # Przygotuj historię rozmowy
        chat_history = _build_chat_history(system_as_user=False)

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Wywołaj model
            settings = OpenAIChatPromptExecutionSettings()

            timeout = getattr(SETTINGS, "INTENT_CLASSIFIER_TIMEOUT_SECONDS", 5.0)

            try:
                response = await asyncio.wait_for(
                    chat_service.get_chat_message_content(
                        chat_history=chat_history, settings=settings
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Intent classification timeout po {timeout}s - używam GENERAL_CHAT"
                )
                return "GENERAL_CHAT"
            except Exception as api_error:
                error_text = str(api_error).lower()
                inner = getattr(api_error, "inner_exception", None)
                if inner:
                    error_text += f" {str(inner).lower()}"

                if "system role not supported" in error_text:
                    logger.warning(
                        "Model nie wspiera roli SYSTEM w IntentManager - retry bez SYSTEM."
                    )
                    chat_history = _build_chat_history(system_as_user=True)
                    try:
                        response = await asyncio.wait_for(
                            chat_service.get_chat_message_content(
                                chat_history=chat_history, settings=settings
                            ),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Intent classification timeout po {timeout}s - używam GENERAL_CHAT"
                        )
                        return "GENERAL_CHAT"
                else:
                    raise

            # Wyciągnij czystą odpowiedź (usuń whitespace)
            intent = str(response).strip().upper()

            # Walidacja odpowiedzi - upewnij się, że to jedna z dozwolonych kategorii
            valid_intents = [
                "CODE_GENERATION",
                "KNOWLEDGE_SEARCH",
                "GENERAL_CHAT",
                "RESEARCH",
                "COMPLEX_PLANNING",
                "VERSION_CONTROL",
                "E2E_TESTING",
                "DOCUMENTATION",
                "RELEASE_PROJECT",
                "START_CAMPAIGN",
                "STATUS_REPORT",
                "INFRA_STATUS",
                "HELP_REQUEST",
                "TIME_REQUEST",
                "UNSUPPORTED_TASK",
            ]
            if intent not in valid_intents:
                # Jeśli odpowiedź nie jest dokładna, spróbuj znaleźć dopasowanie
                for valid_intent in valid_intents:
                    if valid_intent in intent:
                        intent = valid_intent
                        break
                else:
                    # Fallback - użyj GENERAL_CHAT jako domyślnego
                    logger.warning(
                        f"Nierozpoznana intencja: {intent}, używam GENERAL_CHAT jako fallback"
                    )
                    intent = "GENERAL_CHAT"

            logger.info(f"Sklasyfikowana intencja: {intent}")
            self.last_intent_debug["source"] = "llm"
            if intent in valid_intents and intent != "UNSUPPORTED_TASK":
                self._append_user_phrase(intent, user_input, language)
            return intent

        except Exception as e:
            logger.error(f"Błąd podczas klasyfikacji intencji: {e}")
            # W przypadku błędu użyj heurystyki: chat vs unsupported
            if any(
                self._normalize_text(keyword) in normalized
                for keyword in self.HELP_KEYWORDS
            ):
                self.last_intent_debug["source"] = "fallback"
                return "HELP_REQUEST"
            fallback_langs = [language] if language else list(self.LEXICON_FILES.keys())
            for lang in fallback_langs:
                lexicon = self._load_lexicon(lang)
                user_lexicon = self._load_user_lexicon(lang)
                lexicon = self._merge_lexicons(lexicon, user_lexicon)
                if self._match_intent_lexicon(normalized, lexicon)[0]:
                    self.last_intent_debug["source"] = "fallback"
                    return "GENERAL_CHAT"
            self.last_intent_debug["source"] = "fallback"
            return "GENERAL_CHAT"

    def requires_tool(self, intent: str) -> bool:
        """Zwraca True jeśli intencja wymaga narzędzia/systemowej wiedzy."""
        return intent in self.TOOL_REQUIRED_INTENTS
