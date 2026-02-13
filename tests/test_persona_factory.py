"""Testy dla PersonaFactory."""

import pytest

from venom_core.simulation.persona_factory import Persona, PersonaFactory, TechLiteracy


def test_persona_creation():
    """Test tworzenia persony."""
    persona = Persona(
        name="Jan",
        age=45,
        tech_literacy=TechLiteracy.MEDIUM,
        patience=0.5,
        goal="Kupić produkt",
        traits=["ciekawy", "ostrożny"],
        frustration_threshold=3,
    )

    assert persona.name == "Jan"
    assert persona.age == 45
    assert persona.tech_literacy == TechLiteracy.MEDIUM
    assert persona.patience == pytest.approx(0.5)
    assert persona.goal == "Kupić produkt"
    assert "ciekawy" in persona.traits


def test_persona_to_dict():
    """Test konwersji persony do słownika."""
    persona = Persona(
        name="Anna",
        age=30,
        tech_literacy=TechLiteracy.HIGH,
        patience=0.8,
        goal="Test",
        traits=["dokładny"],
    )

    persona_dict = persona.to_dict()

    assert persona_dict["name"] == "Anna"
    assert persona_dict["age"] == 30
    assert persona_dict["tech_literacy"] == TechLiteracy.HIGH
    assert persona_dict["patience"] == pytest.approx(0.8)


def test_persona_to_json():
    """Test konwersji persony do JSON."""
    persona = Persona(
        name="Marek",
        age=60,
        tech_literacy=TechLiteracy.LOW,
        patience=0.3,
        goal="Zarejestrować się",
        traits=["niecierpliwy"],
    )

    json_str = persona.to_json()

    assert "Marek" in json_str
    assert "60" in json_str
    assert "low" in json_str
    assert "Zarejestrować się" in json_str


def test_persona_from_dict():
    """Test tworzenia persony ze słownika."""
    data = {
        "name": "Piotr",
        "age": 35,
        "tech_literacy": "high",
        "patience": 0.7,
        "goal": "Test goal",
        "traits": ["analityczny"],
        "frustration_threshold": 4,
        "description": "Test description",
    }

    persona = Persona.from_dict(data)

    assert persona.name == "Piotr"
    assert persona.age == 35
    assert persona.tech_literacy == TechLiteracy.HIGH
    assert persona.patience == pytest.approx(0.7)


def test_persona_factory_initialization():
    """Test inicjalizacji PersonaFactory."""
    factory = PersonaFactory()

    assert factory.kernel is None  # Brak kernela


def test_persona_factory_generate_persona():
    """Test generowania pojedynczej persony."""
    factory = PersonaFactory()

    persona = factory.generate_persona(goal="Kupić buty")

    assert persona.name is not None
    assert persona.goal == "Kupić buty"
    assert persona.age > 0
    assert persona.patience >= 0.0
    assert persona.patience <= 1.0
    assert persona.frustration_threshold > 0


def test_persona_factory_generate_with_archetype():
    """Test generowania persony z konkretnym archetypem."""
    factory = PersonaFactory()

    # Senior
    senior = factory.generate_persona(goal="Test", archetype="senior")
    assert senior.tech_literacy == TechLiteracy.LOW
    assert senior.age >= 55

    # Impulsive buyer
    impulsive = factory.generate_persona(goal="Test", archetype="impulsive_buyer")
    assert impulsive.tech_literacy == TechLiteracy.HIGH
    assert impulsive.age >= 18 and impulsive.age <= 35


def test_persona_factory_generate_diverse_personas():
    """Test generowania zróżnicowanych person."""
    factory = PersonaFactory()

    personas = factory.generate_diverse_personas(goal="Zarejestrować konto", count=5)

    assert len(personas) == 5

    # Sprawdź różnorodność
    tech_levels = set(p.tech_literacy for p in personas)
    ages = [p.age for p in personas]

    # Powinny być różne poziomy techniczne
    assert len(tech_levels) > 1

    # Powinny być różne przedziały wiekowe
    assert max(ages) - min(ages) > 10


def test_persona_factory_unknown_archetype():
    """Test generowania persony z nieznanym archetypem (powinien użyć losowego)."""
    factory = PersonaFactory()

    persona = factory.generate_persona(goal="Test", archetype="unknown_archetype")

    # Powinna być wygenerowana pomimo nieznanego archetypu
    assert persona.goal == "Test"


def test_persona_frustration_threshold_calculation():
    """Test obliczania progu frustracji na podstawie cierpliwości."""
    factory = PersonaFactory()

    # Niska cierpliwość = niski próg
    low_patience = factory.generate_persona(
        goal="Test", archetype="frustrated_returner"
    )
    assert low_patience.frustration_threshold <= 3

    # Wysoka cierpliwość = wyższy próg
    high_patience = factory.generate_persona(goal="Test", archetype="professional")
    assert high_patience.frustration_threshold >= 4


def test_persona_traits_are_copied():
    """Test że cechy są kopiowane (nie współdzielone między personami)."""
    factory = PersonaFactory()

    persona1 = factory.generate_persona(goal="Test1", archetype="senior")
    persona2 = factory.generate_persona(goal="Test2", archetype="senior")

    # Cechy powinny być niezależne
    persona1.traits.append("custom_trait")
    assert "custom_trait" not in persona2.traits


def test_persona_factory_with_kernel():
    """Test PersonaFactory z kernelem (dla LLM enhancement)."""
    # TODO: Wymaga mock kernela lub prawdziwej konfiguracji
    # Dla MVP używamy prostej wersji bez LLM
    factory = PersonaFactory(kernel=None)

    persona = factory.generate_persona(goal="Test", use_llm=False)
    assert persona.description != ""  # Powinna mieć podstawowy opis


def test_persona_enrichment_high_patience_branch():
    factory = PersonaFactory(kernel=None)
    persona = Persona(
        name="Anna",
        age=34,
        tech_literacy=TechLiteracy.HIGH,
        patience=0.9,
        goal="Kupić produkt",
        traits=["dokładny"],
        description="",
    )
    enriched = factory._enrich_persona_with_llm(persona)
    assert enriched.description
    assert persona.name in enriched.description
    assert str(persona.age) in enriched.description
    assert persona.goal in enriched.description
    assert "Szybko się frustruje" not in enriched.description


def test_persona_enrichment_with_llm_mock():
    """Test wzbogacania persony przez LLM (mock kernel)."""
    from unittest.mock import MagicMock, AsyncMock
    
    # Mock kernel i chat service
    mock_kernel = MagicMock()
    mock_chat_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Anna to 34-letnia profesjonalistka z wysoką znajomością technologii. "
                     "Jest cierpliwa i dokładna w swoich działaniach, a jej głównym celem jest kupić produkt."
    )
    
    mock_chat_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_chat_service)
    
    factory = PersonaFactory(kernel=mock_kernel)
    persona = Persona(
        name="Anna",
        age=34,
        tech_literacy=TechLiteracy.HIGH,
        patience=0.9,
        goal="Kupić produkt",
        traits=["dokładny"],
        description="",
    )
    
    enriched = factory._enrich_persona_with_llm(persona)
    
    # Sprawdź że LLM został wywołany
    assert mock_chat_service.get_chat_message_content.called
    # Sprawdź że dostaliśmy wzbogacony opis
    assert enriched.description
    assert "Anna" in enriched.description
    assert "profesjonalistka" in enriched.description or len(enriched.description) > 20


def test_persona_enrichment_llm_fallback_on_error():
    """Test fallbacku do szablonu gdy LLM rzuca wyjątek."""
    from unittest.mock import MagicMock, AsyncMock
    
    # Mock kernel który rzuca wyjątek
    mock_kernel = MagicMock()
    mock_chat_service = MagicMock()
    mock_chat_service.get_chat_message_content = AsyncMock(
        side_effect=Exception("LLM error")
    )
    mock_kernel.get_service = MagicMock(return_value=mock_chat_service)
    
    factory = PersonaFactory(kernel=mock_kernel)
    persona = Persona(
        name="Jan",
        age=60,
        tech_literacy=TechLiteracy.LOW,
        patience=0.3,
        goal="Test celu",
        traits=["niecierpliwy"],
        description="",
    )
    
    enriched = factory._enrich_persona_with_llm(persona)
    
    # Sprawdź że dostaliśmy fallback (szablon)
    assert enriched.description
    assert "Jan" in enriched.description
    assert "60" in enriched.description or "rzadko używa komputera" in enriched.description


def test_persona_enrichment_llm_empty_response():
    """Test fallbacku gdy LLM zwraca pustą odpowiedź."""
    from unittest.mock import MagicMock, AsyncMock
    
    # Mock kernel z pustą odpowiedzią
    mock_kernel = MagicMock()
    mock_chat_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="")
    
    mock_chat_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_chat_service)
    
    factory = PersonaFactory(kernel=mock_kernel)
    persona = Persona(
        name="Test",
        age=30,
        tech_literacy=TechLiteracy.MEDIUM,
        patience=0.5,
        goal="Test",
        traits=["test"],
        description="",
    )
    
    enriched = factory._enrich_persona_with_llm(persona)
    
    # Sprawdź że dostaliśmy fallback (szablon) gdy LLM zwrócił pusty string
    assert enriched.description
    assert "Test" in enriched.description
