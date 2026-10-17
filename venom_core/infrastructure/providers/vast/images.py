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


SHA256_PREFIX = "sha256:"
DIGEST_MISMATCH = "vast.registry_digest_mismatch"
MANIFEST_PATTERN = r"sha256:[a-f0-9]{64}"


def _image_parts(image: str, arch: str) -> tuple[str, str]:
    repo, sep, tag = image.removeprefix("docker.io/").rpartition(":")
    if (
        arch not in {"amd64", "arm64"}
        or not sep
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9._-]*", repo)
        or not re.fullmatch(r"\w[\w.-]{0,127}", tag, flags=re.ASCII)
        or ".." in repo
        or "//" in repo
    ):
        raise VastError("vast.invalid_public_image")
    return repo, tag


def _digest(response: httpx.Response) -> str:
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise VastError("vast.registry_response_limit")
    return SHA256_PREFIX + hashlib.sha256(response.content).hexdigest()


def _manifest_digest(value: str) -> str:
    if not re.fullmatch(MANIFEST_PATTERN, value):
        raise VastError("vast.invalid_image_manifest")
    return value


def _architecture_manifest(doc: dict, arch: str) -> str | None:
    if "manifests" not in doc:
        return None
    matches = [
        item
        for item in doc["manifests"]
        if item.get("platform", {}).get("os") == "linux"
        and item.get("platform", {}).get("architecture") == arch
    ]
    if len(matches) != 1:
        raise VastError("vast.image_architecture_unavailable")
    return _manifest_digest(matches[0].get("digest", ""))


class RegistryReader:
    def __init__(self, client: httpx.Client, repo: str):
        self.client = client
        self.base_url = f"https://registry-1.docker.io/v2/{repo}"
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
        self.headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT}

    def manifest(self, ref: str) -> tuple[dict, str]:
        response = self.client.get(
            f"{self.base_url}/manifests/{ref}", headers=self.headers
        )
        sha = _digest(response)
        if ref.startswith(SHA256_PREFIX) and ref != sha:
            raise VastError(DIGEST_MISMATCH)
        advertised = response.headers.get("Docker-Content-Digest")
        if advertised and sha != advertised:
            raise VastError(DIGEST_MISMATCH)
        return response.json(), sha

    def check_config(self, doc: dict, arch: str) -> None:
        config = _manifest_digest(doc.get("config", {}).get("digest", ""))
        response = self.client.get(
            f"{self.base_url}/blobs/{config}",
            headers=self.headers,
            follow_redirects=True,
        )
        if _digest(response) != config:
            raise VastError(DIGEST_MISMATCH)
        metadata = response.json()
        if metadata.get("os") != "linux" or metadata.get("architecture") != arch:
            raise VastError("vast.image_architecture_unavailable")


def resolve_image(image: str, arch: str, client: httpx.Client) -> dict:
    repo, tag = _image_parts(image, arch)
    try:
        reader = RegistryReader(client, repo)
        doc, sha = reader.manifest(tag)
        reference = _architecture_manifest(doc, arch)
        if reference is not None:
            doc, sha = reader.manifest(reference)
        reader.check_config(doc, arch)
        return {
            "image": f"{repo}@{sha}",
            "source_tag": image,
            "cpu_arch": arch,
            "runtime_compatibility": "requires_remote_inspection",
        }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        raise VastError("vast.registry_failed") from None
