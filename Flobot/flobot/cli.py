from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .agent import FlobotAgent, run_live_agent


def normalize_agent_name(name: str, public_server: bool) -> str:
    """Apply the username convention expected by the selected live server."""
    clean_name = name.strip()
    if public_server:
        if clean_name.startswith("[Bot]"):
            clean_name = clean_name[len("[Bot]") :].strip()
        return clean_name or "Flobot"
    if not clean_name.startswith("[Bot]"):
        return f"[Bot] {clean_name or 'Flobot'}"
    return clean_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Python Flobot for generals.io")
    parser.add_argument("config_file", type=Path)
    parser.add_argument("-n", "--number-of-games", type=int, default=1)
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument(
        "--diagnostics-file",
        type=Path,
        default=Path("flobot-diagnostics.log"),
        help="write diagnostic logs to this file (default: flobot-diagnostics.log)",
    )
    parser.add_argument(
        "--transport",
        choices=("auto", "polling", "websocket"),
        default="auto",
        help="Socket.IO transport to use (default: auto)",
    )
    parser.add_argument(
        "--no-register-username",
        action="store_true",
        help="do not call the remote client's bot registration endpoint",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.diagnostics_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.FileHandler(args.diagnostics_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("flobot").info("Diagnostic log: %s", args.diagnostics_file.resolve())
    with args.config_file.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    game = config["gameConfig"]
    server_url = game.get("GAME_SERVER_URL", "wss://botws.generals.io/").lower()
    public_server = "botws.generals.io" not in server_url
    configured_name = game.get("username", "[Bot] Flobot")
    agent_name = normalize_agent_name(configured_name, public_server)
    if agent_name != configured_name:
        logging.getLogger("flobot").info(
            "Using server-compatible agent name %r instead of %r",
            agent_name,
            configured_name,
        )
    agent = FlobotAgent(agent_name)
    try:
        run_live_agent(
            agent,
            user_id=game["userId"],
            lobby_id=game["customGameId"],
            public_server=public_server,
            number_of_games=args.number_of_games,
            game_speed=game.get("customGameSpeed"),
            register_username=not args.no_register_username,
            transport=args.transport,
        )
    except KeyboardInterrupt:
        logging.getLogger("flobot").info("Interrupted; leaving game")


if __name__ == "__main__":
    main()
