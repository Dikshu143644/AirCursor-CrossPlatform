"""Authenticated local HTTP/WebSocket remote gateway.

Install with: pip install '.[remote]'. The host app supplies an OS input adapter.
"""
import asyncio
import hmac
import json
import secrets
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from aiohttp import web, WSMsgType
except ImportError as exc:
    raise RuntimeError("Install aircursor_core[remote] to use the remote gateway") from exc

_STATIC = Path(__file__).with_name("static")
_ALLOWED = {"move", "click", "scroll", "button", "ping"}

class RemoteGateway:
    def __init__(self, on_command: Callable[[dict[str, Any]], None],
                 token: Optional[str] = None, max_clients: int = 4) -> None:
        self.on_command = on_command
        self.token = token or secrets.token_urlsafe(24)
        self.max_clients = max_clients
        self._clients: set[web.WebSocketResponse] = set()
        self._app = web.Application(client_max_size=16 * 1024)
        self._app.router.add_get("/", self._index)
        self._app.router.add_get("/remote.js", self._script)
        self._app.router.add_get("/api/status", self._status)
        self._app.router.add_get("/ws", self._websocket)

    @property
    def app(self) -> web.Application:
        return self._app

    async def _index(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(_STATIC / "remote.html")

    async def _script(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(_STATIC / "remote.js")

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response({"name": "AirCursor", "protocol": 1, "clients": len(self._clients)})

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        if len(self._clients) >= self.max_clients:
            raise web.HTTPServiceUnavailable(text="Remote client limit reached")
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4096)
        await ws.prepare(request)
        try:
            auth = await asyncio.wait_for(ws.receive(), timeout=5)
            if auth.type != WSMsgType.TEXT:
                await ws.close(code=4001, message=b"authentication required")
                return ws
            try:
                payload = json.loads(auth.data)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            supplied = payload.get("token", "") if isinstance(payload, dict) else ""
            if not isinstance(payload, dict) or payload.get("type") != "auth" or not isinstance(supplied, str) or not hmac.compare_digest(supplied, self.token):
                await ws.close(code=4003, message=b"unauthorized")
                return ws
            self._clients.add(ws)
            await ws.send_json({"type": "ready", "protocol": 1})
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    try:
                        command = json.loads(message.data)
                        self._validate(command)
                        self.on_command(command)
                        await ws.send_json({"type": "ack", "id": command.get("id")})
                    except (ValueError, TypeError, json.JSONDecodeError) as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})
                elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        except asyncio.TimeoutError:
            await ws.close(code=4001, message=b"authentication timeout")
        finally:
            self._clients.discard(ws)
        return ws

    @staticmethod
    def _validate(command: Any) -> None:
        if not isinstance(command, dict) or command.get("type") not in _ALLOWED:
            raise ValueError("unsupported command")
        kind = command["type"]
        if kind == "move":
            for key in ("x", "y"):
                value = command.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    raise ValueError(key + " must be normalized between 0 and 1")
        elif kind == "scroll":
            value = command.get("delta", 0)
            if isinstance(value, bool) or not isinstance(value, int) or not -10 <= value <= 10:
                raise ValueError("scroll delta must be an integer from -10 to 10")
        elif kind in ("click", "button"):
            if command.get("button", "left") not in ("left", "right", "middle"):
                raise ValueError("invalid mouse button")

    async def close(self) -> None:
        for client in tuple(self._clients):
            await client.close(code=1001, message=b"server shutting down")

async def serve(host: str = "0.0.0.0", port: int = 8765,
                on_command: Optional[Callable[[dict[str, Any]], None]] = None,
                token: Optional[str] = None):
    """Start the gateway and return (runner, gateway) for controlled shutdown."""
    gateway = RemoteGateway(on_command or (lambda command: None), token)
    runner = web.AppRunner(gateway.app)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner, gateway
