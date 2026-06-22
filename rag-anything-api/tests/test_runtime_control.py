import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).parents[1] / "runtime_control.py"
APP_PATH = Path(__file__).parents[1] / "app.py"
START_PATH = Path(__file__).parents[1] / "start.py"
TOKEN_HEADER = "X-Test-System-Shutdown-Token"
ALLOWED_HOSTS = {"127.0.0.1", "::1", "testclient"}


@pytest.fixture(scope="module")
def runtime_control():
    if not MODULE_PATH.exists():
        pytest.skip("runtime_control.py does not exist yet")
    spec = importlib.util.spec_from_file_location("rag_api_runtime_control", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_control_module_exists():
    assert MODULE_PATH.exists(), "runtime_control.py must exist"


def make_app(runtime_control, token="secret"):
    app = FastAPI()
    runtime_control.install_shutdown_route(app, token=token, allowed_hosts=ALLOWED_HOSTS)
    return app


def test_no_configured_token_returns_404(runtime_control, monkeypatch):
    monkeypatch.delenv("TEST_SYSTEM_SHUTDOWN_TOKEN", raising=False)
    app = FastAPI()
    runtime_control.install_shutdown_route(app, allowed_hosts=ALLOWED_HOSTS)

    response = TestClient(app).post("/__desktop/shutdown")

    assert response.status_code == 404


@pytest.mark.parametrize("headers", [{}, {TOKEN_HEADER: "wrong"}])
def test_missing_or_wrong_token_returns_403(runtime_control, headers):
    response = TestClient(make_app(runtime_control)).post(
        "/__desktop/shutdown", headers=headers
    )

    assert response.status_code == 403


def test_non_loopback_client_returns_403(runtime_control):
    app = make_app(runtime_control)
    app.state.uvicorn_server = SimpleNamespace(should_exit=False)

    response = TestClient(app, client=("192.0.2.10", 50000)).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "secret"}
    )

    assert response.status_code == 403
    assert app.state.uvicorn_server.should_exit is False


def test_missing_client_returns_403(runtime_control):
    app = make_app(runtime_control)
    route = next(route for route in app.routes if route.path == "/__desktop/shutdown")
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(TOKEN_HEADER.lower().encode(), b"secret")],
            "method": "POST",
            "path": "/__desktop/shutdown",
            "query_string": b"",
            "client": None,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(route.endpoint(request))

    assert exc_info.value.status_code == 403


def test_server_unavailable_returns_503(runtime_control):
    response = TestClient(make_app(runtime_control)).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "secret"}
    )

    assert response.status_code == 503


def test_success_sets_exit_flag_and_returns_json(runtime_control):
    app = make_app(runtime_control)
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server

    response = TestClient(app).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "secret"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert server.should_exit is True


def test_shutdown_route_is_absent_from_openapi(runtime_control):
    schema = make_app(runtime_control).openapi()

    assert "/__desktop/shutdown" not in schema["paths"]


def test_app_installs_route_and_uses_controlled_uvicorn_server():
    source = APP_PATH.read_text(encoding="utf-8")

    assert source.count("install_shutdown_route(app)") == 1
    assert "server = uvicorn.Server(" in source
    assert "app.state.uvicorn_server = server" in source
    assert "server.run()" in source
    assert "uvicorn.run(" not in source


def test_start_script_uses_controlled_uvicorn_server():
    source = START_PATH.read_text(encoding="utf-8")

    assert "server = uvicorn.Server(" in source
    assert "app.state.uvicorn_server = server" in source
    assert "server.run()" in source
    assert "uvicorn.run(" not in source
