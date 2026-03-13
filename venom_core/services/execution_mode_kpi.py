from __future__ import annotations


def build_execution_mode_kpi_payload(
    metrics: dict,
    gui_fallback_alert_threshold: float = 20.0,
) -> dict[str, object]:
    """Build dashboard payload for execution-mode planner KPI.

    Contract is intentionally explicit for operational dashboards and alerting.
    """
    routing = metrics.get("routing") or {}
    execution_mode = routing.get("execution_mode") or {}
    share_rate = execution_mode.get("share_rate") or {}
    counts = execution_mode.get("counts") or {}

    api_skill_share = float(share_rate.get("api_skill") or 0.0)
    browser_share = float(share_rate.get("browser_automation") or 0.0)
    gui_share = float(share_rate.get("gui_fallback") or 0.0)

    alert_active = gui_share >= gui_fallback_alert_threshold

    return {
        "status": "ok",
        "kpi": {
            "total": int(execution_mode.get("total") or 0),
            "counts": {
                "api_skill": int(counts.get("api_skill") or 0),
                "browser_automation": int(counts.get("browser_automation") or 0),
                "gui_fallback": int(counts.get("gui_fallback") or 0),
            },
            "share_rate": {
                "api_skill": api_skill_share,
                "browser_automation": browser_share,
                "gui_fallback": gui_share,
            },
            "success_rate": float(execution_mode.get("success_rate") or 0.0),
            "manual_intervention_rate": float(
                execution_mode.get("manual_intervention_rate") or 0.0
            ),
            "retry_loop_rate": float(execution_mode.get("retry_loop_rate") or 0.0),
        },
        "alerts": {
            "gui_fallback_overuse": {
                "active": alert_active,
                "threshold": gui_fallback_alert_threshold,
                "current": gui_share,
                "severity": "high" if alert_active else "none",
            }
        },
    }
