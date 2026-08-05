from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha1
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import logging
import mimetypes
from pathlib import Path
import socket
import struct
import threading
import time
from typing import Any, Protocol
from urllib.parse import urlparse

from .constants import Terrain

LOGGER = logging.getLogger("flobot.monitor")
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PLAYER_COLORS = ("#4f9cff", "#ff5d73", "#38d39f", "#f4b84a")


class SessionController(Protocol):
    def start_session(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...
    def stop_session(self) -> tuple[int, dict[str, Any]]: ...
    def get_status(self) -> dict[str, Any]: ...


def _websocket_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """Encode one unmasked server-to-client WebSocket frame."""
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(length)
    elif length <= 0xFFFF:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    return bytes(header) + payload


def _read_exact(connection: socket.socket, length: int) -> bytes | None:
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def _read_websocket_frame(connection: socket.socket) -> tuple[int, bytes] | None:
    header = _read_exact(connection, 2)
    if header is None:
        return None
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        extended = _read_exact(connection, 2)
        if extended is None:
            return None
        length = struct.unpack("!H", extended)[0]
    elif length == 127:
        extended = _read_exact(connection, 8)
        if extended is None:
            return None
        length = struct.unpack("!Q", extended)[0]
    mask = _read_exact(connection, 4) if masked else None
    if masked and mask is None:
        return None
    payload = _read_exact(connection, length)
    if payload is None:
        return None
    if mask is not None:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, payload


@dataclass
class _WebSocketPeer:
    connection: socket.socket
    lock: threading.Lock = field(default_factory=threading.Lock)

    def send(self, payload: bytes, opcode: int = 0x1) -> None:
        frame = _websocket_frame(payload, opcode)
        with self.lock:
            self.connection.sendall(frame)


class _MonitorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BattleMonitor:
    """Publish the current battle over local HTTP polling and WebSocket APIs."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        static_dir: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.static_dir = static_dir.resolve() if static_dir else None
        self.session_controller: SessionController | None = None
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_json: bytes | None = None
        self._snapshot_lock = threading.Lock()
        self._peers: dict[socket.socket, _WebSocketPeer] = {}
        self._peers_lock = threading.Lock()
        self._recent_moves: deque[dict[str, Any]] = deque(maxlen=5)
        self._game_id = "waiting-for-game"
        self._player_name = "Flobot"
        self._started_at = time.monotonic()
        self._server: _MonitorHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self) -> None:
        if self._server is not None:
            return
        monitor = self

        class RequestHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                LOGGER.debug("[http] %s", format % args)

            def _cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Cache-Control", "no-store")

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self._cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    return {}
                body = self.rfile.read(length)
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                return payload

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                path = urlparse(self.path).path.rstrip("/") or "/"
                if path == "/api/snapshot":
                    snapshot = monitor.get_snapshot()
                    if snapshot is None:
                        self.send_response(204)
                        self._cors_headers()
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                    else:
                        self._send_json(200, snapshot)
                    return
                if path == "/api/health":
                    snapshot = monitor.get_snapshot()
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "hasSnapshot": snapshot is not None,
                            "turn": snapshot.get("turn") if snapshot else None,
                            "websocketClients": monitor.websocket_client_count,
                            "session": monitor.session_controller.get_status()
                            if monitor.session_controller
                            else None,
                        },
                    )
                    return
                if path == "/api/session":
                    if monitor.session_controller is None:
                        self._send_json(404, {"error": "session_control_unavailable"})
                    else:
                        self._send_json(200, monitor.session_controller.get_status())
                    return
                if path == "/ws":
                    self._handle_websocket()
                    return
                if self._serve_static(path):
                    return
                self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                path = urlparse(self.path).path.rstrip("/") or "/"
                if monitor.session_controller is None:
                    self._send_json(404, {"error": "session_control_unavailable"})
                    return
                try:
                    if path == "/api/session/start":
                        status, response = monitor.session_controller.start_session(self._read_json())
                    elif path == "/api/session/stop":
                        status, response = monitor.session_controller.stop_session()
                    else:
                        self._send_json(404, {"error": "not_found"})
                        return
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self._send_json(400, {"error": "invalid_json"})
                    return
                self._send_json(status, response)

            def _serve_static(self, path: str) -> bool:
                root = monitor.static_dir
                if root is None or not root.is_dir():
                    return False
                relative = "index.html" if path == "/" else path.lstrip("/")
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root):
                    return False
                if not candidate.is_file():
                    candidate = root / "index.html"
                if not candidate.is_file():
                    return False
                content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type in {
                    "application/javascript",
                    "application/json",
                }:
                    content_type += "; charset=utf-8"
                self._send_bytes(200, candidate.read_bytes(), content_type)
                return True

            def _handle_websocket(self) -> None:
                websocket_key = self.headers.get("Sec-WebSocket-Key")
                if self.headers.get("Upgrade", "").lower() != "websocket" or not websocket_key:
                    self._send_json(400, {"error": "websocket_upgrade_required"})
                    return
                accept = base64.b64encode(
                    sha1((websocket_key + WEBSOCKET_GUID).encode("ascii")).digest()
                ).decode("ascii")
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.flush()

                peer = monitor._add_peer(self.connection)
                self.close_connection = True
                try:
                    initial = monitor.get_websocket_message()
                    if initial is not None:
                        peer.send(initial)
                    self.connection.settimeout(0.75)
                    while not monitor._stopping.is_set():
                        try:
                            frame = _read_websocket_frame(self.connection)
                        except TimeoutError:
                            continue
                        if frame is None:
                            break
                        opcode, payload = frame
                        if opcode == 0x8:
                            peer.send(payload, opcode=0x8)
                            break
                        if opcode == 0x9:
                            peer.send(payload, opcode=0xA)
                except (ConnectionError, OSError):
                    pass
                finally:
                    monitor._remove_peer(self.connection)

        self._stopping.clear()
        self._server = _MonitorHTTPServer((self.host, self.port), RequestHandler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="flobot-monitor",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("[monitor] listening host=%s port=%d", self.host, self.port)

    def set_session_controller(self, controller: SessionController) -> None:
        self.session_controller = controller

    def stop(self) -> None:
        self._stopping.set()
        with self._peers_lock:
            peers = list(self._peers.values())
            self._peers.clear()
        for peer in peers:
            try:
                peer.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                peer.connection.close()
            except OSError:
                pass
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def begin_game(self, game_id: str, player_name: str) -> None:
        self._game_id = game_id or "live-game"
        self._player_name = player_name
        self._started_at = time.monotonic()
        self._recent_moves.clear()
        with self._snapshot_lock:
            self._snapshot = None
            self._snapshot_json = None

    def publish_turn(
        self,
        state: Any,
        observation: Any,
        action: tuple[int, int, int] | None,
    ) -> dict[str, Any]:
        last_move: dict[str, Any] | None = None
        if action is not None:
            source, destination, _split = action
            last_move = {
                "id": f"{state.turn}-0-{source}-{destination}",
                "turn": int(state.turn),
                "playerId": 0,
                "from": int(source),
                "to": int(destination),
                "description": "机器人下达移动",
            }
            self._recent_moves.appendleft(last_move)

        tiles = []
        cities = set(state.cities)
        generals = {index for index in state.generals if index is not None and index >= 0}
        for index, terrain_value in enumerate(state.terrain):
            terrain = int(terrain_value)
            discovered = bool(state.discovered_tiles[index])
            if terrain == Terrain.FOG_OBSTACLE:
                kind = "fog-obstacle"
            elif terrain == Terrain.FOG or not discovered:
                kind = "fog"
            elif terrain == Terrain.MOUNTAIN:
                kind = "mountain"
            elif index in generals:
                kind = "general"
            elif index in cities:
                kind = "city"
            else:
                kind = "plain"
            tiles.append(
                {
                    "index": index,
                    "row": index // state.width,
                    "column": index % state.width,
                    "kind": kind,
                    "ownerId": terrain if terrain >= 0 else None,
                    "army": int(state.armies[index]),
                    "discovered": discovered,
                }
            )

        players = [
            {
                "id": 0,
                "name": self._player_name,
                "color": PLAYER_COLORS[0],
                "army": int(observation.owned_army_count),
                "land": int(observation.owned_land_count),
                "alive": int(observation.owned_land_count) > 0,
            },
            {
                "id": 1,
                "name": "对手",
                "color": PLAYER_COLORS[1],
                "army": int(observation.opponent_army_count),
                "land": int(observation.opponent_land_count),
                "alive": int(observation.opponent_land_count) > 0,
            },
        ]
        snapshot = {
            "gameId": self._game_id,
            "turn": int(state.turn),
            "width": int(state.width),
            "height": int(state.height),
            "status": "playing",
            "elapsedSeconds": max(0, int(time.monotonic() - self._started_at)),
            "observerPlayerId": 0,
            "players": players,
            "tiles": tiles,
            "lastMove": last_move,
            "recentMoves": list(self._recent_moves),
            "updatedAt": int(time.time() * 1000),
        }
        self.publish_snapshot(snapshot)
        return snapshot

    def finish_game(self) -> None:
        snapshot = self.get_snapshot()
        if snapshot is None:
            return
        snapshot["status"] = "finished"
        snapshot["updatedAt"] = int(time.time() * 1000)
        self.publish_snapshot(snapshot)

    def publish_snapshot(self, snapshot: dict[str, Any]) -> None:
        snapshot_json = json.dumps(
            {"type": "snapshot", "payload": snapshot},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        with self._snapshot_lock:
            self._snapshot = snapshot
            self._snapshot_json = snapshot_json
        with self._peers_lock:
            peers = list(self._peers.values())
        for peer in peers:
            try:
                peer.send(snapshot_json)
            except (ConnectionError, OSError):
                self._remove_peer(peer.connection)

    def get_snapshot(self) -> dict[str, Any] | None:
        with self._snapshot_lock:
            if self._snapshot is None:
                return None
            return json.loads(json.dumps(self._snapshot, ensure_ascii=False))

    def get_websocket_message(self) -> bytes | None:
        with self._snapshot_lock:
            return self._snapshot_json

    @property
    def websocket_client_count(self) -> int:
        with self._peers_lock:
            return len(self._peers)

    def _add_peer(self, connection: socket.socket) -> _WebSocketPeer:
        peer = _WebSocketPeer(connection)
        with self._peers_lock:
            self._peers[connection] = peer
        LOGGER.info("[monitor] websocket-connected clients=%d", self.websocket_client_count)
        return peer

    def _remove_peer(self, connection: socket.socket) -> None:
        with self._peers_lock:
            removed = self._peers.pop(connection, None)
        if removed is not None:
            LOGGER.info("[monitor] websocket-disconnected clients=%d", self.websocket_client_count)


__all__ = ["BattleMonitor"]
