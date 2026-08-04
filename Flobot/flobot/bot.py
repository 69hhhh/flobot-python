from __future__ import annotations

from typing import Any, Protocol

from .bot_types import Move
from .constants import RUSH_COLLECT_TURNS
from .game_map import GameMap
from .game_state import GameState


class EventEmitter(Protocol):
    def emit(self, event: str, *args: Any) -> Any: ...


class Bot:
    def __init__(self, socket: EventEmitter, player_index: int, data: dict[str, Any]):
        self.socket = socket
        self.queued_moves = 0
        self.last_attacked_index = -1
        self.move_count = 0
        self.is_collecting = False
        self.collect_area: list[int] = []
        self.is_infiltrating = False
        self.rush_collect_turns_left = RUSH_COLLECT_TURNS
        self.game_state = GameState(data, player_index)
        self.game_map = GameMap(self.game_state.width, self.game_state.height, player_index)

    def update(self, data: dict[str, Any]) -> None:
        from .strategy import pick_strategy

        self.game_state.update(data)
        self.queued_moves = max(0, self.queued_moves - 1)
        pick_strategy(self)

    def queue_moves(self, moves: list[Move]) -> None:
        for move in moves:
            self.move(move)

    def move(self, move: Move) -> bool:
        if move.end == -1:
            return False
        if not (0 <= move.start < self.game_state.size and 0 <= move.end < self.game_state.size):
            return False
        self.queued_moves += 1
        self.last_attacked_index = move.end
        self.socket.emit("attack", move.start, move.end)
        self.move_count += 1
        return True


__all__ = ["Bot", "Move"]
