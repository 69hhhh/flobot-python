from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import logging
import threading
from typing import TYPE_CHECKING, Any

import numpy as np
from generals.agents import Agent
from generals.core.action import Action
from generals.core.observation import Observation

from .bot_types import Move
from .constants import RUSH_COLLECT_TURNS, Terrain
from .game_map import GameMap
from .strategy import pick_strategy

if TYPE_CHECKING:
    from .monitor import BattleMonitor

LOGGER = logging.getLogger("flobot.diagnostics")
DIRECTION_NAMES = ("up", "down", "left", "right")


@dataclass
class ObservationState:
    """Game-state view used by the original Flobot strategies."""

    width: int
    height: int
    size: int
    player_index: int
    turn: int
    armies: list[int]
    terrain: list[int]
    cities: list[int]
    own_tiles: dict[int, int]
    enemy_tiles: dict[int, int]
    own_general: int
    enemy_general: int
    discovered_tiles: list[bool]
    generals: list[int] = field(default_factory=list)


class _StrategyBot:
    """Small facade that lets legacy strategies queue actions without a socket."""

    def __init__(self) -> None:
        self.pending_moves: deque[Move] = deque()
        self.queued_moves = 0
        self.last_attacked_index = -1
        self.move_count = 0
        self.is_collecting = False
        self.collect_area: list[int] = []
        self.is_infiltrating = False
        self.rush_collect_turns_left = RUSH_COLLECT_TURNS
        self.game_state: ObservationState
        self.game_map: GameMap

    def move(self, move: Move) -> bool:
        if move.end == -1:
            return False
        self.pending_moves.append(move)
        self.queued_moves = len(self.pending_moves)
        return True

    def queue_moves(self, moves: list[Move]) -> None:
        for move in moves:
            self.move(move)

    def clear_moves(self) -> None:
        self.pending_moves.clear()
        self.queued_moves = 0


class FlobotAgent(Agent):
    """Expose the Flobot heuristics through generals-bots' Agent.act API."""

    def __init__(self, id: str = "[Bot] Flobot"):
        super().__init__(id)
        self._bot = _StrategyBot()
        self._discovered: list[bool] = []
        self._shape: tuple[int, int] | None = None
        self.last_turn = -1
        self.last_action = "not-started"

    def reset(self) -> None:
        self._bot = _StrategyBot()
        self._discovered = []
        self._shape = None
        self.last_turn = -1
        self.last_action = "reset"

    def act(self, observation: Observation) -> Action:
        state = self._to_state(observation)
        self._bot.game_state = state
        self._bot.game_map = GameMap(state.width, state.height, state.player_index)
        self.last_turn = state.turn
        LOGGER.debug(
            "[turn] turn=%d land=%d army=%d opponent_land=%d opponent_army=%d "
            "queued=%d collecting=%s infiltrating=%s own_general=%d enemy_general=%d",
            state.turn,
            int(observation.owned_land_count),
            int(observation.owned_army_count),
            int(observation.opponent_land_count),
            int(observation.opponent_army_count),
            len(self._bot.pending_moves),
            self._bot.is_collecting,
            self._bot.is_infiltrating,
            state.own_general,
            state.enemy_general,
        )

        move = self._next_valid_queued_move(state)
        if move is None:
            self._bot.clear_moves()
            pick_strategy(self._bot)  # type: ignore[arg-type]
            move = self._next_valid_queued_move(state)

        if move is None:
            self.last_action = (
                f"PASS turn={state.turn} land={int(observation.owned_land_count)} "
                "reason=no-valid-strategy-move"
            )
            LOGGER.debug("[action] %s", self.last_action)
            return Action(to_pass=True)

        direction = self._direction(move, state.width)
        if direction is None:
            self.last_action = f"PASS turn={state.turn} reason=invalid-direction move={move}"
            LOGGER.warning("[action] %s", self.last_action)
            return Action(to_pass=True)
        row, column = divmod(move.start, state.width)
        end_row, end_column = divmod(move.end, state.width)
        self._bot.last_attacked_index = move.end
        self._bot.move_count += 1
        self.last_action = (
            f"MOVE turn={state.turn} source={move.start}({row},{column}) "
            f"destination={move.end}({end_row},{end_column}) "
            f"direction={DIRECTION_NAMES[direction]} split=0 "
            f"source_army={state.armies[move.start]} "
            f"destination_army={state.armies[move.end]} land={int(observation.owned_land_count)}"
        )
        LOGGER.debug("[action] %s", self.last_action)
        return Action(
            to_pass=False,
            row=row,
            col=column,
            direction=direction,
            to_split=False,
        )

    def _next_valid_queued_move(self, state: ObservationState) -> Move | None:
        while self._bot.pending_moves:
            move = self._bot.pending_moves.popleft()
            self._bot.queued_moves = len(self._bot.pending_moves)
            rejection = self._move_rejection_reason(move, state)
            if rejection is None:
                return move
            LOGGER.debug(
                "[queue] turn=%d discarded start=%d end=%d reason=%s remaining=%d",
                state.turn,
                move.start,
                move.end,
                rejection,
                len(self._bot.pending_moves),
            )
        return None

    def _move_rejection_reason(self, move: Move, state: ObservationState) -> str | None:
        if not 0 <= move.start < state.size:
            return "source-out-of-bounds"
        if not 0 <= move.end < state.size:
            return "destination-out-of-bounds"
        if move.start not in state.own_tiles:
            return "source-not-owned"
        if state.armies[move.start] <= 1:
            return "source-has-one-army"
        if not self._are_adjacent(move, state.width):
            return "tiles-not-adjacent"
        if self._direction(move, state.width) is None:
            return "invalid-direction"
        return None

    @staticmethod
    def _are_adjacent(move: Move, width: int) -> bool:
        start_row, start_column = divmod(move.start, width)
        end_row, end_column = divmod(move.end, width)
        return abs(start_row - end_row) + abs(start_column - end_column) == 1

    @staticmethod
    def _direction(move: Move, width: int) -> int | None:
        difference = move.end - move.start
        return {-width: 0, width: 1, -1: 2, 1: 3}.get(difference)

    def _to_state(self, observation: Observation) -> ObservationState:
        height, width = observation.armies.shape
        if self._shape != (height, width):
            self._shape = (height, width)
            self._discovered = [False] * (height * width)
            self._bot.clear_moves()

        armies = np.asarray(observation.armies, dtype=int).reshape(-1).tolist()
        terrain = np.full((height, width), Terrain.FOG, dtype=int)
        terrain[np.asarray(observation.structures_in_fog, dtype=bool)] = Terrain.FOG_OBSTACLE
        terrain[np.asarray(observation.mountains, dtype=bool)] = Terrain.MOUNTAIN
        terrain[np.asarray(observation.neutral_cells, dtype=bool)] = Terrain.EMPTY
        terrain[np.asarray(observation.opponent_cells, dtype=bool)] = 1
        terrain[np.asarray(observation.owned_cells, dtype=bool)] = 0
        flat_terrain = terrain.reshape(-1).tolist()

        visible = ~(
            np.asarray(observation.fog_cells, dtype=bool)
            | np.asarray(observation.structures_in_fog, dtype=bool)
        )
        for index in np.flatnonzero(visible):
            self._discovered[int(index)] = True

        own_mask = np.asarray(observation.owned_cells, dtype=bool).reshape(-1)
        enemy_mask = np.asarray(observation.opponent_cells, dtype=bool).reshape(-1)
        general_mask = np.asarray(observation.generals, dtype=bool).reshape(-1)
        own_general_indices = np.flatnonzero(general_mask & own_mask)
        enemy_general_indices = np.flatnonzero(general_mask & enemy_mask)
        own_general = int(own_general_indices[0]) if len(own_general_indices) else -1
        enemy_general = int(enemy_general_indices[0]) if len(enemy_general_indices) else -1

        own_indices = np.flatnonzero(own_mask)
        enemy_indices = np.flatnonzero(enemy_mask)
        own_tiles = {int(index): armies[int(index)] for index in own_indices}
        enemy_tiles = {int(index): armies[int(index)] for index in enemy_indices}
        cities = [int(index) for index in np.flatnonzero(np.asarray(observation.cities).reshape(-1))]

        return ObservationState(
            width=width,
            height=height,
            size=width * height,
            player_index=0,
            turn=int(observation.timestep),
            armies=armies,
            terrain=flat_terrain,
            cities=cities,
            own_tiles=own_tiles,
            enemy_tiles=enemy_tiles,
            own_general=own_general,
            enemy_general=enemy_general,
            discovered_tiles=self._discovered.copy(),
            generals=[own_general, enemy_general],
        )


def action_to_server_indices(action: Action, width: int) -> tuple[int, int, int] | None:
    """Convert an Action without generals-bots 2.5.0's NumPy int8 overflow."""
    if bool(action[0]):
        return None
    row = int(action[1])
    column = int(action[2])
    direction = int(action[3])
    split = int(action[4])
    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if not 0 <= direction < len(offsets):
        raise ValueError(f"invalid action direction: {direction}")
    row_offset, column_offset = offsets[direction]
    source_index = row * width + column
    destination_index = (row + row_offset) * width + column + column_offset
    return source_index, destination_index, split


def game_session_lost(initial_sid: str | None, current_sid: str | None, connected: bool) -> bool:
    """Return true when a reconnect can no longer belong to the active game."""
    return not connected or current_sid is None or current_sid != initial_sid


def run_live_agent(
    agent: FlobotAgent,
    user_id: str,
    lobby_id: str,
    *,
    public_server: bool,
    number_of_games: int = 1,
    game_speed: int | None = None,
    register_username: bool = True,
    transport: str = "auto",
    monitor: BattleMonitor | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Run Flobot using the official generals-bots remote client."""
    from socketio import Client as SocketIOClient
    from generals.remote import GeneralsIOClient
    from socketio.exceptions import DisconnectedError, TimeoutError

    class NonReconnectingSocketIOClient(SocketIOClient):
        def __init__(self, *args: Any, **kwargs: Any):
            kwargs["reconnection"] = False
            super().__init__(*args, **kwargs)

    class OverflowSafeGeneralsIOClient(GeneralsIOClient):
        client_class = NonReconnectingSocketIOClient

        def connect(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            auth: Any = None,
            transports: list[str] | None = None,
            namespace: str = "/",
            socketio_path: str = "socket.io",
            wait_timeout: int = 5,
        ) -> None:
            selected_transports = None if transport == "auto" else [transport]
            super().connect(
                url,
                headers=headers or {},
                auth=auth,
                transports=selected_transports or transports,
                namespace=namespace,
                socketio_path=socketio_path,
                wait_timeout=wait_timeout,
            )

        def _generate_action(self, observation: Observation) -> tuple[int, int, int] | None:
            action = self.agent.act(observation)
            width = int(self.game_state.map[0])
            return action_to_server_indices(action, width)

        def _play_game(self) -> None:
            game_sid = self.sid
            self._game_diagnostic_sid = game_sid
            if monitor is not None:
                monitor.begin_game(self.replay_id or lobby_id, self.agent.id)
            LOGGER.info("[network] game-start sid=%s replay=%s", game_sid, self.replay_id)
            while True:
                if stop_event is not None and stop_event.is_set():
                    LOGGER.info("[network] stop-requested sid=%s", self.sid)
                    self.emit("leave_game")
                    self._status = "off"
                    return
                try:
                    message = self.receive(timeout=1 if stop_event is not None else 10)
                except TimeoutError:
                    if game_session_lost(game_sid, self.sid, self.connected):
                        self._finish_disconnected_game()
                        return
                    LOGGER.warning(
                        "[network] receive-timeout sid=%s last_turn=%d last_action=%s",
                        self.sid,
                        self.agent.last_turn,
                        self.agent.last_action,
                    )
                    continue
                except DisconnectedError:
                    self._finish_disconnected_game()
                    return

                if game_session_lost(game_sid, self.sid, self.connected):
                    self._finish_disconnected_game()
                    return
                if not message:
                    continue
                event, *data = message
                if event == "game_update" and data:
                    self.game_state.update(data[0])
                    LOGGER.debug(
                        "[network] event=game_update sid=%s turn=%s",
                        self.sid,
                        self.game_state.turn,
                    )
                    observation = self.game_state.get_observation()
                    action = self._generate_action(observation)
                    if monitor is not None:
                        monitor.publish_turn(self.agent._bot.game_state, observation, action)
                    if action:
                        LOGGER.debug("[network] emit=attack payload=%s sid=%s", action, self.sid)
                        self.emit("attack", action)
                elif event in {"game_lost", "game_won"}:
                    LOGGER.info(
                        "[network] event=%s sid=%s last_turn=%d last_action=%s",
                        event,
                        self.sid,
                        self.agent.last_turn,
                        self.agent.last_action,
                    )
                    if monitor is not None:
                        monitor.finish_game(event == "game_won")
                    self._finish_game(event == "game_won")
                    return
                else:
                    LOGGER.debug("[network] event=%s sid=%s data=%s", event, self.sid, data)

        def _finish_disconnected_game(self) -> None:
            self._status = "off"
            self._score_losses += 1
            LOGGER.error(
                "[network] game-session-lost initial_sid=%s current_sid=%s connected=%s "
                "last_turn=%d last_action=%s",
                getattr(self, "_game_diagnostic_sid", None),
                self.sid,
                self.connected,
                self.agent.last_turn,
                self.agent.last_action,
            )
            print(
                "Game connection was replaced or disconnected; the server "
                "removed this player, so the local game loop has stopped."
            )
            if self.replay_id:
                prefix = "" if self.public_server else "bot."
                print(f"Replay link: https://{prefix}generals.io/replays/{self.replay_id}")

    with OverflowSafeGeneralsIOClient(agent, user_id, public_server=public_server) as client:
        LOGGER.info(
            "[network] requested_transport=%s active_transport=%s sid=%s",
            transport,
            client.transport,
            client.sid,
        )
        if register_username:
            try:
                client.register_agent(agent.id)
            except ValueError as error:
                if "already have a username" not in str(error).lower():
                    raise
                print(
                    "This user ID already has a username; keeping the existing "
                    "server username and continuing."
                )
        for game_number in range(max(1, number_of_games)):
            if stop_event is not None and stop_event.is_set():
                break
            agent.reset()
            client.join_private_lobby(lobby_id)
            if game_speed is not None:
                client.emit("set_custom_options", (lobby_id, {"game_speed": game_speed}))
            print(f"Starting game {game_number + 1}/{max(1, number_of_games)}...")
            client.join_game()
