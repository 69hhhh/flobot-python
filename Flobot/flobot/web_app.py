from __future__ import annotations

import argparse
import logging
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse
import webbrowser

from .agent import FlobotAgent, run_live_agent
from .monitor import BattleMonitor

LOGGER = logging.getLogger("flobot.web")
OFFICIAL_ROOM_HOSTS = {
    "generals.io": True,
    "www.generals.io": True,
    "bot.generals.io": False,
}


def parse_room_url(value: str) -> tuple[str, bool]:
    """Return (room_id, public_server) for an official Generals.io room URL."""
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_ROOM_HOSTS:
        raise ValueError("只允许 generals.io 官方 HTTPS 房间网址")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    try:
        games_index = parts.index("games")
        room_id = parts[games_index + 1]
    except (ValueError, IndexError):
        raise ValueError("房间网址必须包含 /games/房间ID") from None
    if not room_id:
        raise ValueError("房间 ID 不能为空")
    return room_id, OFFICIAL_ROOM_HOSTS[parsed.hostname]


class BotSessionManager:
    """Start and stop the original Python Flobot from local web requests."""

    def __init__(self, monitor: BattleMonitor) -> None:
        self.monitor = monitor
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._status: dict[str, Any] = {
            "state": "idle",
            "roomId": None,
            "message": "等待启动",
        }

    def start_session(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        room_url = payload.get("roomUrl")
        user_id = payload.get("userId")
        if not isinstance(room_url, str) or not isinstance(user_id, str) or not user_id.strip():
            return 400, {"error": "请填写房间网址和 user_id"}
        try:
            room_id, public_server = parse_room_url(room_url)
        except ValueError as error:
            return 400, {"error": str(error)}

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return 409, {"error": "已有机器人会话正在运行，请先停止"}
            stop_event = threading.Event()
            self._stop_event = stop_event
            self._status = {
                "state": "starting",
                "roomId": room_id,
                "message": "正在连接 Generals.io",
            }
            self.monitor.begin_game(room_id, "Flobot")
            worker = threading.Thread(
                target=self._run_session,
                args=(user_id.strip(), room_id, public_server, stop_event),
                name="flobot-game-session",
                daemon=True,
            )
            self._thread = worker
            worker.start()
        return 202, self.get_status()

    def stop_session(self) -> tuple[int, dict[str, Any]]:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._status = {
                    "state": "idle",
                    "roomId": None,
                    "message": "机器人未运行",
                }
                return 200, dict(self._status)
            self._status = {
                **self._status,
                "state": "stopping",
                "message": "正在安全退出房间",
            }
            if self._stop_event is not None:
                self._stop_event.set()
            return 202, dict(self._status)

    def restart_session(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Safely replace the current game with a fresh session using new request data."""
        room_url = payload.get("roomUrl")
        user_id = payload.get("userId")
        if not isinstance(room_url, str) or not isinstance(user_id, str) or not user_id.strip():
            return 400, {"error": "请填写房间网址和 user_id"}
        try:
            parse_room_url(room_url)
        except ValueError as error:
            return 400, {"error": str(error)}

        with self._lock:
            worker = self._thread
            stop_event = self._stop_event
            if worker is not None and worker.is_alive():
                self._status = {
                    **self._status,
                    "state": "restarting",
                    "message": "正在结束上一局并重新加入",
                }
                if stop_event is not None:
                    stop_event.set()

        if worker is not None and worker.is_alive():
            worker.join(timeout=3)
        if worker is not None and worker.is_alive():
            return 409, {"error": "上一局仍在退出，请稍后重试"}
        return self.start_session(payload)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def shutdown(self) -> None:
        with self._lock:
            event = self._stop_event
            worker = self._thread
        if event is not None:
            event.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout=3)

    def _run_session(
        self,
        user_id: str,
        room_id: str,
        public_server: bool,
        stop_event: threading.Event,
    ) -> None:
        agent_name = "Flobot" if public_server else "[Bot] Flobot"
        with self._lock:
            self._status = {
                "state": "running",
                "roomId": room_id,
                "message": "机器人已启动，等待房间或回合数据",
            }
        try:
            run_live_agent(
                FlobotAgent(agent_name),
                user_id=user_id,
                lobby_id=room_id,
                public_server=public_server,
                number_of_games=1,
                game_speed=None,
                register_username=False,
                transport="auto",
                monitor=self.monitor,
                stop_event=stop_event,
            )
        except Exception as error:  # Remote protocol failures are reported to the UI.
            LOGGER.error("Bot session ended with %s", type(error).__name__)
            with self._lock:
                self._status = {
                    "state": "error",
                    "roomId": room_id,
                    "message": "连接失败，请检查房间网址、user_id 和网络",
                }
            return
        with self._lock:
            if stop_event.is_set():
                self._status = {
                    "state": "idle",
                    "roomId": None,
                    "message": "机器人已停止",
                }
            else:
                self._status = {
                    "state": "finished",
                    "roomId": room_id,
                    "message": "对局已结束",
                }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Flobot local web application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "frontend" / "dist",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    index_file = args.static_dir / "index.html"
    if not index_file.is_file():
        raise SystemExit("前端尚未构建，请先在 frontend 目录运行 npm run build")

    monitor = BattleMonitor(args.host, args.port, static_dir=args.static_dir)
    sessions = BotSessionManager(monitor)
    monitor.set_session_controller(sessions)
    monitor.start()
    url = f"http://{args.host}:{monitor.port}/"
    print(f"Flobot 网页已启动：{url}")
    print("按 Ctrl+C 可关闭网页和机器人。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Stopping Flobot web application")
    finally:
        sessions.shutdown()
        monitor.stop()


if __name__ == "__main__":
    main()
