from urllib.parse import urlunsplit

from venom_core.utils.url_policy import (
    apply_http_policy_to_url,
    build_http_url,
    resolve_http_scheme,
)


def test_auto_policy_keeps_localhost_http_even_in_production() -> None:
    assert resolve_http_scheme("localhost", env="production", policy="auto") == "http"


def test_auto_policy_uses_https_for_external_in_production() -> None:
    assert (
        resolve_http_scheme("api.example.com", env="production", policy="auto")
        == "https"
    )


def test_force_http_overrides_external_host() -> None:
    assert (
        resolve_http_scheme("api.example.com", env="production", policy="force_http")
        == "http"
    )


def test_apply_http_policy_to_url_rewrites_scheme() -> None:
    insecure_url = urlunsplit(("http", "api.example.com", "/v1/models", "", ""))
    rewritten = apply_http_policy_to_url(
        insecure_url, env="production", policy="force_https"
    )
    assert rewritten == "https://api.example.com/v1/models"


def test_build_http_url_uses_policy() -> None:
    assert (
        build_http_url(
            "api.example.com", 443, "/healthz", env="production", policy="auto"
        )
        == "https://api.example.com:443/healthz"
    )
