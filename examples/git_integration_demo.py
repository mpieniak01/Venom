"""Demo: Git Integration & DevOps Workflow

Ten przykład pokazuje jak używać GitSkill i IntegratorAgent do zarządzania repozytorium Git.
"""

import asyncio
import tempfile
from pathlib import Path

from venom_core.execution.skills.git_skill import GitSkill


async def demo_git_workflow():
    """Demonstracja workflow Git z GitSkill."""
    print("🕷️ Venom Git Integration Demo\n")
    print("=" * 60)

    # Utwórz tymczasowy workspace dla demo
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Workspace: {temp_dir}\n")

    # Utwórz GitSkill
    git = GitSkill(workspace_root=temp_dir)

    # 1. Inicjalizacja repozytorium
    print("1️⃣ Inicjalizacja repozytorium Git...")
    result = await git.init_repo()
    print(f"   {result}\n")

    # 2. Sprawdź aktualny branch
    print("2️⃣ Sprawdzanie aktualnego brancha...")
    branch = await git.get_current_branch()
    print(f"   Aktualny branch: {branch}\n")

    # 3. Utwórz plik
    print("3️⃣ Tworzenie pliku test.py...")
    test_file = Path(temp_dir) / "test.py"
    test_file.write_text('def hello():\n    print("Hello from Venom!")\n')
    print("   ✅ Plik utworzony\n")

    # 4. Sprawdź status
    print("4️⃣ Sprawdzanie statusu Git...")
    status = await git.get_status()
    print(f"   Status:\n{status}\n")

    # 5. Stage pliki
    print("5️⃣ Stage'owanie plików...")
    result = await git.add_files(["."])
    print(f"   {result}\n")

    # 6. Commit
    print("6️⃣ Tworzenie commita...")
    result = await git.commit("feat(demo): add hello function")
    print(f"   {result}\n")

    # 7. Utwórz nowy branch
    print("7️⃣ Tworzenie nowego brancha...")
    result = await git.checkout("feat/new-feature", create_new=True)
    print(f"   {result}\n")

    # 8. Sprawdź aktualny branch
    print("8️⃣ Sprawdzanie aktualnego brancha...")
    branch = await git.get_current_branch()
    print(f"   Aktualny branch: {branch}\n")

    # 9. Dodaj kolejny plik
    print("9️⃣ Dodawanie kolejnego pliku...")
    feature_file = Path(temp_dir) / "feature.py"
    feature_file.write_text('def feature():\n    return "New feature"\n')
    print("   ✅ Plik utworzony\n")

    # 10. Commit zmian
    print("🔟 Commitowanie zmian...")
    await git.add_files(["."])
    result = await git.commit("feat(feature): add new feature function")
    print(f"   {result}\n")

    # 11. Zobacz historię
    print("1️⃣1️⃣ Historia commitów...")
    history = await git.get_last_commit_log(n=5)
    print(f"   Historia:\n{history}\n")

    # 12. Sprawdź diff (po modyfikacji pliku)
    print("1️⃣2️⃣ Modyfikacja pliku i sprawdzenie diff...")
    feature_file.write_text('def feature():\n    return "Updated feature"\n')
    diff = await git.get_diff()
    print(f"   Diff:\n{diff[:200]}...\n")

    print("=" * 60)
    print("✅ Demo zakończone!\n")
    print(f"💡 Tip: Workspace znajduje się w {temp_dir}")
    print("   Możesz go sprawdzić komendami git lub usunąć ręcznie.\n")


if __name__ == "__main__":
    asyncio.run(demo_git_workflow())
