"""Tests for ops-agent container parsing."""

import importlib.util
from pathlib import Path

_ops_agent_path = Path(__file__).resolve().parents[1] / "ops-agent" / "main.py"
_spec = importlib.util.spec_from_file_location("ops_agent_main", _ops_agent_path)
assert _spec and _spec.loader
ops_agent_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops_agent_main)

_dedupe_by_service = ops_agent_main._dedupe_by_service
_guess_service_name = ops_agent_main._guess_service_name
_parse_container_rows = ops_agent_main._parse_container_rows


def test_guess_service_name_standard_compose():
    assert _guess_service_name("archivedb-api-1") == "api"
    assert _guess_service_name("archivedb-ops-agent-1") == "ops-agent"


def test_parse_container_rows_uses_compose_service_label():
    output = "archivedb-api-1\tUp 2 hours (healthy)\trunning\tapi\n"
    rows = _parse_container_rows(output)
    assert len(rows) == 1
    assert rows[0]["name"] == "api"
    assert rows[0]["status"] == "running"
    assert rows[0]["health"] == "healthy"


def test_dedupe_prefers_running_instance():
    items = [
        {"name": "api", "full_name": "archivedb-api-1", "status": "exited", "health": None, "detail": ""},
        {"name": "api", "full_name": "archivedb-api-2", "status": "running", "health": None, "detail": ""},
    ]
    result = _dedupe_by_service(items)
    assert len(result) == 1
    assert result[0]["full_name"] == "archivedb-api-2"
