#!/usr/bin/env python3
"""Generate installation inputs and platform locks from one dependency policy.

Locking uses pip's real resolver in a disposable subprocess, never the installed
working environment as evidence. Only declared PyPI artifacts can enter locks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
POLICY = "config/dependency-profiles.json"
LOCK_LINE = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \\]+)")
SHA256 = re.compile(r"[a-f0-9]{64}")


def policy_hash(policy: dict[str, Any]) -> str:
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if Path(relative).is_absolute() or not target.is_relative_to(root.resolve()):
        raise ValueError(f"Path must remain inside repository: {relative}")
    return target


def requirements_for(policy: dict[str, Any], profile: str) -> dict[str, str]:
    profiles = policy["profiles"]
    collected: dict[str, str] = {}
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            raise ValueError(f"Cyclic profile inheritance: {name}")
        if name not in profiles:
            raise ValueError(f"Unknown profile: {name}")
        visited.add(name)
        spec = profiles[name]
        if spec.get("extends"):
            visit(spec["extends"])
        for group in spec["groups"]:
            for line in policy["groups"][group]:
                req = Requirement(line)
                package = canonicalize_name(req.name)
                previous = collected.get(package)
                if previous and Requirement(previous) != req:
                    raise ValueError(
                        f"Conflicting policies for {package}: {previous} / {line}"
                    )
                collected[package] = line
        visited.remove(name)

    visit(profile)
    check_packages(policy, profile, set(collected))
    return collected


def profile_policy_hash(policy: dict[str, Any], profile: str) -> str:
    """Changing an unrelated component must not invalidate a qualified base."""
    scope = {
        "platform": policy["platform"],
        "source": policy["source"],
        "kind": policy["profiles"][profile]["kind"],
        "requirements": requirements_for(policy, profile),
        "exclusive_distributions": policy["exclusive_distributions"],
    }
    if scope["kind"] == "application":
        scope["forbidden_application_packages"] = policy[
            "forbidden_application_packages"
        ]
    return policy_hash(scope)


def check_packages(policy: dict[str, Any], profile: str, packages: set[str]) -> None:
    for group in policy["exclusive_distributions"]:
        overlap = packages.intersection(group)
        if len(overlap) > 1:
            raise ValueError(f"Overlapping distribution namespaces: {sorted(overlap)}")
    if policy["profiles"][profile]["kind"] == "application":
        forbidden = packages.intersection(policy["forbidden_application_packages"])
        if forbidden:
            raise ValueError(f"Forbidden application packages: {sorted(forbidden)}")


def load_policy(root: Path = ROOT) -> dict[str, Any]:
    policy = json.loads((root / POLICY).read_text())
    if policy.get("schema_version") != 1:
        raise ValueError("Unsupported dependency policy schema")
    if policy.get("source") != "https://pypi.org/simple":
        raise ValueError("Only the declared official package source is supported")
    for name, spec in policy["profiles"].items():
        if spec["kind"] not in {"application", "component"}:
            raise ValueError(f"Invalid profile kind: {name}")
        safe_path(root, spec["input"])
        safe_path(root, spec["lock"])
        requirements_for(policy, name)
    for alias, profile in policy["aliases"].items():
        safe_path(root, alias)
        if profile not in policy["profiles"]:
            raise ValueError(f"Unknown alias profile: {profile}")
    generated_paths = (
        {spec["input"] for spec in policy["profiles"].values()}
        | set(policy["aliases"])
        | set(policy.get("constraint_groups", {}))
    )
    for name, spec in policy.get("deferred_profiles", {}).items():
        if name in policy["profiles"] or spec.get("status") != "deferred":
            raise ValueError(f"Invalid deferred profile: {name}")
        if not isinstance(spec.get("reason"), str) or not spec["reason"].strip():
            raise ValueError(f"Deferred profile requires a reason: {name}")
        if manifest := spec.get("manifest"):
            safe_path(root, manifest)
            if manifest in generated_paths:
                raise ValueError(f"Deferred manifest is managed: {manifest}")
    return policy


def require_active_profile(policy: dict[str, Any], profile: str) -> None:
    if profile in policy["profiles"]:
        return
    if profile in policy.get("deferred_profiles", {}):
        reason = policy["deferred_profiles"][profile]["reason"]
        raise ValueError(f"Dependency profile '{profile}' is deferred: {reason}")
    raise ValueError(f"Unknown profile: {profile}")


def generated_inputs(policy: dict[str, Any]) -> dict[str, str]:
    header = (
        "# Generated by scripts/dev/dependency_profiles.py; do not edit.\n"
        f"# Policy SHA256: {policy_hash(policy)}\n"
        "# Inputs are not a qualified lock; install a matching platform lock for releases.\n"
    )
    output = {}
    for name, spec in policy["profiles"].items():
        lines = [header, f"# Profile: {name} ({spec['kind']})\n"]
        if spec.get("boundary"):
            lines.append(f"# {spec['boundary']}\n")
        # SCM scanners discard -r/-c includes. Emit the complete profile so
        # remote scans and local pip receive identical direct requirements.
        requirements = requirements_for(policy, name)
        lines.extend(f"{req}\n" for _, req in sorted(requirements.items()))
        output[spec["input"]] = "".join(lines)
    for alias, profile in policy["aliases"].items():
        output[alias] = (
            header
            + f"# Compatibility alias for {profile}.\n"
            + "".join(
                f"{req}\n"
                for _, req in sorted(requirements_for(policy, profile).items())
            )
        )
    for filename, spec in policy.get("constraint_groups", {}).items():
        requirements = requirements_for(policy, spec["profile"])
        output[filename] = header + "".join(
            requirements[canonicalize_name(name)] + "\n" for name in spec["packages"]
        )
    return output


def generate(root: Path, policy: dict[str, Any], *, check: bool = False) -> list[str]:
    changed = []
    for filename, content in generated_inputs(policy).items():
        target = safe_path(root, filename)
        if not target.exists() or target.read_text() != content:
            changed.append(filename)
            if not check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
    return changed


def read_lock(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for line in path.read_text().splitlines():
        match = LOCK_LINE.match(line)
        if match:
            name = canonicalize_name(match[1])
            if name in packages:
                raise ValueError(f"Duplicate lock package: {name}")
            packages[name] = match[2]
    if not packages:
        raise ValueError(f"Empty or invalid lock: {path}")
    return packages


def check_artifact(name: str, url: object, digest: object) -> None:
    """Apply the same source and hash policy to resolver and receipt artifacts."""
    if not isinstance(url, str):
        raise ValueError(f"Unapproved artifact source for {name}")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "files.pythonhosted.org"
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"Unapproved artifact source for {name}")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError(f"Missing or invalid artifact hash for {name}")


def report_packages(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    if report.get("version") != "1" or not report.get("install"):
        raise ValueError("Incomplete pip resolver report")
    packages: dict[str, dict[str, str]] = {}
    for item in report["install"]:
        info = item["metadata"]
        name = canonicalize_name(info["name"])
        if name in packages:
            raise ValueError(f"Duplicate report package: {name}")
        download = item["download_info"]
        url = download["url"]
        digest = download.get("archive_info", {}).get("hashes", {}).get("sha256", "")
        check_artifact(name, url, digest)
        packages[name] = {"version": info["version"], "sha256": digest, "url": url}
    return packages


def check_direct_requirements(
    policy: dict[str, Any], profile: str, packages: dict[str, str]
) -> None:
    for name, line in requirements_for(policy, profile).items():
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        version = packages.get(name)
        if version is None or version not in requirement.specifier:
            raise ValueError(
                f"Missing or incompatible direct requirement in {profile}: {line}; got {version}"
            )


def inventory_delta(
    base: dict[str, str], candidate: dict[str, str]
) -> dict[str, dict[str, str | None]]:
    return {
        name: {"expected": version, "actual": candidate.get(name)}
        for name, version in sorted(base.items())
        if candidate.get(name) != version
    }


def render_lock(
    policy: dict[str, Any], profile: str, report: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    environment = report.get("environment", {})
    actual_target = {
        "python": environment.get("python_version"),
        "system": environment.get("platform_system"),
        "machine": environment.get("platform_machine"),
    }
    if actual_target != policy["platform"]:
        raise ValueError(
            f"Resolver interpreter does not match lock target: {actual_target}"
        )
    packages = report_packages(report)
    check_packages(policy, profile, set(packages))
    lines = [
        "# Generated by dependency_profiles.py using pip's real resolver.\n",
        f"# Profile: {profile}; target: Linux x86_64 / Python 3.12\n",
        f"# Profile policy SHA256: {profile_policy_hash(policy, profile)}\n",
        f"# Policy SHA256: {policy_hash(policy)}\n",
        "# Artifact hashes pin this platform; other platforms need separate qualification.\n",
        "--index-url https://pypi.org/simple\n",
    ]
    for name, item in sorted(packages.items()):
        lines.append(
            f"{name}=={item['version']} \\\n    --hash=sha256:{item['sha256']}\n"
        )
    content = "".join(lines)
    receipt = {
        "schema_version": 1,
        "profile": profile,
        "policy_sha256": policy_hash(policy),
        "profile_policy_sha256": profile_policy_hash(policy, profile),
        "lock_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "platform": policy["platform"],
        "resolver_environment": environment,
        "resolver": {"name": "pip", "version": report.get("pip_version")},
        "qualification": "RESOLVED_ONLY",
        "artifacts": packages,
    }
    return content, receipt


def lock_profile(root: Path, policy: dict[str, Any], profile: str, python: str) -> Path:
    target = policy["platform"]
    actual = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "system": platform.system(),
        "machine": platform.machine(),
    }
    if actual != target:
        raise ValueError(
            f"Locking requires declared target {target}; current interpreter is {actual}"
        )
    if generate(root, policy, check=True):
        raise ValueError("Generated inputs are stale; run generate first")
    spec = policy["profiles"][profile]
    with tempfile.TemporaryDirectory(prefix="venom-profile-resolve-") as scratch:
        report_path = Path(scratch) / "report.json"
        command = [
            python,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--ignore-installed",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--prefer-binary",
            "--report",
            str(report_path),
            "--index-url",
            policy["source"],
            "-r",
            str(root / spec["input"]),
        ]
        base = {}
        required_base = {}
        if spec.get("extends"):
            # Every application extension freezes the complete Light graph,
            # including transitive packages. A resolver conflict is explicit.
            base_name = spec["extends"]
            base_path = root / policy["profiles"][base_name]["lock"]
            base_text = base_path.read_text()
            if (
                f"# Profile policy SHA256: {profile_policy_hash(policy, base_name)}"
                not in base_text
            ):
                raise ValueError(
                    f"Parent {base_name} lock is stale; resolve parent before extensions"
                )
            base = read_lock(base_path)
            required_base = dict(base)
            # Freeze any already-qualified application lock's overlapping packages.
            # Constraints do not install CI-only packages in Full.
            for other_name, other in policy["profiles"].items():
                other_path = root / other["lock"]
                if (
                    other_name == profile
                    or other["kind"] != "application"
                    or not other_path.exists()
                ):
                    continue
                if (
                    f"# Profile policy SHA256: {profile_policy_hash(policy, other_name)}"
                    not in other_path.read_text()
                ):
                    continue
                for package, version in read_lock(other_path).items():
                    if package in base and base[package] != version:
                        raise ValueError(
                            f"Existing application locks disagree for {package}"
                        )
                    base[package] = version
            constraint = Path(scratch) / "base-constraints.txt"
            constraint.write_text(
                "".join(
                    f"{name}=={version}\n" for name, version in sorted(base.items())
                )
            )
            command.extend(["--constraint", str(constraint)])
        subprocess.run(command, check=True, cwd=root)
        report = json.loads(report_path.read_text())
        content, receipt = render_lock(policy, profile, report)
        candidate = {
            name: item["version"] for name, item in receipt["artifacts"].items()
        }
        check_direct_requirements(policy, profile, candidate)
        expected_shared = {
            name: version
            for name, version in base.items()
            if name in candidate or name in required_base
        }
        if delta := inventory_delta(expected_shared, candidate):
            raise ValueError(f"Application base fingerprint changed: {delta}")
        path = safe_path(root, spec["lock"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.with_suffix(".json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        return path


def check_lock_artifacts(path: Path, artifacts: dict[str, dict[str, str]]) -> None:
    """Match each generated lock entry to its approved receipt artifact."""
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        match = LOCK_LINE.match(line)
        if match is None:
            continue
        name = canonicalize_name(match[1])
        artifact = artifacts[name]
        check_artifact(name, artifact.get("url"), artifact.get("sha256"))
        expected = [
            f"{name}=={artifact['version']} \\",
            f"    --hash=sha256:{artifact['sha256']}",
        ]
        if lines[index : index + 2] != expected:
            raise ValueError(f"Lock artifact hash mismatch: {name}")


def audit_locks(root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    """Verify receipts, ownership and shared versions without importing a runtime."""
    applications: dict[str, dict[str, str]] = {}
    counts: dict[str, int] = {}
    for name, spec in policy["profiles"].items():
        path = safe_path(root, spec["lock"])
        receipt = json.loads(path.with_suffix(".json").read_text())
        if (
            receipt.get("profile") != name
            or receipt.get("lock_sha256")
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError(f"Lock receipt mismatch: {name}")
        if receipt.get("profile_policy_sha256") != profile_policy_hash(policy, name):
            raise ValueError(f"Stale lock policy: {name}")
        if receipt.get("platform") != policy["platform"]:
            raise ValueError(f"Lock receipt platform mismatch: {name}")
        locked = read_lock(path)
        artifacts = receipt.get("artifacts", {})
        expected = {package: item["version"] for package, item in artifacts.items()}
        if not expected or locked != expected:
            raise ValueError(f"Incomplete lock artifact inventory: {name}")
        check_lock_artifacts(path, artifacts)
        check_packages(policy, name, set(locked))
        check_direct_requirements(policy, name, locked)
        counts[name] = len(locked)
        if spec["kind"] == "application":
            for other, packages in applications.items():
                shared = {
                    package: version
                    for package, version in packages.items()
                    if package in locked
                }
                if difference := inventory_delta(shared, locked):
                    raise ValueError(
                        f"Shared application versions differ: {other}/{name}: {difference}"
                    )
            applications[name] = locked
    return {
        "status": "PASS",
        "packages": counts,
        "qualification": "LOCK_INTEGRITY_ONLY",
        "deferred_profiles": sorted(policy.get("deferred_profiles", {})),
    }


def verify_environment(
    root: Path, policy: dict[str, Any], profile: str, python: str
) -> dict[str, Any]:
    lock_path = root / policy["profiles"][profile]["lock"]
    if (
        f"# Profile policy SHA256: {profile_policy_hash(policy, profile)}"
        not in lock_path.read_text()
    ):
        raise ValueError("Environment lock is stale relative to dependency policy")
    expected = read_lock(lock_path)
    result = subprocess.run(
        [python, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
        capture_output=True,
        text=True,
        check=True,
    )
    inventory = json.loads(result.stdout)
    installed: dict[str, str] = {
        canonicalize_name(item["name"]): item["version"] for item in inventory
    }
    distribution_names = {
        canonicalize_name(item["name"]): item["name"] for item in inventory
    }
    check = subprocess.run(
        [python, "-m", "pip", "check"], capture_output=True, text=True, check=False
    )
    delta = inventory_delta(expected, installed)
    # The separately pinned bootstrap toolchain is the only permitted addition.
    # A Full environment cannot masquerade as a clean Light installation.
    bootstrap = requirements_for(policy, "build")
    # Bootstrap-only additions must satisfy their pinned policy too. Merely
    # allowlisting "pip" let vulnerable venv seed versions pass qualification.
    bootstrap_delta = {
        name: {"expected": line, "actual": installed[name]}
        for name, line in bootstrap.items()
        if name in installed
        and name not in expected
        and installed[name] not in Requirement(line).specifier
    }
    unexpected = sorted(set(installed) - set(expected) - set(bootstrap))
    check_packages(policy, profile, set(installed))
    clean = subprocess.run(
        [
            python,
            "-c",
            "import sys; from pathlib import Path; p=Path(sys.prefix)/'pyvenv.cfg'; print(p.read_text() if p.exists() else '')",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    isolated = "include-system-site-packages = false" in clean.stdout.lower()
    return {
        "profile": profile,
        "status": "PASS"
        if not delta
        and not bootstrap_delta
        and not unexpected
        and check.returncode == 0
        and isolated
        else "FAIL",
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "packages": installed,
        "distribution_names": distribution_names,
        "delta": delta,
        "unexpected_packages": unexpected,
        "bootstrap_delta": bootstrap_delta,
        "pip_check_exit": check.returncode,
        "pip_check": (check.stdout + check.stderr).strip(),
        "isolated_venv": isolated,
    }


def security_probe_packages(
    policy: dict[str, Any], profile: str, locked: dict[str, str], mode: str
) -> tuple[dict[str, str], list[str]]:
    """Choose actual lock versions or literal inclusive direct-version minima.

    A minimum probe is a component vulnerability query, not an installable graph.
    Unbounded declarations use the qualified version and are reported explicitly.
    """
    if mode == "lock":
        return dict(locked), []
    if mode != "minima":
        raise ValueError(f"Unknown security probe mode: {mode}")
    packages = {}
    unbounded = []
    for name, line in requirements_for(policy, profile).items():
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        candidates = [
            Version(bound.version)
            for bound in requirement.specifier
            if bound.operator in {"==", ">="} and "*" not in bound.version
        ]
        if candidates:
            version = str(max(candidates))
        else:
            version = locked[name]
            unbounded.append(name)
        if version not in requirement.specifier:
            raise ValueError(f"Cannot represent declared minimum safely: {line}")
        packages[name] = version
    return packages, sorted(unbounded)


def write_security_probe(
    directory: Path,
    packages: dict[str, str],
    *,
    installed: bool = False,
    distribution_names: dict[str, str] | None = None,
) -> Path:
    """Export installed Pip components or a no-install Poetry minimum probe."""
    if not packages:
        raise ValueError("Cannot scan an empty component inventory")
    directory.mkdir(parents=True, exist_ok=True)
    header = "# Diagnostic component inventory; NOT an installation/release lock.\n"
    if installed:
        path = directory / "requirements.txt"
        lines = []
        for name, version in sorted(packages.items()):
            # Preserve the distribution spelling needed by Snyk's Pip resolver.
            spelling = (distribution_names or {}).get(name, name)
            if canonicalize_name(spelling) != name:
                raise ValueError(f"Distribution name does not match inventory: {name}")
            lines.append(f"{spelling}=={version}\n")
        path.write_text(header + "".join(lines))
        return path
    manifest = (
        header
        + '[tool.poetry]\nname = "venom-local-security-probe"\n'
        + 'version = "0.0.0"\ndescription = "Local vulnerability query"\nauthors = []\n'
        + '[tool.poetry.dependencies]\npython = ">=3.12,<3.13"\n'
        + "".join(
            f"{json.dumps(name)} = {json.dumps(version)}\n"
            for name, version in sorted(packages.items())
        )
    )
    (directory / "pyproject.toml").write_text(manifest)
    lock = header + "".join(
        "[[package]]\n"
        + f"name = {json.dumps(name)}\nversion = {json.dumps(version)}\n"
        + 'description = "Diagnostic component"\noptional = false\n'
        + 'python-versions = "*"\n\n'
        for name, version in sorted(packages.items())
    )
    lock += (
        '[metadata]\nlock-version = "1.1"\npython-versions = ">=3.12,<3.13"\n'
        + f'content-hash = "{hashlib.sha256(manifest.encode()).hexdigest()}"\n'
    )
    path = directory / "poetry.lock"
    path.write_text(lock)
    return path


def scan_security_probe(
    root: Path,
    directory: Path,
    packages: dict[str, str],
    snyk: str,
    org: str,
    *,
    python: str | None = None,
    distribution_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not org.strip():
        raise ValueError("An explicit Snyk organization is required")
    root = root.resolve()
    directory = directory.resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Security probe must remain inside the repository")
    manager = "pip" if python is not None else "poetry"
    lock = write_security_probe(
        directory,
        packages,
        installed=python is not None,
        distribution_names=distribution_names,
    )
    output = directory / "snyk.json"
    # Never let a previous successful report survive a failed invocation.
    output.unlink(missing_ok=True)
    command = [
        snyk,
        "test",
        f"--package-manager={manager}",
        "--print-deps",
        f"--org={org}",
        f"--file={lock.relative_to(root)}",
        f"--policy-path={root / '.snyk'}",
        f"--json-file-output={output}",
    ]
    if python is not None:
        command.append(f"--command={python}")
    try:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, timeout=300, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "ERROR", "complete": False, "error": str(error)}
    (directory / "stdout.log").write_text(result.stdout)
    (directory / "stderr.log").write_text(result.stderr)
    try:
        payload = json.loads(output.read_text())
    except (OSError, ValueError):
        payload = {}
    vulnerabilities = (
        payload.get("vulnerabilities") if isinstance(payload, dict) else None
    )
    # Count equality alone cannot establish which component versions were sent.
    # In particular, Snyk's Poetry parser omits bootstrap tools such as pip.
    versions_by_name: dict[str, set[str]] = {}
    for name, version in re.findall(
        r"(?m)^[ \t│]*[├└]─ ([A-Za-z0-9_.-]+) @ ([^\s]+)[ \t]*$",
        result.stdout,
    ):
        versions_by_name.setdefault(canonicalize_name(name), set()).add(version)
    conflicting_components = {
        name: sorted(versions)
        for name, versions in versions_by_name.items()
        if len(versions) != 1
    }
    observed: dict[str, str] = {
        name: next(iter(versions))
        for name, versions in versions_by_name.items()
        if len(versions) == 1
    }
    component_delta = inventory_delta(packages, observed)
    unexpected_components = sorted(set(observed) - set(packages))
    complete = (
        not component_delta
        and not conflicting_components
        and not unexpected_components
        and isinstance(vulnerabilities, list)
        and all(
            isinstance(v, dict) and isinstance(v.get("id"), str)
            for v in vulnerabilities
        )
        and payload.get("dependencyCount") == len(packages)
        and payload.get("packageManager") == manager
        and payload.get("org") == org
        and not payload.get("error")
        and (
            (result.returncode == 0 and not vulnerabilities)
            or (result.returncode == 1 and bool(vulnerabilities))
        )
    )
    rows = vulnerabilities if isinstance(vulnerabilities, list) else []
    findings = {
        v["id"]: {
            "package": v.get("packageName", v.get("moduleName")),
            "version": v.get("version"),
            "severity": v.get("severity"),
            "fixed_in": v.get("fixedIn", []),
        }
        for v in rows
        if isinstance(v, dict) and isinstance(v.get("id"), str)
    }
    return {
        "status": ("FINDINGS" if findings else "PASS") if complete else "ERROR",
        "complete": complete,
        "exit_code": result.returncode,
        "organization": payload.get("org") if isinstance(payload, dict) else None,
        "component_delta": component_delta,
        "conflicting_components": conflicting_components,
        "unexpected_components": unexpected_components,
        "observed_components": observed,
        "expected_packages": len(packages),
        "scanned_packages": payload.get("dependencyCount")
        if isinstance(payload, dict)
        else None,
        "findings": findings,
    }


def scan_installed_security_inventory(
    root: Path,
    directory: Path,
    packages: dict[str, str],
    snyk: str,
    org: str,
    python: str,
    distribution_names: dict[str, str],
) -> dict[str, Any]:
    """Cover the exact installed inventory without Poetry's bootstrap omissions.

    A flat application query avoids Pip's unresolved transitive name aliases.
    Bootstrap tools omitted by Poetry are queried through the qualified Python.
    No incomplete subquery or unknown component is accepted as full coverage.
    """
    bootstrap_names = {"pip", "setuptools", "distribute", "wheel"}
    parts = {}
    for name, bootstrap in (("application", False), ("bootstrap", True)):
        selected = {
            k: v for k, v in packages.items() if (k in bootstrap_names) == bootstrap
        }
        if bootstrap and "packaging" in packages:
            # wheel depends on packaging. Include this verified version too so
            # the Pip query's transitive closure is fully declared. Application
            # coverage can overlap here; both queries must agree on the version.
            selected["packaging"] = packages["packaging"]
        if selected:
            parts[name] = scan_security_probe(
                root,
                directory / name,
                selected,
                snyk,
                org,
                python=python if bootstrap else None,
                distribution_names=distribution_names if bootstrap else None,
            )
    observed = {
        name: version
        for part in parts.values()
        for name, version in part.get("observed_components", {}).items()
    }
    findings = {
        key: value
        for part in parts.values()
        for key, value in part.get("findings", {}).items()
    }
    delta = inventory_delta(packages, observed)
    complete = (
        bool(parts)
        and not delta
        and set(observed) == set(packages)
        and all(part["complete"] for part in parts.values())
    )
    return {
        "status": ("FINDINGS" if findings else "PASS") if complete else "ERROR",
        "complete": complete,
        "organization": org,
        "expected_packages": len(packages),
        "scanned_packages": len(observed),
        "component_delta": delta,
        "observed_components": observed,
        "findings": findings,
        "parts": parts,
    }


def audit_security_inputs(
    root: Path,
    policy: dict[str, Any],
    profile: str,
    python: str,
    directory: Path,
    snyk: str,
    org: str,
) -> dict[str, Any]:
    """Audit the installed candidate and declared versions before publication."""
    if generate(root, policy, check=True):
        raise ValueError("Generated inputs are stale; run generate first")
    audit_locks(root, policy)
    environment = verify_environment(root, policy, profile, python)
    report: dict[str, Any] = {
        "profile": profile,
        "scope": "LOCAL_INSTALLED_AND_MINIMUM_COMPONENT_QUERIES",
        "not_an_scm_emulator": True,
        "organization": org,
        "environment": environment,
        "status": "ERROR",
        "complete": False,
        "probes": {},
    }
    if environment["status"] != "PASS":
        return report
    locked = read_lock(root / policy["profiles"][profile]["lock"])
    report["input_sha256"] = {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest()
        for path in (
            POLICY,
            policy["profiles"][profile]["input"],
            policy["profiles"][profile]["lock"],
            ".snyk",
        )
    }
    installed_packages = environment["packages"]
    report["probes"]["lock"] = {
        **scan_installed_security_inventory(
            root,
            directory / "lock",
            installed_packages,
            snyk,
            org,
            python,
            environment.get("distribution_names", {}),
        ),
        "packages": installed_packages,
        "qualified_fallback_without_inclusive_minimum": [],
    }
    packages, unbounded = security_probe_packages(policy, profile, locked, "minima")
    report["probes"]["minima"] = {
        **scan_security_probe(root, directory / "minima", packages, snyk, org),
        "packages": packages,
        "qualified_fallback_without_inclusive_minimum": unbounded,
    }
    report["complete"] = all(p["complete"] for p in report["probes"].values())
    if report["complete"]:
        report["status"] = (
            "FINDINGS"
            if any(p["status"] == "FINDINGS" for p in report["probes"].values())
            else "PASS"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("generate", "lock", "verify", "audit-locks", "audit-security"),
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--profile", default="light")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--snyk", default="snyk")
    parser.add_argument("--snyk-org")
    args = parser.parse_args()
    security_directory: Path | None = None
    try:
        if args.action == "audit-security":
            if args.out_dir is None:
                raise ValueError("audit-security requires --out-dir for local evidence")
            candidate = safe_path(args.root, str(args.out_dir))
            if not any(
                candidate.is_relative_to((args.root / name).resolve())
                for name in ("docs_dev", "test-results")
            ):
                raise ValueError(
                    "Security evidence must remain in docs_dev or test-results"
                )
            security_directory = candidate
            security_directory.mkdir(parents=True, exist_ok=True)
            # Invalidate prior qualification before any policy/environment checks.
            (security_directory / "report.json").unlink(missing_ok=True)
            if not args.snyk_org or not args.snyk_org.strip():
                raise ValueError("audit-security requires --snyk-org matching SCM")
        policy = load_policy(args.root)
        require_active_profile(policy, args.profile)
        if args.action == "generate":
            changed = generate(args.root, policy, check=args.check)
            print(
                json.dumps(
                    {
                        "status": "FAIL" if args.check and changed else "PASS",
                        "changed": changed,
                    }
                )
            )
            return int(args.check and bool(changed))
        if args.action == "audit-locks":
            print(json.dumps(audit_locks(args.root, policy), sort_keys=True))
            return 0
        if args.action == "audit-security":
            assert security_directory is not None
            report = audit_security_inputs(
                args.root,
                policy,
                args.profile,
                args.python,
                security_directory,
                args.snyk,
                args.snyk_org,
            )
            (security_directory / "report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            print(
                json.dumps(
                    {
                        "profile": args.profile,
                        "status": report["status"],
                        "complete": report["complete"],
                        "report": str(security_directory / "report.json"),
                    }
                )
            )
            return 2 if not report["complete"] else int(report["status"] != "PASS")
        if args.action == "lock":
            print(lock_profile(args.root, policy, args.profile, args.python))
            return 0
        report = verify_environment(args.root, policy, args.profile, args.python)
        print(json.dumps(report, indent=2, sort_keys=True))
        return int(report["status"] != "PASS")
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f"Dependency profile ERROR: {error}", file=sys.stderr)
        if args.action == "audit-security":
            if security_directory is not None:
                try:
                    (security_directory / "report.json").write_text(
                        json.dumps(
                            {
                                "profile": args.profile,
                                "organization": args.snyk_org,
                                "status": "ERROR",
                                "complete": False,
                                "error": str(error),
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                except OSError as report_error:
                    print(f"Security report ERROR: {report_error}", file=sys.stderr)
            return 2
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
