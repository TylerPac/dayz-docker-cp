"""Prometheus metrics: server state, players and resources at /metrics.

Written out by hand in the text exposition format rather than through
prometheus_client: a dozen gauges do not justify a dependency, and every value
already exists in the services the dashboard reads.

Off unless METRICS_TOKEN is set, and then only answered with that token as a
bearer token - the same thing a Prometheus scrape config or a ServiceMonitor's
bearerTokenSecret sends. The panel's login does not apply: a scraper has no
session, and the token is the narrower key.
"""

from __future__ import annotations

import hmac

from flask import Flask, Response, abort, request

from .extensions import limiter
from .services.server import ServerState

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def register(app: Flask, version: str) -> None:
    settings = app.config["SETTINGS"]

    @app.get("/metrics")
    @limiter.exempt
    def metrics():
        # 404 rather than 401 while disabled: the route should look absent.
        if not settings.metrics_token:
            abort(404)
        if not _authorized(settings.metrics_token):
            return Response("unauthorized\n", 401, {"WWW-Authenticate": "Bearer"})
        return Response(render(app, version), content_type=CONTENT_TYPE)


def _authorized(token: str) -> bool:
    scheme, _, presented = request.headers.get("Authorization", "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(presented.strip(), token)


def render(app: Flask, version: str) -> str:
    status = app.extensions["server"].status()
    lines: list[str] = []

    def gauge(name: str, help_text: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for labels, value in samples:
            lines.append(f"{name}{labels} {value:g}")

    gauge("dayz_panel_info", "Control panel version.", [(f'{{version="{version}"}}', 1)])
    gauge(
        "dayz_server_state",
        "Server process state; exactly one state is 1.",
        [(f'{{state="{s.value}"}}', int(status["state"] == s.value)) for s in ServerState],
    )
    gauge(
        "dayz_server_up",
        "1 once the mission is loaded and players can join.",
        [("", int(status["state"] == ServerState.RUNNING.value))],
    )
    gauge("dayz_server_uptime_seconds", "Seconds since the server process started.",
          [("", status["uptime_seconds"])])
    gauge("dayz_server_restart_attempts", "Automatic restarts after recent crashes.",
          [("", status["restart_attempts"])])

    if status["rss_mb"] is not None:
        gauge("dayz_server_memory_rss_bytes", "Resident memory of the server process.",
              [("", status["rss_mb"] * 1024 * 1024)])
    if status["cpu_percent"] is not None:
        gauge("dayz_server_cpu_percent", "CPU of the server process, 100 = one core.",
              [("", status["cpu_percent"])])

    # Only a running server answers the Steam query; asking a stopped one costs
    # a one second timeout on every scrape for a number that is 0 anyway.
    if status["state"] == ServerState.RUNNING.value:
        info = app.extensions["query"].info()
        gauge("dayz_server_query_reachable", "1 if the Steam query port answered.",
              [("", int(info.reachable))])
        if info.reachable:
            gauge("dayz_server_players", "Players online (Steam A2S).", [("", info.players)])
            gauge("dayz_server_max_players", "Player slots (Steam A2S).",
                  [("", info.max_players)])

    return "\n".join(lines) + "\n"
