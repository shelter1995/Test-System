import asyncio
import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).parents[1] / "runtime_control.py"
BACKEND_PATH = Path(__file__).parents[1] / "tutor_backend.py"
TOKEN_HEADER = "X-Test-System-Shutdown-Token"
ALLOWED_HOSTS = {"127.0.0.1", "::1", "testclient"}


@pytest.fixture(scope="module")
def runtime_control():
    if not MODULE_PATH.exists():
        pytest.skip("runtime_control.py does not exist yet")
    spec = importlib.util.spec_from_file_location("ai_tutor_runtime_control", MODULE_PATH)
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


def make_fake_uvicorn(monkeypatch):
    records = SimpleNamespace(configs=[], servers=[])
    module = ModuleType("uvicorn")

    class FakeConfig:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs
            self.reload = kwargs.get("reload", False)
            records.configs.append(self)

    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.should_exit = False
            self.ran = False
            records.servers.append(self)

        def run(self):
            assert self.config.app.state.uvicorn_server is self
            self.ran = True

    module.Config = FakeConfig
    module.Server = FakeServer
    monkeypatch.setitem(sys.modules, "uvicorn", module)
    return records


def execute_main_block(path, namespace):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    main_block = next(
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )
    code = compile(ast.Module(body=main_block.body, type_ignores=[]), str(path), "exec")
    exec(code, namespace)


def test_no_configured_token_returns_404(runtime_control, monkeypatch):
    monkeypatch.delenv("TEST_SYSTEM_SHUTDOWN_TOKEN", raising=False)
    app = FastAPI()
    runtime_control.install_shutdown_route(app, allowed_hosts=ALLOWED_HOSTS)

    response = TestClient(app).post("/__desktop/shutdown")

    assert response.status_code == 404


@pytest.mark.parametrize("token_source", ["explicit", "environment"])
@pytest.mark.parametrize("token_value", ["", " ", "\t\r\n"])
def test_blank_token_is_treated_as_unconfigured(
    runtime_control, monkeypatch, token_source, token_value
):
    app = FastAPI()
    if token_source == "explicit":
        monkeypatch.setenv("TEST_SYSTEM_SHUTDOWN_TOKEN", "fallback-secret")
        runtime_control.install_shutdown_route(
            app, token=token_value, allowed_hosts=ALLOWED_HOSTS
        )
    else:
        monkeypatch.setenv("TEST_SYSTEM_SHUTDOWN_TOKEN", token_value)
        runtime_control.install_shutdown_route(app, allowed_hosts=ALLOWED_HOSTS)

    response = TestClient(app).post("/__desktop/shutdown")

    assert response.status_code == 404


def test_environment_token_authorizes_shutdown(runtime_control, monkeypatch):
    monkeypatch.setenv("TEST_SYSTEM_SHUTDOWN_TOKEN", "env-secret")
    app = FastAPI()
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server
    runtime_control.install_shutdown_route(app, allowed_hosts=ALLOWED_HOSTS)

    response = TestClient(app).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "env-secret"}
    )

    assert response.status_code == 200
    assert server.should_exit is True


def test_explicit_token_takes_precedence_over_environment(runtime_control, monkeypatch):
    monkeypatch.setenv("TEST_SYSTEM_SHUTDOWN_TOKEN", "env-secret")
    app = make_app(runtime_control, token="explicit-secret")
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server
    client = TestClient(app)

    env_response = client.post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "env-secret"}
    )
    explicit_response = client.post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "explicit-secret"}
    )

    assert env_response.status_code == 403
    assert explicit_response.status_code == 200
    assert server.should_exit is True


def test_default_allowed_hosts_excludes_testclient(runtime_control):
    app = FastAPI()
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server
    runtime_control.install_shutdown_route(app, token="secret")

    response = TestClient(app).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "secret"}
    )

    assert response.status_code == 403
    assert server.should_exit is False


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_default_allowed_hosts_accept_loopback(runtime_control, host):
    app = FastAPI()
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server
    runtime_control.install_shutdown_route(app, token="secret")

    response = TestClient(app, client=(host, 50000)).post(
        "/__desktop/shutdown", headers={TOKEN_HEADER: "secret"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert server.should_exit is True


@pytest.mark.parametrize("headers", [{}, {TOKEN_HEADER: "wrong"}])
def test_missing_or_wrong_token_returns_403(runtime_control, headers):
    response = TestClient(make_app(runtime_control)).post(
        "/__desktop/shutdown", headers=headers
    )

    assert response.status_code == 403


def test_non_ascii_header_returns_403(runtime_control):
    app = FastAPI()
    server = SimpleNamespace(should_exit=False)
    app.state.uvicorn_server = server
    runtime_control.install_shutdown_route(app, token="secret")
    route = next(route for route in app.routes if route.path == "/__desktop/shutdown")
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(TOKEN_HEADER.lower().encode(), b"\xff")],
            "method": "POST",
            "path": "/__desktop/shutdown",
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(route.endpoint(request))

    assert exc_info.value.status_code == 403
    assert server.should_exit is False


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


def test_backend_main_uses_configured_controlled_uvicorn_server(monkeypatch):
    source = BACKEND_PATH.read_text(encoding="utf-8")
    assert source.count("install_shutdown_route(app)") == 1
    records = make_fake_uvicorn(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace())
    config = SimpleNamespace(
        TUTOR_SERVICE_HOST="configured-tutor-host",
        TUTOR_SERVICE_PORT=18002,
        RAG_SERVICE_URL="http://configured-rag",
    )

    execute_main_block(
        BACKEND_PATH,
        {
            "__name__": "__main__",
            "app": app,
            "config": config,
            "check_port_available": lambda port: True,
        },
    )

    assert len(records.configs) == 1
    assert records.configs[0].app is app
    assert records.configs[0].kwargs == {
        "host": "configured-tutor-host",
        "port": 18002,
        "log_level": "info",
    }
    assert records.configs[0].reload is False
    assert len(records.servers) == 1
    assert app.state.uvicorn_server is records.servers[0]
    assert records.servers[0].ran is True
