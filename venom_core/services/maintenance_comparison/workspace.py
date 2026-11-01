"""Trial copies are exports of one commit, never the operator's dirty tree."""

import difflib
import hashlib
import os
import subprocess
import tarfile
from pathlib import Path

EXCLUDED = {"__pycache__", ".pytest_cache"}
GIT_BOOKKEEPING = {
    "index",
    "objects",
    "logs",
    "COMMIT_EDITMSG",
    "FETCH_HEAD",
    "ORIG_HEAD",
}


def snapshot(root: Path) -> dict[str, str]:
    """Hash files and symlink targets, excluding transient caches and Git bookkeeping."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if (
            relative.parts[0] == ".git"
            and len(relative.parts) > 1
            and relative.parts[1] in GIT_BOOKKEEPING
        ):
            continue
        if path.is_symlink():
            result[str(relative)] = "symlink:" + str(path.readlink())
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(65536):
                    digest.update(chunk)
            result[str(relative)] = digest.hexdigest()
    return result


def prepare(repo: Path, sha: str, target: Path, case) -> dict[str, str]:
    """Export a pinned commit into a new private trial copy and apply its controlled fixture."""
    if target.exists():
        raise ValueError("trial_workspace_must_be_new")
    target.mkdir(parents=True, mode=0o700)
    archive_path = target.parent / (target.name + ".tar")
    with archive_path.open("wb") as output:
        subprocess.run(
            ["git", "archive", "--format=tar", sha], cwd=repo, stdout=output, check=True
        )
    try:
        with tarfile.open(archive_path) as archive:
            archive.extractall(target, filter="data")
    finally:
        archive_path.unlink()
    for name, text in case.files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if case.role == "operator" and case.id in {"operator-02", "operator-03"}:
        (target / "operator_notes.md").write_text("old\n")
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=experiment"], cwd=target, check=True
    )
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=VenomExperiment",
            "-c",
            "user.email=experiment@localhost",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Controlled trial baseline",
        ],
        cwd=target,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        },
        check=True,
    )
    if case.id in {"operator-02", "operator-03"}:
        (target / "operator_notes.md").write_text("new\n")
    return snapshot(target)


def changed_files(before: dict[str, str], after: dict[str, str]) -> set[str]:
    """Return paths added, removed or changed between two workspace snapshots."""
    return {
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    }


def patch(case, root: Path) -> str:
    """Produce diffs only for allowed small regular files, ignoring symlinks."""
    parts: list[str] = []
    for name in case.allowed_changes:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
            continue
        parts.extend(
            difflib.unified_diff(
                case.files.get(name, "").splitlines(True),
                path.read_text().splitlines(True),
                fromfile="a/" + name,
                tofile="b/" + name,
            )
        )
    return "".join(parts)
