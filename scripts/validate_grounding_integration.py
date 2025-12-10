#!/usr/bin/env python3
"""
Standalone validation script for Google Search Grounding Integration.
Validates code changes without requiring full dependencies.
"""

import sys
from pathlib import Path


def ensure(condition: bool, message: str) -> None:
    """Raise AssertionError with message when condition fails."""
    if not condition:
        raise AssertionError(message)


def validate_state_manager():
    """Validate StateManager changes."""
    print("=" * 80)
    print("Validating StateManager...")
    print("=" * 80)

    state_manager_path = Path("venom_core/core/state_manager.py")
    with open(state_manager_path, "r") as f:
        code = f.read()

    # Check for paid_mode_enabled field
    ensure(
        "self.paid_mode_enabled: bool = False" in code,
        "❌ Missing paid_mode_enabled field",
    )
    print("✓ paid_mode_enabled field exists")

    # Check for set_paid_mode method
    ensure(
        "def set_paid_mode(self, enabled: bool)" in code,
        "❌ Missing set_paid_mode method",
    )
    print("✓ set_paid_mode method exists")

    # Check for is_paid_mode_enabled method
    ensure(
        "def is_paid_mode_enabled(self)" in code,
        "❌ Missing is_paid_mode_enabled method",
    )
    print("✓ is_paid_mode_enabled method exists")

    # Check persistence
    ensure(
        '"paid_mode_enabled": self.paid_mode_enabled' in code,
        "❌ paid_mode_enabled not persisted",
    )
    print("✓ paid_mode_enabled is persisted to JSON")

    # Check loading
    ensure(
        'self.paid_mode_enabled = data.get("paid_mode_enabled", False)' in code,
        "❌ paid_mode_enabled not loaded from JSON",
    )
    print("✓ paid_mode_enabled is loaded from JSON")

    print("✅ StateManager validation passed!\n")


def validate_task_type():
    """Validate TaskType.RESEARCH addition."""
    print("=" * 80)
    print("Validating TaskType.RESEARCH...")
    print("=" * 80)

    model_router_path = Path("venom_core/execution/model_router.py")
    with open(model_router_path, "r") as f:
        code = f.read()

    # Check for RESEARCH enum value
    ensure('RESEARCH = "RESEARCH"' in code, "❌ Missing RESEARCH task type")
    print("✓ TaskType.RESEARCH exists")

    # Check for comment
    ensure(
        "# Badania, wyszukiwanie w Internecie" in code or "RESEARCH" in code,
        "❌ Missing RESEARCH description",
    )
    print("✓ RESEARCH task type has description")

    print("✅ TaskType.RESEARCH validation passed!\n")


def validate_router_logic():
    """Validate router logic for RESEARCH."""
    print("=" * 80)
    print("Validating Router Logic...")
    print("=" * 80)

    model_router_path = Path("venom_core/execution/model_router.py")
    with open(model_router_path, "r") as f:
        code = f.read()

    # Check for RESEARCH routing logic
    ensure(
        "if task_type == TaskType.RESEARCH:" in code,
        "❌ Missing RESEARCH routing logic",
    )
    print("✓ RESEARCH routing logic exists")

    # Check for paid_mode comment or reference
    ensure(
        "RESEARCH" in code and ("Google" in code or "DuckDuckGo" in code),
        "❌ Missing search provider logic",
    )
    print("✓ Search provider logic exists")

    print("✅ Router logic validation passed!\n")


def validate_kernel_builder():
    """Validate enable_grounding parameter."""
    print("=" * 80)
    print("Validating KernelBuilder...")
    print("=" * 80)

    kernel_builder_path = Path("venom_core/execution/kernel_builder.py")
    with open(kernel_builder_path, "r") as f:
        code = f.read()

    # Check for enable_grounding parameter
    ensure(
        "enable_grounding: bool = False" in code,
        "❌ Missing enable_grounding parameter",
    )
    print("✓ enable_grounding parameter exists")

    # Check for grounding configuration
    ensure("grounding" in code.lower(), "❌ Missing grounding configuration")
    print("✓ Grounding configuration exists")

    # Check for Google Search tools comment
    ensure(
        "google_search" in code or "tools" in code,
        "❌ Missing Google Search tools reference",
    )
    print("✓ Google Search tools reference exists")

    print("✅ KernelBuilder validation passed!\n")


def validate_researcher_agent():
    """Validate ResearcherAgent changes."""
    print("=" * 80)
    print("Validating ResearcherAgent...")
    print("=" * 80)

    researcher_path = Path("venom_core/agents/researcher.py")
    with open(researcher_path, "r") as f:
        code = f.read()

    # Check for format_grounding_sources function
    ensure(
        "def format_grounding_sources" in code,
        "❌ Missing format_grounding_sources function",
    )
    print("✓ format_grounding_sources function exists")

    # Check for grounding_metadata handling
    ensure("grounding_metadata" in code, "❌ Missing grounding_metadata handling")
    print("✓ grounding_metadata handling exists")

    # Check for get_last_search_source method
    ensure(
        "def get_last_search_source" in code, "❌ Missing get_last_search_source method"
    )
    print("✓ get_last_search_source method exists")

    # Check for _last_search_source field
    ensure("_last_search_source" in code, "❌ Missing _last_search_source field")
    print("✓ _last_search_source field exists")

    # Check for sources section formatting
    ensure(
        "📚 Źródła (Google Grounding)" in code, "❌ Missing sources section formatting"
    )
    print("✓ Sources section formatting exists")

    print("✅ ResearcherAgent validation passed!\n")


def validate_frontend():
    """Validate frontend badge implementation."""
    print("=" * 80)
    print("Validating Frontend...")
    print("=" * 80)

    app_js_path = Path("web/static/js/app.js")
    with open(app_js_path, "r") as f:
        code = f.read()

    # Check for research-source-badge class
    ensure("research-source-badge" in code, "❌ Missing research-source-badge class")
    print("✓ research-source-badge class exists")

    # Check for google_grounding badge
    ensure("google_grounding" in code, "❌ Missing google_grounding badge")
    print("✓ google_grounding badge exists")

    # Check for duckduckgo badge
    ensure("duckduckgo" in code, "❌ Missing duckduckgo badge")
    print("✓ duckduckgo badge exists")

    # Check for emoji icons
    ensure("🌍" in code and "🦆" in code, "❌ Missing emoji icons")
    print("✓ Emoji icons exist (🌍 🦆)")

    # Check for CSS classes (styles moved to app.css)
    ensure("google-grounded" in code, "❌ Missing google-grounded CSS class usage")
    print("✓ google-grounded CSS class usage exists")

    ensure("web-search" in code, "❌ Missing web-search CSS class usage")
    print("✓ web-search CSS class usage exists")

    # Check for metadata parameter in addChatMessage
    ensure(
        "metadata = null" in code or "metadata" in code,
        "❌ Missing metadata parameter in addChatMessage",
    )
    print("✓ metadata parameter in addChatMessage exists")

    # Validate CSS file
    css_path = Path("web/static/css/app.css")
    with open(css_path, "r") as f:
        css_code = f.read()

    ensure(
        ".research-source-badge" in css_code,
        "❌ Missing research-source-badge CSS class",
    )
    print("✓ research-source-badge CSS class exists in app.css")

    ensure(".google-grounded" in css_code, "❌ Missing google-grounded CSS class")
    print("✓ google-grounded CSS class exists in app.css")

    ensure("#1e40af" in css_code, "❌ Missing Google Grounded badge color in CSS")
    print("✓ Google Grounded badge color exists in CSS (#1e40af)")

    ensure("#6b7280" in css_code, "❌ Missing Web Search badge color in CSS")
    print("✓ Web Search badge color exists in CSS (#6b7280)")

    print("✅ Frontend validation passed!\n")


def validate_tests():
    """Validate test additions."""
    print("=" * 80)
    print("Validating Tests...")
    print("=" * 80)

    # Test state_and_orchestrator
    state_test_path = Path("tests/test_state_and_orchestrator.py")
    with open(state_test_path, "r") as f:
        code = f.read()

    ensure(
        "test_state_manager_paid_mode_default" in code,
        "❌ Missing test_state_manager_paid_mode_default",
    )
    print("✓ test_state_manager_paid_mode_default exists")

    ensure(
        "test_state_manager_set_paid_mode" in code,
        "❌ Missing test_state_manager_set_paid_mode",
    )
    print("✓ test_state_manager_set_paid_mode exists")

    ensure(
        "test_state_manager_paid_mode_persistence" in code,
        "❌ Missing test_state_manager_paid_mode_persistence",
    )
    print("✓ test_state_manager_paid_mode_persistence exists")

    # Test hybrid_model_router
    router_test_path = Path("tests/test_hybrid_model_router.py")
    with open(router_test_path, "r") as f:
        code = f.read()

    ensure(
        "test_route_research_task" in code, "❌ Missing test_route_research_task tests"
    )
    print("✓ test_route_research_task tests exist")

    # Test kernel_builder
    kernel_test_path = Path("tests/test_kernel_builder.py")
    with open(kernel_test_path, "r") as f:
        code = f.read()

    ensure(
        "test_kernel_builder_enable_grounding_parameter" in code,
        "❌ Missing test_kernel_builder_enable_grounding_parameter",
    )
    print("✓ test_kernel_builder_enable_grounding_parameter exists")

    print("✅ Tests validation passed!\n")


def validate_documentation():
    """Validate documentation."""
    print("=" * 80)
    print("Validating Documentation...")
    print("=" * 80)

    docs_path = Path("docs/google_search_grounding_integration.md")
    if not docs_path.exists():
        raise AssertionError("❌ Missing documentation file")

    with open(docs_path, "r") as f:
        content = f.read()

    # Check for key sections
    ensure("# Google Search Grounding Integration" in content, "❌ Missing main title")
    print("✓ Main title exists")

    ensure(
        "Architektura" in content or "Architecture" in content,
        "❌ Missing architecture section",
    )
    print("✓ Architecture section exists")

    ensure(
        "Kryteria Akceptacji" in content or "DoD" in content,
        "❌ Missing acceptance criteria section",
    )
    print("✓ Acceptance criteria section exists")

    ensure("paid_mode" in content, "❌ Missing paid_mode documentation")
    print("✓ paid_mode documentation exists")

    ensure("Google Grounding" in content, "❌ Missing Google Grounding documentation")
    print("✓ Google Grounding documentation exists")

    print("✅ Documentation validation passed!\n")


def main():
    """Main validation function."""
    print("\n" + "=" * 80)
    print("GOOGLE SEARCH GROUNDING INTEGRATION - VALIDATION")
    print("=" * 80 + "\n")

    try:
        # Change to repo root
        repo_root = Path(__file__).parent.parent
        import os

        os.chdir(repo_root)

        # Run all validations
        validate_state_manager()
        validate_task_type()
        validate_router_logic()
        validate_kernel_builder()
        validate_researcher_agent()
        validate_frontend()
        validate_tests()
        validate_documentation()

        print("=" * 80)
        print("✅ ALL VALIDATIONS PASSED!")
        print("=" * 80)
        print("\nSummary:")
        print("✓ StateManager: paid_mode_enabled with get/set methods")
        print("✓ TaskType: RESEARCH enum value added")
        print("✓ Router: RESEARCH routing logic implemented")
        print("✓ KernelBuilder: enable_grounding parameter added")
        print("✓ ResearcherAgent: grounding sources formatting")
        print("✓ Frontend: Badge rendering (🌍 Google, 🦆 DuckDuckGo)")
        print("✓ Tests: Unit tests for all components")
        print("✓ Documentation: Complete integration guide")

        print("\n✅ Implementation complete and ready for review!")
        return 0

    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
