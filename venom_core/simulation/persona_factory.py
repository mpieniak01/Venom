"""Moduł: persona_factory - generator profili użytkowników dla symulacji."""

import asyncio
import json
import secrets
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional, TypedDict

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
secure_random = secrets.SystemRandom()


class TechLiteracy(str, Enum):
    """Poziom znajomości technologii."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Persona:
    """Model persony użytkownika dla symulacji.

    Atrybuty:
        name: Imię użytkownika
        age: Wiek użytkownika
        tech_literacy: Poziom znajomości technologii (low/medium/high)
        patience: Poziom cierpliwości (0.0-1.0, gdzie 0.0 = bardzo niecierpliwy)
        goal: Cel użytkownika w aplikacji
        traits: Lista cech charakteru (np. "impulsywny", "dokładny")
        frustration_threshold: Próg frustracji - ile błędów przed rezygnacją
        description: Dodatkowy opis persony
    """

    name: str
    age: int
    tech_literacy: TechLiteracy
    patience: float
    goal: str
    traits: list[str]
    frustration_threshold: int = 3
    description: str = ""

    def to_dict(self) -> dict:
        """Konwertuje personę do słownika."""
        return asdict(self)

    def to_json(self) -> str:
        """Konwertuje personę do JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        """Tworzy personę ze słownika."""
        # Konwertuj tech_literacy na enum jeśli to string
        if isinstance(data.get("tech_literacy"), str):
            data["tech_literacy"] = TechLiteracy(data["tech_literacy"])
        return cls(**data)


class PersonaFactory:
    """Fabryka do generowania profili użytkowników za pomocą LLM."""

    # Szablony podstawowych person
    class PersonaTemplate(TypedDict):
        archetype: str
        description: str
        tech_literacy: TechLiteracy
        patience: float
        age_range: tuple[int, int]
        traits: list[str]

    PERSONA_TEMPLATES: list[PersonaTemplate] = [
        {
            "archetype": "senior",
            "description": "Osoba starsza, mało techniczna, łatwo się frustruje",
            "tech_literacy": TechLiteracy.LOW,
            "patience": 0.3,
            "age_range": (55, 75),
            "traits": ["ostrożny", "nieufny", "potrzebuje jasnych instrukcji"],
        },
        {
            "archetype": "impulsive_buyer",
            "description": "Młoda osoba, impulsywna, szybkie decyzje",
            "tech_literacy": TechLiteracy.HIGH,
            "patience": 0.5,
            "age_range": (18, 35),
            "traits": ["impulsywny", "niecierpliwy", "oczekuje szybkości"],
        },
        {
            "archetype": "professional",
            "description": "Profesjonalista, doświadczony, metodyczny",
            "tech_literacy": TechLiteracy.HIGH,
            "patience": 0.8,
            "age_range": (30, 50),
            "traits": ["dokładny", "analityczny", "oczekuje efektywności"],
        },
        {
            "archetype": "casual_user",
            "description": "Przeciętny użytkownik, średnie umiejętności",
            "tech_literacy": TechLiteracy.MEDIUM,
            "patience": 0.6,
            "age_range": (25, 45),
            "traits": ["ciekawy", "otwarty", "oczekuje intuicyjności"],
        },
        {
            "archetype": "frustrated_returner",
            "description": "Użytkownik który miał już złe doświadczenia",
            "tech_literacy": TechLiteracy.MEDIUM,
            "patience": 0.2,
            "age_range": (20, 60),
            "traits": ["podejrzliwy", "wyczulony na błędy", "szybko rezygnuje"],
        },
    ]

    # Polskie imiona do losowania
    POLISH_NAMES = {
        "male": [
            "Janusz",
            "Marek",
            "Tomasz",
            "Piotr",
            "Krzysztof",
            "Adam",
            "Michał",
            "Paweł",
            "Bartosz",
            "Jakub",
        ],
        "female": [
            "Anna",
            "Maria",
            "Katarzyna",
            "Małgorzata",
            "Agnieszka",
            "Barbara",
            "Ewa",
            "Joanna",
            "Magdalena",
            "Monika",
        ],
    }

    # Stałe dla obliczeń
    FRUSTRATION_THRESHOLD_MULTIPLIER = 5  # Mnożnik dla progu frustracji
    PATIENCE_HIGH_THRESHOLD = 0.6  # Próg dla wysokiej cierpliwości

    def __init__(self, kernel: Optional[Kernel] = None):
        """
        Inicjalizacja PersonaFactory.

        Args:
            kernel: Opcjonalny kernel Semantic Kernel do generowania person z LLM
        """
        self.kernel = kernel
        logger.info("PersonaFactory zainicjalizowany")

    def generate_persona(
        self,
        goal: str,
        archetype: Optional[str] = None,
        use_llm: bool = False,
    ) -> Persona:
        """
        Generuje personę użytkownika.

        Args:
            goal: Cel użytkownika w aplikacji (np. "kupić czerwone buty")
            archetype: Opcjonalny archetyp (senior, impulsive_buyer, itp.)
            use_llm: Czy użyć LLM do wzbogacenia persony (wymaga kernela)

        Returns:
            Wygenerowana persona
        """
        # Wybierz szablon
        if archetype:
            template = next(
                (t for t in self.PERSONA_TEMPLATES if t["archetype"] == archetype),
                None,
            )
            if not template:
                logger.warning(
                    f"Nieznany archetyp: {archetype}, użyto losowego szablonu"
                )
                template = secure_random.choice(self.PERSONA_TEMPLATES)
        else:
            template = secure_random.choice(self.PERSONA_TEMPLATES)

        # Wygeneruj podstawowe dane
        age = secure_random.randint(*template["age_range"])
        name = secure_random.choice(
            self.POLISH_NAMES["male"] + self.POLISH_NAMES["female"]
        )

        # Wylicz próg frustracji na podstawie cierpliwości
        frustration_threshold = max(
            1, int(template["patience"] * self.FRUSTRATION_THRESHOLD_MULTIPLIER) + 1
        )

        persona = Persona(
            name=name,
            age=age,
            tech_literacy=template["tech_literacy"],
            patience=template["patience"],
            goal=goal,
            traits=template["traits"].copy(),
            frustration_threshold=frustration_threshold,
            description=template["description"],
        )

        # Opcjonalnie wzbogać personę używając LLM
        if use_llm and self.kernel:
            persona = self._enrich_persona_with_llm(persona)

        logger.info(f"Wygenerowano personę: {persona.name}, cel: {goal}")
        return persona

    def _enrich_persona_with_llm(self, persona: Persona) -> Persona:
        """
        Wzbogaca personę używając LLM (dodaje szczegóły, backstory).

        Args:
            persona: Podstawowa persona do wzbogacenia

        Returns:
            Wzbogacona persona
        """
        # Jeśli kernel dostępny, spróbuj wzbogacić przez LLM
        if self.kernel:
            try:
                logger.debug(f"Wzbogacanie persony {persona.name} z LLM")

                # Przygotuj prompt dla LLM
                tech_level = {
                    TechLiteracy.LOW: "rzadko używa komputera",
                    TechLiteracy.MEDIUM: "ma podstawową znajomość technologii",
                    TechLiteracy.HIGH: "jest biegły w obsłudze aplikacji webowych",
                }

                prompt = f"""Stwórz krótki, spójny opis użytkownika dla symulacji UX:

Imię: {persona.name}
Wiek: {persona.age}
Znajomość tech: {tech_level[persona.tech_literacy]}
Cierpliwość: {'wysoka' if persona.patience > self.PATIENCE_HIGH_THRESHOLD else 'niska'}
Cel: {persona.goal}
Cechy: {', '.join(persona.traits)}

Napisz 2-3 zdaniowy opis tej persony, który nadaje jej charakteru i kontekstu.
Nie zmieniaj podanych faktów - tylko dodaj koloryt i tło.
Odpowiedź: tylko opis, bez dodatkowych komentarzy."""

                # Wywołaj LLM
                chat_service = self.kernel.get_service()
                chat_history = ChatHistory()
                chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.USER,
                        content=prompt
                    )
                )

                # Ustawienia wykonania - krótka odpowiedź
                settings = OpenAIChatPromptExecutionSettings(
                    temperature=0.8,
                    max_tokens=150
                )

                # Wywołaj asynchronicznie - zawsze używamy asyncio.run
                # (wywołanie synchroniczne zawsze tworzy nowy loop)
                response = asyncio.run(chat_service.get_chat_message_content(
                    chat_history=chat_history,
                    settings=settings
                ))

                enriched_description = str(response).strip()

                # Walidacja: opis nie może być pusty, wystarczająco długi i powinien zawierać imię persony
                if (
                    enriched_description
                    and len(enriched_description) > 10
                    and persona.name.lower() in enriched_description.lower()
                ):
                    # Ogranicz długość do max 500 znaków
                    persona.description = enriched_description[:500]
                    logger.info(f"Wzbogacono personę {persona.name} przez LLM")
                    return persona
                else:
                    logger.warning(f"LLM zwrócił pusty/zbyt krótki opis lub bez imienia, używam szablonu")
                    # Fallback do szablonu
                    
            except Exception as e:
                logger.warning(f"Błąd podczas wzbogacania persony przez LLM: {e}, używam szablonu")
                # Fallback do szablonu

        # Szablon fallback (bez LLM lub w razie błędu)
        tech_level = {
            TechLiteracy.LOW: "rzadko używa komputera",
            TechLiteracy.MEDIUM: "ma podstawową znajomość technologii",
            TechLiteracy.HIGH: "jest biegły w obsłudze aplikacji webowych",
        }

        backstory = (
            f"{persona.name} ma {persona.age} lat i {tech_level[persona.tech_literacy]}. "
            f"{'Jest cierpliwy i' if persona.patience > self.PATIENCE_HIGH_THRESHOLD else 'Szybko się frustruje i'} "
            f"ma jasny cel: {persona.goal}."
        )

        persona.description = backstory
        return persona

    def generate_diverse_personas(
        self, goal: str, count: int = 5, use_llm: bool = False
    ) -> list[Persona]:
        """
        Generuje zróżnicowany zestaw person dla tego samego celu.

        Args:
            goal: Wspólny cel wszystkich person
            count: Liczba person do wygenerowania
            use_llm: Czy użyć LLM do wzbogacenia

        Returns:
            Lista wygenerowanych person
        """
        personas = []

        # Upewnij się że mamy reprezentację różnych archetypów
        archetypes = [t["archetype"] for t in self.PERSONA_TEMPLATES]

        for i in range(count):
            # Użyj archetypów cyklicznie, aby zapewnić różnorodność
            archetype = archetypes[i % len(archetypes)] if i < len(archetypes) else None
            persona = self.generate_persona(goal, archetype, use_llm)
            personas.append(persona)

        logger.info(f"Wygenerowano {count} zróżnicowanych person dla celu: {goal}")
        return personas
