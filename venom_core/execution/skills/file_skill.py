"""Moduł: file_skill - zarządzanie operacjami plikowymi z sandboxingiem."""

import json
import os
import shutil
from pathlib import Path
from typing import Annotated, Any, Optional

import aiofiles
from semantic_kernel.functions import kernel_function

from venom_core.core.autonomy_enforcement import require_file_write_permission
from venom_core.execution.skills.base_skill import (
    BaseSkill,
    async_safe_action,
    safe_action,
)
from venom_core.services.audit_stream import get_audit_stream


class FileSkill(BaseSkill):
    """
    Skill do bezpiecznych operacji plikowych.
    Wszystkie operacje są ograniczone do WORKSPACE_ROOT.

    Rozszerza BaseSkill o:
    - write_file
    - read_file
    - list_files
    - file_exists
    - rename_path
    - move_path
    - copy_path
    - delete_path
    - batch_file_operations
    """

    ALLOWED_OVERWRITE_POLICIES = {"forbid", "overwrite", "skip"}
    DRY_RUN_MESSAGE = "Dry-run: operacja zaplanowana, bez zmian na dysku"
    SUCCESS_MESSAGE = "Operacja zakończona pomyślnie"

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja FileSkill.
        """
        super().__init__(workspace_root)

    @kernel_function(
        name="write_file",
        description="Zapisuje treść do pliku w workspace. Tworzy katalogi jeśli nie istnieją.",
    )
    @async_safe_action
    async def write_file(
        self,
        file_path: Annotated[
            str,
            "Ścieżka do pliku względem workspace (np. 'test.py', 'subdir/file.txt')",
        ],
        content: Annotated[str, "Treść do zapisania w pliku"],
    ) -> str:
        """
        Zapisuje treść do pliku asynchronicznie.
        """
        require_file_write_permission()

        safe_path = self.validate_path(file_path)

        # Utwórz katalogi nadrzędne jeśli nie istnieją
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Zapisz plik asynchronicznie
        async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
            await f.write(content)

        self.logger.info(f"Zapisano plik: {safe_path}")
        return f"Plik '{file_path}' został pomyślnie zapisany ({len(content)} znaków)"

    @kernel_function(
        name="read_file",
        description="Odczytuje treść pliku z workspace.",
    )
    @async_safe_action
    async def read_file(
        self,
        file_path: Annotated[str, "Ścieżka do pliku względem workspace"],
    ) -> str:
        """
        Odczytuje treść pliku asynchronicznie.
        """
        safe_path = self.validate_path(file_path)

        if not safe_path.exists():
            raise FileNotFoundError(f"Plik '{file_path}' nie istnieje")

        if not safe_path.is_file():
            raise IOError(f"'{file_path}' nie jest plikiem")

        # Odczytaj plik asynchronicznie
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:
            content = await f.read()

        self.logger.info(f"Odczytano plik: {safe_path} ({len(content)} znaków)")
        return content

    def _serialize_report(self, payload: dict[str, Any]) -> str:
        """Serializuje raport operacji do deterministycznego JSON."""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _publish_fileop_audit(self, payload: dict[str, Any]) -> None:
        """Publikuje canonical audit event dla operacji file ops."""
        try:
            operation = str(payload.get("operation") or "file_operation")
            status = str(payload.get("status") or "unknown")
            get_audit_stream().publish(
                source="core.file_ops",
                action=f"file.{operation}",
                actor="file.skill",
                status=status,
                context=str(
                    payload.get("context")
                    or payload.get("source_path")
                    or payload.get("target_path")
                    or ""
                ),
                details=payload,
            )
        except Exception:
            # Audyt ma być best-effort i nie może blokować operacji.
            self.logger.debug(
                "Nie udało się opublikować audytu file_ops", exc_info=True
            )

    def _to_relative(self, path: Path) -> str:
        """Zwraca ścieżkę względną względem workspace."""
        return str(path.relative_to(self.workspace_root))

    def _normalize_overwrite_policy(self, overwrite_policy: str) -> str:
        policy = (overwrite_policy or "").strip().lower()
        if policy not in self.ALLOWED_OVERWRITE_POLICIES:
            allowed = ", ".join(sorted(self.ALLOWED_OVERWRITE_POLICIES))
            raise ValueError(
                f"Nieobsługiwana overwrite_policy='{overwrite_policy}'. "
                f"Dozwolone: {allowed}"
            )
        return policy

    def _coerce_bool(self, value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    def _coerce_overwrite_policy(self, value: Any, default: str) -> str:
        if value is None:
            return self._normalize_overwrite_policy(default)
        if not isinstance(value, str):
            raise ValueError("overwrite_policy musi być stringiem")
        return self._normalize_overwrite_policy(value)

    def _assert_not_workspace_root(self, path: Path, role: str) -> None:
        if path == self.workspace_root:
            raise ValueError(f"Operacja na root workspace jest zabroniona ({role})")

    def _remove_existing_path(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
            return
        path.unlink()

    def _build_result(
        self,
        *,
        operation: str,
        source: Optional[Path] = None,
        target: Optional[Path] = None,
        status: str,
        dry_run: bool,
        changed: bool,
        message: str,
        rollback: Optional[dict[str, Any]] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "operation": operation,
            "status": status,
            "dry_run": dry_run,
            "changed": changed,
            "message": message,
        }
        if source is not None:
            payload["source_path"] = self._to_relative(source)
        if target is not None:
            payload["target_path"] = self._to_relative(target)
        if rollback is not None:
            payload["rollback"] = rollback
        if details:
            payload["details"] = details
        return payload

    def _rename_like(
        self,
        *,
        operation: str,
        source_path: str,
        target_path: str,
        dry_run: bool,
        overwrite_policy: str,
    ) -> dict[str, Any]:
        policy = self._normalize_overwrite_policy(overwrite_policy)
        safe_source = self.validate_path(source_path)
        safe_target = self.validate_path(target_path)
        self._assert_not_workspace_root(safe_source, "source")
        self._assert_not_workspace_root(safe_target, "target")

        if not safe_source.exists():
            raise FileNotFoundError(f"Źródło nie istnieje: '{source_path}'")

        if safe_source == safe_target:
            return self._build_result(
                operation=operation,
                source=safe_source,
                target=safe_target,
                status="skipped",
                dry_run=dry_run,
                changed=False,
                message="Źródło i cel są takie same",
            )

        if safe_target.exists():
            if policy == "forbid":
                raise FileExistsError(f"Cel już istnieje: '{target_path}'")
            if policy == "skip":
                return self._build_result(
                    operation=operation,
                    source=safe_source,
                    target=safe_target,
                    status="skipped",
                    dry_run=dry_run,
                    changed=False,
                    message=f"Pominięto, bo cel istnieje i overwrite_policy={policy}",
                )

        if dry_run:
            return self._build_result(
                operation=operation,
                source=safe_source,
                target=safe_target,
                status="dry_run",
                dry_run=True,
                changed=False,
                message=self.DRY_RUN_MESSAGE,
                rollback={
                    "operation": operation,
                    "source_path": target_path,
                    "target_path": source_path,
                },
                details={"would_change": True, "overwrite_policy": policy},
            )

        safe_target.parent.mkdir(parents=True, exist_ok=True)
        if safe_target.exists() and policy == "overwrite":
            self._remove_existing_path(safe_target)

        if operation == "move_path":
            shutil.move(str(safe_source), str(safe_target))
        else:
            safe_source.rename(safe_target)
        return self._build_result(
            operation=operation,
            source=safe_source,
            target=safe_target,
            status="success",
            dry_run=False,
            changed=True,
            message=self.SUCCESS_MESSAGE,
            rollback={
                "operation": operation,
                "source_path": target_path,
                "target_path": source_path,
            },
            details={"overwrite_policy": policy},
        )

    def _copy_single(
        self,
        *,
        source_path: str,
        target_path: str,
        dry_run: bool,
        overwrite_policy: str,
        recursive: bool,
    ) -> dict[str, Any]:
        policy = self._normalize_overwrite_policy(overwrite_policy)
        safe_source = self.validate_path(source_path)
        safe_target = self.validate_path(target_path)
        self._assert_not_workspace_root(safe_source, "source")
        self._assert_not_workspace_root(safe_target, "target")

        if not safe_source.exists():
            raise FileNotFoundError(f"Źródło nie istnieje: '{source_path}'")

        is_dir = safe_source.is_dir()
        if is_dir and not recursive:
            raise IsADirectoryError(
                "Kopiowanie katalogu wymaga recursive=True dla copy_path"
            )

        if safe_target.exists():
            if policy == "forbid":
                raise FileExistsError(f"Cel już istnieje: '{target_path}'")
            if policy == "skip":
                return self._build_result(
                    operation="copy_path",
                    source=safe_source,
                    target=safe_target,
                    status="skipped",
                    dry_run=dry_run,
                    changed=False,
                    message=f"Pominięto, bo cel istnieje i overwrite_policy={policy}",
                )

        if dry_run:
            return self._build_result(
                operation="copy_path",
                source=safe_source,
                target=safe_target,
                status="dry_run",
                dry_run=True,
                changed=False,
                message=self.DRY_RUN_MESSAGE,
                rollback={
                    "operation": "delete_path",
                    "file_path": target_path,
                    "recursive": is_dir,
                },
                details={
                    "recursive": recursive,
                    "would_change": True,
                    "overwrite_policy": policy,
                },
            )

        safe_target.parent.mkdir(parents=True, exist_ok=True)
        if safe_target.exists() and policy == "overwrite":
            self._remove_existing_path(safe_target)

        if is_dir:
            shutil.copytree(safe_source, safe_target)
        else:
            shutil.copy2(safe_source, safe_target)

        return self._build_result(
            operation="copy_path",
            source=safe_source,
            target=safe_target,
            status="success",
            dry_run=False,
            changed=True,
            message=self.SUCCESS_MESSAGE,
            rollback={
                "operation": "delete_path",
                "file_path": target_path,
                "recursive": is_dir,
            },
            details={"recursive": recursive, "overwrite_policy": policy},
        )

    def _delete_single(
        self,
        *,
        file_path: str,
        dry_run: bool,
        recursive: bool,
    ) -> dict[str, Any]:
        safe_path = self.validate_path(file_path)
        self._assert_not_workspace_root(safe_path, "file_path")

        if not safe_path.exists():
            raise FileNotFoundError(f"Ścieżka nie istnieje: '{file_path}'")

        is_dir = safe_path.is_dir() and not safe_path.is_symlink()
        if is_dir and not recursive:
            raise IsADirectoryError(
                "Usunięcie katalogu wymaga recursive=True dla delete_path"
            )

        if dry_run:
            return self._build_result(
                operation="delete_path",
                source=safe_path,
                status="dry_run",
                dry_run=True,
                changed=False,
                message=self.DRY_RUN_MESSAGE,
                details={
                    "recursive": recursive,
                    "would_change": True,
                    "rollback_supported": False,
                },
            )

        if is_dir:
            shutil.rmtree(safe_path)
        else:
            safe_path.unlink()

        return self._build_result(
            operation="delete_path",
            source=safe_path,
            status="success",
            dry_run=False,
            changed=True,
            message=self.SUCCESS_MESSAGE,
            details={"recursive": recursive, "rollback_supported": False},
        )

    @kernel_function(
        name="rename_path",
        description="Zmienia nazwę ścieżki w workspace (plik lub katalog).",
    )
    @safe_action
    def rename_path(
        self,
        source_path: Annotated[str, "Źródłowa ścieżka względem workspace"],
        target_path: Annotated[str, "Docelowa ścieżka względem workspace"],
        dry_run: Annotated[
            bool, "Jeśli True, tylko planuje operację bez wykonania"
        ] = False,
        overwrite_policy: Annotated[
            str,
            "Polityka konfliktu celu: forbid|overwrite|skip (domyślnie forbid)",
        ] = "forbid",
    ) -> str:
        require_file_write_permission()
        report = self._rename_like(
            operation="rename_path",
            source_path=source_path,
            target_path=target_path,
            dry_run=dry_run,
            overwrite_policy=overwrite_policy,
        )
        self._publish_fileop_audit(report)
        return self._serialize_report(report)

    @kernel_function(
        name="move_path",
        description="Przenosi ścieżkę w workspace (plik lub katalog).",
    )
    @safe_action
    def move_path(
        self,
        source_path: Annotated[str, "Źródłowa ścieżka względem workspace"],
        target_path: Annotated[str, "Docelowa ścieżka względem workspace"],
        dry_run: Annotated[
            bool, "Jeśli True, tylko planuje operację bez wykonania"
        ] = False,
        overwrite_policy: Annotated[
            str,
            "Polityka konfliktu celu: forbid|overwrite|skip (domyślnie forbid)",
        ] = "forbid",
    ) -> str:
        require_file_write_permission()
        report = self._rename_like(
            operation="move_path",
            source_path=source_path,
            target_path=target_path,
            dry_run=dry_run,
            overwrite_policy=overwrite_policy,
        )
        self._publish_fileop_audit(report)
        return self._serialize_report(report)

    @kernel_function(
        name="copy_path",
        description="Kopiuje plik lub katalog w obrębie workspace.",
    )
    @safe_action
    def copy_path(
        self,
        source_path: Annotated[str, "Źródłowa ścieżka względem workspace"],
        target_path: Annotated[str, "Docelowa ścieżka względem workspace"],
        dry_run: Annotated[
            bool, "Jeśli True, tylko planuje operację bez wykonania"
        ] = False,
        overwrite_policy: Annotated[
            str,
            "Polityka konfliktu celu: forbid|overwrite|skip (domyślnie forbid)",
        ] = "forbid",
        recursive: Annotated[
            bool,
            "Dla katalogów: jeśli True kopiuje rekurencyjnie (domyślnie False)",
        ] = False,
    ) -> str:
        require_file_write_permission()
        report = self._copy_single(
            source_path=source_path,
            target_path=target_path,
            dry_run=dry_run,
            overwrite_policy=overwrite_policy,
            recursive=recursive,
        )
        self._publish_fileop_audit(report)
        return self._serialize_report(report)

    @kernel_function(
        name="delete_path",
        description="Usuwa plik lub katalog z workspace.",
    )
    @safe_action
    def delete_path(
        self,
        file_path: Annotated[str, "Ścieżka do usunięcia względem workspace"],
        dry_run: Annotated[
            bool, "Jeśli True, tylko planuje operację bez wykonania"
        ] = False,
        recursive: Annotated[
            bool,
            "Dla katalogów: jeśli True usuwa rekurencyjnie (domyślnie False)",
        ] = False,
    ) -> str:
        require_file_write_permission()
        report = self._delete_single(
            file_path=file_path,
            dry_run=dry_run,
            recursive=recursive,
        )
        self._publish_fileop_audit(report)
        return self._serialize_report(report)

    def _normalize_batch_action(self, action: str) -> str:
        normalized = (action or "").strip().lower()
        aliases = {
            "rename": "rename_path",
            "rename_path": "rename_path",
            "move": "move_path",
            "move_path": "move_path",
            "copy": "copy_path",
            "copy_path": "copy_path",
            "delete": "delete_path",
            "delete_path": "delete_path",
        }
        if normalized not in aliases:
            raise ValueError(f"Nieobsługiwana akcja batch: '{action}'")
        return aliases[normalized]

    def _parse_batch_operations(self, operations_json: str) -> list[dict[str, Any]]:
        payload = json.loads(operations_json)
        if not isinstance(payload, list):
            raise ValueError("operations_json musi zawierać listę operacji JSON")
        if not payload:
            raise ValueError("Lista operacji batch nie może być pusta")
        normalized: list[dict[str, Any]] = []
        for index, operation in enumerate(payload):
            if not isinstance(operation, dict):
                raise ValueError(f"Operacja batch na pozycji {index} nie jest obiektem")
            normalized.append(operation)
        return normalized

    def _run_batch_operation(
        self,
        operation: dict[str, Any],
        *,
        default_dry_run: bool,
        default_overwrite_policy: str,
    ) -> dict[str, Any]:
        action = self._normalize_batch_action(str(operation.get("action", "")))
        dry_run = self._coerce_bool(operation.get("dry_run"), default_dry_run)
        overwrite_policy = self._coerce_overwrite_policy(
            operation.get("overwrite_policy"), default_overwrite_policy
        )

        if action in {"rename_path", "move_path", "copy_path"}:
            source_raw = operation.get("source_path", operation.get("source"))
            target_raw = operation.get("target_path", operation.get("target"))
            if not isinstance(source_raw, str) or not isinstance(target_raw, str):
                raise ValueError(
                    f"Operacja {action} wymaga source_path/source i target_path/target"
                )

            if action == "rename_path":
                return self._rename_like(
                    operation="rename_path",
                    source_path=source_raw,
                    target_path=target_raw,
                    dry_run=dry_run,
                    overwrite_policy=overwrite_policy,
                )
            if action == "move_path":
                return self._rename_like(
                    operation="move_path",
                    source_path=source_raw,
                    target_path=target_raw,
                    dry_run=dry_run,
                    overwrite_policy=overwrite_policy,
                )

            recursive = self._coerce_bool(operation.get("recursive"), False)
            return self._copy_single(
                source_path=source_raw,
                target_path=target_raw,
                dry_run=dry_run,
                overwrite_policy=overwrite_policy,
                recursive=recursive,
            )

        file_path_raw = operation.get("file_path", operation.get("path"))
        if not isinstance(file_path_raw, str):
            raise ValueError("Operacja delete_path wymaga file_path/path")
        recursive = self._coerce_bool(operation.get("recursive"), False)
        return self._delete_single(
            file_path=file_path_raw,
            dry_run=dry_run,
            recursive=recursive,
        )

    @kernel_function(
        name="batch_file_operations",
        description=(
            "Wykonuje operacje plikowe batch (rename/move/copy/delete) "
            "na podstawie listy JSON."
        ),
    )
    @safe_action
    def batch_file_operations(
        self,
        operations_json: Annotated[
            str,
            (
                "Lista operacji JSON, np. "
                '[{"action":"move","source_path":"a.txt","target_path":"b.txt"}]'
            ),
        ],
        dry_run: Annotated[
            bool, "Domyślny dry_run dla operacji bez jawnego dry_run"
        ] = False,
        overwrite_policy: Annotated[
            str,
            "Domyślna overwrite_policy: forbid|overwrite|skip (domyślnie forbid)",
        ] = "forbid",
        continue_on_error: Annotated[
            bool,
            "Jeśli True, batch kontynuuje po błędzie pojedynczej operacji",
        ] = False,
    ) -> str:
        require_file_write_permission()
        default_policy = self._normalize_overwrite_policy(overwrite_policy)
        operations = self._parse_batch_operations(operations_json)
        results: list[dict[str, Any]] = []
        failures = 0

        for index, operation in enumerate(operations):
            try:
                result = self._run_batch_operation(
                    operation,
                    default_dry_run=dry_run,
                    default_overwrite_policy=default_policy,
                )
                result["index"] = index
                results.append(result)
            except Exception as exc:
                failures += 1
                failure = {
                    "index": index,
                    "operation": str(operation.get("action", "unknown")),
                    "status": "failed",
                    "dry_run": self._coerce_bool(operation.get("dry_run"), dry_run),
                    "changed": False,
                    "message": str(exc),
                }
                results.append(failure)
                if not continue_on_error:
                    break

        succeeded = sum(1 for item in results if item.get("status") != "failed")
        if failures:
            batch_status = "failed"
        elif dry_run:
            batch_status = "dry_run"
        else:
            batch_status = "success"
        payload = {
            "operation": "batch_file_operations",
            "status": batch_status,
            "context": f"batch:{len(results)}",
            "dry_run": dry_run,
            "overwrite_policy": default_policy,
            "continue_on_error": continue_on_error,
            "operations_total": len(operations),
            "operations_executed": len(results),
            "operations_succeeded": succeeded,
            "operations_failed": failures,
            "changed": any(result.get("changed", False) for result in results),
            "results": results,
        }
        self._publish_fileop_audit(payload)
        return self._serialize_report(payload)

    @kernel_function(
        name="list_files",
        description="Listuje pliki i katalogi w workspace. Może listować rekurencyjnie z konfigurowalną głębokością.",
    )
    @safe_action
    def list_files(
        self,
        directory: Annotated[
            str, "Katalog względem workspace (domyślnie '.', czyli root workspace)"
        ] = ".",
        recursive: Annotated[
            bool, "Czy listować rekurencyjnie (domyślnie False)"
        ] = False,
        max_depth: Annotated[int, "Maksymalna głębokość rekurencji (domyślnie 3)"] = 3,
    ) -> str:
        """
        Listuje pliki i katalogi w podanym katalogu.
        """
        safe_path = self.validate_path(directory)
        if not safe_path.exists():
            return f"Katalog '{directory}' nie istnieje"
        if not safe_path.is_dir():
            return f"'{directory}' nie jest katalogiem"
        if recursive:
            return self._list_files_recursive(directory, safe_path, max_depth)
        return self._list_files_flat(directory, safe_path)

    def _list_files_recursive(
        self, directory: str, safe_path: Path, max_depth: int
    ) -> str:
        items = [
            f"Zawartość katalogu '{directory}' (rekurencyjnie, max {max_depth} poziomy):\n"
        ]
        skipped_files = 0

        for root, dirs, files in os.walk(safe_path):
            depth = self._get_relative_depth(root, safe_path)
            if depth > max_depth:
                dirs.clear()
                continue
            indent = "  " * depth
            self._append_recursive_dirs(items, dirs, root, depth, max_depth)
            if depth >= max_depth:
                dirs.clear()
            skipped_files += self._append_recursive_files(items, files, root, indent)

        if skipped_files > 0:
            self.logger.warning(f"Pominięto {skipped_files} niedostępnych plików")
        if len(items) == 1:
            items.append("  (katalog pusty)")
        self.logger.info(
            f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive=True)"
        )
        return "\n".join(items)

    def _list_files_flat(self, directory: str, safe_path: Path) -> str:
        items = []
        for item in sorted(safe_path.iterdir()):
            stat_result = item.stat()
            item_type = "katalog" if item.is_dir() else "plik"
            relative_path = item.relative_to(self.workspace_root)
            size = str(stat_result.st_size) if item.is_file() else "-"
            items.append(f"  [{item_type}] {relative_path} ({size} bajtów)")

        if not items:
            return f"Katalog '{directory}' jest pusty"

        items.insert(0, f"Zawartość katalogu '{directory}':")
        self.logger.info(
            f"Wylistowano {len(items) - 1} elementów w: {safe_path} (recursive=False)"
        )
        return "\n".join(items)

    def _get_relative_depth(self, root: str, safe_path: Path) -> int:
        try:
            return len(Path(root).relative_to(safe_path).parts)
        except ValueError:
            return 0

    def _append_recursive_dirs(
        self,
        items: list[str],
        dirs: list[str],
        root: str,
        depth: int,
        max_depth: int,
    ) -> None:
        if depth >= max_depth:
            return
        indent = "  " * depth
        for dir_name in sorted(dirs):
            dir_path = Path(root) / dir_name
            rel_path = dir_path.relative_to(self.workspace_root)
            items.append(f"{indent}[katalog] {rel_path}/")

    def _append_recursive_files(
        self, items: list[str], files: list[str], root: str, indent: str
    ) -> int:
        skipped = 0
        for file_name in sorted(files):
            file_path = Path(root) / file_name
            try:
                stat_result = file_path.stat()
                size = str(stat_result.st_size)
                rel_path = file_path.relative_to(self.workspace_root)
                items.append(f"{indent}[plik] {rel_path} ({size} bajtów)")
            except Exception:
                skipped += 1
        return skipped

    @kernel_function(
        name="file_exists",
        description="Sprawdza czy plik lub katalog istnieje w workspace.",
    )
    def file_exists(
        self,
        file_path: Annotated[str, "Ścieżka do pliku/katalogu względem workspace"],
    ) -> str:
        # Ten wrapper manualny symuluje safe_action dla synchronicznej metody
        # (metody kernel_function w SK mogą być sync lub async)
        try:
            safe_path = self.validate_path(file_path)
            exists = safe_path.exists()
            self.logger.info(f"Sprawdzono istnienie: {safe_path} = {exists}")
            return "True" if exists else "False"
        except Exception as e:
            # Używamy logiki z BaseSkill.safe_action
            if hasattr(self, "logger"):
                self.logger.error(f"Błąd w file_exists: {e}", exc_info=True)
            return f"❌ Wystąpił błąd: {str(e)}"
