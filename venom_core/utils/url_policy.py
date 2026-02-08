"""Central policy for resolving HTTP scheme across environments."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse, urlunparse

from venom_core.config import SETTINGS

VALID_URL_SCHEME_POLICIES = {"auto", "force_http", "force_https"}
PROD_ENVS = {"production", "prod", "staging", "stage"}


def normalize_url_scheme_policy(policy: str | None = None) -> str:
    value = (policy or getattr(SETTINGS, "URL_SCHEME_POLICY", "auto") or "auto").strip()
    lowered = value.lower()
    if lowered in VALID_URL_SCHEME_POLICIES:
        return lowered
    return "auto"


def normalize_env(env: str | None = None) -> str:
    value = (env or getattr(SETTINGS, "ENV", "development") or "development").strip()
    return value.lower()


def is_local_or_private_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "0.0.0.0", "::1"}:
        return True
    if host.endswith(".localhost"):
        return True
    if host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def resolve_http_scheme(
    hostname: str, env: str | None = None, policy: str | None = None
) -> str:
    active_policy = normalize_url_scheme_policy(policy)
    if active_policy == "force_https":
        return "https"
    if active_policy == "force_http":
        return "http"

    if is_local_or_private_host(hostname):
        return "http"

    return "https" if normalize_env(env) in PROD_ENVS else "http"


def apply_http_policy_to_url(
    url: str, env: str | None = None, policy: str | None = None
) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return url

    scheme = resolve_http_scheme(parsed.hostname, env=env, policy=policy)
    return urlunparse(parsed._replace(scheme=scheme))


def build_http_url(
    hostname: str,
    port: int | None = None,
    path: str = "",
    env: str | None = None,
    policy: str | None = None,
) -> str:
    scheme = resolve_http_scheme(hostname, env=env, policy=policy)
    netloc = f"{hostname}:{port}" if port else hostname
    normalized_path = path if not path or path.startswith("/") else f"/{path}"
    return urlunparse((scheme, netloc, normalized_path, "", "", ""))
