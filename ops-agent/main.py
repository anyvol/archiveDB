"""Read-only Docker container status and logs for archiveDB."""

from __future__ import annotations

import os
import subprocess

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALLOWED_CONTAINERS = {"db", "api", "proxy", "backup", "ops-agent", "ocr"}
TOKEN = os.getenv("OPS_AGENT_TOKEN", "").strip()

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


@app.get("/containers")
def list_containers(_: None = Depends(_auth)) -> list[dict]:
    try:
        output = _docker(
            "ps",
            "-a",
            "--filter", "label=com.docker.compose.project",
            "--format", "{{.Names}}\t{{.Status}}\t{{.State}}",
        )
    except Exception:
        return []
    items: list[dict] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, status, state = parts[0], parts[1], parts[2]
        short = name.split("-")[-1] if "-" in name else name
        if short not in ALLOWED_CONTAINERS and name not in ALLOWED_CONTAINERS:
            continue
        health = "healthy" if "(healthy)" in status else ("unhealthy" if "(unhealthy)" in status else None)
        items.append({"name": short, "full_name": name, "status": state, "health": health, "detail": status})
    return items


@app.get("/containers/{name}/logs")
def container_logs(
    name: str,
    tail: int = Query(200, ge=10, le=2000),
    _: None = Depends(_auth),
) -> dict:
    if name not in ALLOWED_CONTAINERS:
        raise HTTPException(status_code=404, detail="Container not allowed")
    try:
        containers = list_containers()
        full_name = next((c["full_name"] for c in containers if c["name"] == name), None)
        if not full_name:
            raise HTTPException(status_code=404, detail="Container not found")
        logs = _docker("logs", "--tail", str(tail), full_name)
        return {"name": name, "logs": logs}
    except HTTPException:
        raise
    except Exception as exc:
        return {"name": name, "logs": f"Error: {exc}"}
