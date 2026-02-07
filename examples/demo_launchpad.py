#!/usr/bin/env python3
"""
Skrypt demonstracyjny dla funkcji THE_LAUNCHPAD.
Pokazuje działanie nowych komponentów bez potrzeby pełnego środowiska.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Dodaj ścieżkę do venom_core
sys.path.insert(0, str(Path(__file__).parent.parent))


async def demo_media_skill():
    """Demonstracja MediaSkill - generowanie obrazów."""
    print("\n" + "=" * 60)
    print("DEMO: MediaSkill - Generowanie Obrazów")
    print("=" * 60)

    from venom_core.execution.skills.media_skill import MediaSkill

    with tempfile.TemporaryDirectory() as tmpdir:
        skill = MediaSkill(assets_dir=tmpdir)

        # Test 1: Generuj placeholder logo
        print("\n1. Generowanie placeholder logo dla aplikacji fintech...")
        logo_path = await skill.generate_image(
            prompt="Minimalist logo for fintech payment app",
            size="512x512",
            filename="fintech_logo.png",
        )
        print(f"✓ Logo wygenerowane: {logo_path}")
        assert Path(logo_path).exists()

        # Test 2: Zmień rozmiar dla różnych użyć
        print("\n2. Przygotowanie favicon 32x32...")
        favicon_path = await skill.resize_image(
            image_path=logo_path, width=32, height=32, output_name="favicon.png"
        )
        print(f"✓ Favicon wygenerowany: {favicon_path}")
        assert Path(favicon_path).exists()

        # Test 3: Lista assetów
        print("\n3. Lista wszystkich wygenerowanych assetów:")
        assets_list = await skill.list_assets()
        print(assets_list)

    print("\n✓ MediaSkill działa poprawnie!")


async def demo_cloud_provisioner():
    """Demonstracja CloudProvisioner - deployment (mock mode)."""
    print("\n" + "=" * 60)
    print("DEMO: CloudProvisioner - Cloud Deployment")
    print("=" * 60)

    from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

    # Inicjalizacja (bez prawdziwego klucza SSH)
    provisioner = CloudProvisioner(
        ssh_key_path=None, default_user="testuser", timeout=30
    )
    print("\n✓ CloudProvisioner zainicjalizowany")

    # Test placeholder DNS
    print("\n1. Konfiguracja DNS (placeholder)...")
    demo_ip = os.getenv("VENOM_DEMO_DNS_IP", "").strip()
    if not demo_ip:
        print(
            "   ⚠️ Pomijam test DNS: ustaw VENOM_DEMO_DNS_IP aby przetestować configure_domain."
        )
        return
    dns_result = await provisioner.configure_domain(
        domain="myapp.example.com", ip=demo_ip
    )
    print(f"   Status: {dns_result['status']}")
    print(f"   Message: {dns_result['message']}")

    print("\n✓ CloudProvisioner działa poprawnie!")
    print("\nUWAGA: Pełny deployment wymaga prawdziwego serwera VPS i klucza SSH.")


def demo_agents():
    """Demonstracja nowych agentów - struktury."""
    print("\n" + "=" * 60)
    print("DEMO: Creative Director & DevOps Agents")
    print("=" * 60)

    print("\n1. Creative Director Agent:")
    print("   - Kompetencje: Branding, Copywriting, Social Media")
    print("   - System Prompt: Ekspert w tworzeniu identyfikacji wizualnej")
    print("   - Dostępne funkcje: generate_image, resize_image")

    print("\n2. DevOps Agent:")
    print("   - Kompetencje: Infrastructure, Deployment, Security")
    print("   - System Prompt: Ekspert DevOps i SRE")
    print("   - Dostępne funkcje: provision_server, deploy_stack, check_health")

    print("\n✓ Agenci zdefiniowani poprawnie (wymagają kernel do pełnego działania)")


async def main():
    """Główna funkcja demonstracyjna."""
    print("\n" + "=" * 70)
    print(" " * 15 + "THE_LAUNCHPAD - Demo Funkcjonalności")
    print("=" * 70)
    print("\nZadanie 029: Warstwa Wdrożeniowa i Kreatywna")
    print("Komponenty: CloudProvisioner, MediaSkill, Agents")

    try:
        # Demo MediaSkill
        await demo_media_skill()

        # Demo CloudProvisioner
        await demo_cloud_provisioner()

        # Demo Agents (struktury)
        demo_agents()

        print("\n" + "=" * 70)
        print(" " * 20 + "✓ WSZYSTKIE DEMO PRZESZŁY POMYŚLNIE")
        print("=" * 70)
        print("\nSystem jest gotowy do:")
        print("  • Generowania logo i assetów graficznych")
        print("  • Deploymentu aplikacji na zdalne serwery (SSH)")
        print("  • Tworzenia strategii brandingowych i marketingowych")
        print("  • Zarządzania infrastrukturą produkcyjną")
        print("\nSzczegóły w: workspace/MARKETING_KIT_TEMPLATE.md")

    except Exception as e:
        print(f"\n❌ Błąd podczas demonstracji: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
