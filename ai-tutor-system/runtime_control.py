import hmac
import os
from collections.abc import Collection

from fastapi import FastAPI, HTTPException, Request


SHUTDOWN_PATH = "/__desktop/shutdown"
TOKEN_HEADER = "X-Test-System-Shutdown-Token"
DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1"})


def install_shutdown_route(
    app: FastAPI,
    token: str | None = None,
    allowed_hosts: Collection[str] | None = None,
) -> None:
    expected_token = token if token is not None else os.getenv("TEST_SYSTEM_SHUTDOWN_TOKEN")
    permitted_hosts = frozenset(allowed_hosts) if allowed_hosts is not None else DEFAULT_ALLOWED_HOSTS

    @app.post(SHUTDOWN_PATH, include_in_schema=False)
    async def shutdown(request: Request) -> dict[str, str]:
        if expected_token is None:
            raise HTTPException(status_code=404, detail="Not Found")
        if request.client is None or request.client.host not in permitted_hosts:
            raise HTTPException(status_code=403, detail="Forbidden")

        supplied_token = request.headers.get(TOKEN_HEADER)
        if supplied_token is None or not hmac.compare_digest(supplied_token, expected_token):
            raise HTTPException(status_code=403, detail="Forbidden")

        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(status_code=503, detail="Service Unavailable")

        server.should_exit = True
        return {"status": "shutting_down"}
