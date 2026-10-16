"""Resolve public Docker Hub tags to immutable Linux architecture manifests."""

import hashlib
import re

import httpx

from venom_core.infrastructure.providers.vast.client import VastError

ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


def resolve_image(image: str, arch: str, client: httpx.Client) -> dict:
    value = image.removeprefix("docker.io/")
    repo, sep, tag = value.rpartition(":")
    if (
        arch not in {"amd64", "arm64"}
        or not sep
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9._-]*", repo)
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag)
        or ".." in repo
        or "//" in repo
    ):
        raise VastError("vast.invalid_public_image")
    try:
        auth = client.get(
            "https://auth.docker.io/token",
            params={
                "service": "registry.docker.io",
                "scope": f"repository:{repo}:pull",
            },
        )
        auth.raise_for_status()
        token = auth.json().get("token")
        if not isinstance(token, str) or not token:
            raise VastError("vast.registry_auth_failed")
        headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT}

        def manifest(ref: str) -> tuple[dict, str]:
            response = client.get(
                f"https://registry-1.docker.io/v2/{repo}/manifests/{ref}",
                headers=headers,
            )
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise VastError("vast.registry_response_limit")
            sha = "sha256:" + hashlib.sha256(response.content).hexdigest()
            if ref.startswith("sha256:") and ref != sha:
                raise VastError("vast.registry_digest_mismatch")
            advertised = response.headers.get("Docker-Content-Digest")
            if advertised and sha != advertised:
                raise VastError("vast.registry_digest_mismatch")
            return response.json(), sha

        doc, sha = manifest(tag)
        if "manifests" in doc:
            matches = [
                item
                for item in doc["manifests"]
                if item.get("platform", {}).get("os") == "linux"
                and item.get("platform", {}).get("architecture") == arch
            ]
            if len(matches) != 1:
                raise VastError("vast.image_architecture_unavailable")
            ref = matches[0].get("digest", "")
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", ref):
                raise VastError("vast.invalid_image_manifest")
            doc, sha = manifest(ref)
        config = doc.get("config", {}).get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", config):
            raise VastError("vast.invalid_image_manifest")
        response = client.get(
            f"https://registry-1.docker.io/v2/{repo}/blobs/{config}",
            headers=headers,
            follow_redirects=True,
        )
        response.raise_for_status()
        if (
            len(response.content) > 2_000_000
            or "sha256:" + hashlib.sha256(response.content).hexdigest() != config
        ):
            raise VastError("vast.registry_digest_mismatch")
        metadata = response.json()
        if metadata.get("os") != "linux" or metadata.get("architecture") != arch:
            raise VastError("vast.image_architecture_unavailable")
        return {
            "image": f"{repo}@{sha}",
            "source_tag": image,
            "cpu_arch": arch,
            "runtime_compatibility": "requires_remote_inspection",
        }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        raise VastError("vast.registry_failed") from None
