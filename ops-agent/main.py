"""Read-only Docker container status and logs for archiveDB."""

from __future__ import annotations

import os
import subprocess

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN = os.getenv("OPS_AGENT_TOKEN", "").strip()
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT_NAME", "").strip()

app = FastAPI(title="archiveDB ops-agent")
security = HTTPBearer(auto_error=False)


def _auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if not TOKEN:
        return
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _resolve_compose_project() -> str | None:
    if COMPOSE_PROJECT:
        return COMPOSE_PROJECT
    hostname = os.getenv("HOSTNAME", "").strip()
    if not hostname:
        return None
    try:
        project = _docker(
            "inspect",
            hostname,
            "--format",
            '{{index .Config.Labels "com.docker.compose.project"}}',
        ).strip()
        return project or None
    except Exception:
        return None


def _guess_service_name(full_name: str) -> str:
    """Fallback when compose service label is missing."""
    if "-" not in full_name:
        return full_name
    parts = full_name.split("-")
    if len(parts) >= 3 and parts[-1].isdigit():
        return "-".join(parts[1:-1]) if len(parts) > 3 else parts[-2]
    return parts[-1]


def _parse_container_rows(output: str) -> list[dict]:
    items: list[dict] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        full_name, status, state = parts[0], parts[1], parts[2]
        service = parts[3].strip() if len(parts) > 3 and parts[3].strip() else _guess_service_name(full_name)
        health = "healthy" if "(healthy)" in status else ("unhealthy" if "(unhealthy)" in status else None)
        items.append(
            {
                "name": service,
                "full_name": full_name,
                "status": state,
                "health": health,
                "detail": status,
            }
        )
    return items


def _dedupe_by_service(items: list[dict]) -> list[dict]:
    """Prefer a running container when several instances share the same compose service."""
    by_service: dict[str, dict] = {}
    for item in items:
        service = item["name"]
        existing = by_service.get(service)
        if existing is None:
            by_service[service] = item
            continue
        if item["status"] == "running" and existing["status"] != "running":
            by_service[service] = item
    return sorted(by_service.values(), key=lambda row: row["name"])


def fetch_containers() -> list[dict]:
    project = _resolve_compose_project()
    args = [
        "ps",
        "-a",
        "--format",
        '{{.Names}}\t{{.Status}}\t{{.State}}\t{{.Label "com.docker.compose.service"}}',
    ]
    if project:
        args[2:2] = ["--filter", f"label=com.docker.compose.project={project}"]
    else:
        args[2:2] = ["--filter", "label=com.docker.compose.project"]

    try:
        output = _docker(*args)
    except Exception:
        return []
    return _dedupe_by_service(_parse_container_rows(output))


@app.get("/containers")
def list_containers(_: None = Depends(_auth)) -> list[dict]:
    return fetch_containers()


@app.get("/containers/{name}/logs")
def container_logs(
    name: str,
    tail: int = Query(200, ge=10, le=2000),
    _: None = Depends(_auth),
) -> dict:
    try:
        containers = fetch_containers()
        full_name = next((c["full_name"] for c in containers if c["name"] == name), None)
        if not full_name:
            raise HTTPException(status_code=404, detail="Container not found")
        logs = _docker("logs", "--tail", str(tail), full_name)
        return {"name": name, "logs": logs}
    except HTTPException:
        raise
    except Exception as exc:
        return {"name": name, "logs": f"Error: {exc}"}
