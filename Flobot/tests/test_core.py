import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
import unittest.mock as mock
from urllib.request import Request, urlopen

import numpy as np
from generals.core.observation import Observation

from flobot.agent import FlobotAgent, action_to_server_indices, game_session_lost
from generals.core.action import Action
from flobot.algorithms import a_star, breadth_first_search, shortest_path
from flobot.bot import Bot, Move
from flobot.cli import build_parser, normalize_agent_name
from flobot.constants import Terrain
from flobot.game_map import GameMap
from flobot.game_state import GameState
from flobot.heuristics import choose_enemy_target_by_lowest_army
from flobot.monitor import BattleMonitor
from flobot.patcher import patch
from flobot.web_app import BotSessionManager, parse_room_url


def replace_all(values: list[int]) -> list[int]:
    return [0, len(values), *values]


def game_update(
    *,
    width: int = 3,
    height: int = 3,
    armies: list[int] | None = None,
    terrain: list[int] | None = None,
    generals: list[int] | None = None,
    turn: int = 1,
) -> dict:
    size = width * height
    armies = armies or [1] * size
    terrain = terrain or [Terrain.EMPTY] * size
    return {
        "cities_diff": [0, 0],
        "map_diff": replace_all([width, height, *armies, *terrain]),
        "generals": generals or [0, -1],
        "turn": turn,
    }


class FakeSocket:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def emit(self, event: str, *args: int) -> None:
        self.events.append((event, *args))


class PatcherTests(unittest.TestCase):
    def test_patch_examples_from_original_implementation(self) -> None:
        self.assertEqual(patch([0, 0], [1, 1, 3]), [0, 3])
        self.assertEqual(patch([0, 0], [0, 1, 2, 1]), [2, 0])


class StateAndMapTests(unittest.TestCase):
    def test_state_classifies_tiles_and_generals(self) -> None:
        state = GameState(
            game_update(
                armies=[5, 2, 1, 1, 1, 1, 1, 1, 4],
                terrain=[0, 0, -1, -2, -3, -4, -1, -1, 1],
                generals=[0, 8],
            ),
            0,
        )
        self.assertEqual(state.own_tiles, {0: 5, 1: 2})
        self.assertEqual(state.enemy_tiles, {8: 4})
        self.assertEqual((state.own_general, state.enemy_general), (0, 8))

    def test_adjacency_never_wraps_rows(self) -> None:
        state = GameState(game_update(), 0)
        game_map = GameMap(3, 3, 0)
        self.assertEqual({tile.index for tile in game_map.adjacent_tiles(state, 2)}, {1, 5})
        self.assertEqual({tile.index for tile in game_map.adjacent_tiles(state, 0)}, {1, 3})

    def test_index_zero_can_attack(self) -> None:
        state = GameState(
            game_update(armies=[5, 1, 1, 1, 1, 1, 1, 1, 1], terrain=[0, 1, -1, -1, -1, -1, -1, -1, -1]),
            0,
        )
        self.assertEqual(GameMap.remaining_armies_after_attack(state, 0, 1), 3)

    def test_known_city_is_walkable_and_pathable(self) -> None:
        state = GameState(
            game_update(
                width=3,
                height=1,
                armies=[8, 3, 1],
                terrain=[0, Terrain.EMPTY, 1],
                generals=[0, -1],
            ),
            0,
        )
        state.cities = [1]
        game_map = GameMap(3, 1, 0)
        self.assertTrue(game_map.is_walkable(state, 1))
        self.assertEqual(a_star(state, game_map, 0, [2]), [0, 1, 2])

    def test_enemy_target_falls_back_after_fog_is_fully_explored(self) -> None:
        state = GameState(
            game_update(
                width=4,
                height=1,
                armies=[8, 2, 4, 1],
                terrain=[0, 0, 1, 1],
                generals=[0, -1],
                turn=300,
            ),
            0,
        )
        state.discovered_tiles = [True] * state.size
        target = choose_enemy_target_by_lowest_army(state, GameMap(4, 1, 0))
        self.assertEqual(target, 2)


class AlgorithmTests(unittest.TestCase):
    def setUp(self) -> None:
        terrain = [0, -1, -1, -1, Terrain.MOUNTAIN, -1, -1, -1, 1]
        self.state = GameState(game_update(terrain=terrain, generals=[0, 8]), 0)
        self.game_map = GameMap(3, 3, 0)

    def test_bfs_respects_radius_and_obstacles(self) -> None:
        found = breadth_first_search(self.state, self.game_map, 0, 2)
        self.assertEqual({(tile.index, tile.general_distance) for tile in found}, {(1, 1), (3, 1), (2, 2), (6, 2)})

    def test_shortest_path_returns_only_moves(self) -> None:
        moves = shortest_path(self.state, self.game_map, 0, 8)
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(isinstance(move, Move) for move in moves))
        self.assertEqual(moves[0].start, 0)
        self.assertEqual(moves[-1].end, 8)

    def test_a_star_routes_around_mountain(self) -> None:
        path = a_star(self.state, self.game_map, 0, [8])
        self.assertEqual(path[0], 0)
        self.assertEqual(path[-1], 8)
        self.assertNotIn(4, path)

    def test_a_star_accounts_for_city_defenders(self) -> None:
        state = GameState(
            game_update(
                width=3,
                height=2,
                armies=[20, 50, 1, 0, 0, 0],
                terrain=[0, Terrain.EMPTY, 1, Terrain.EMPTY, Terrain.EMPTY, Terrain.EMPTY],
                generals=[0, -1],
            ),
            0,
        )
        state.cities = [1]
        path = a_star(state, GameMap(3, 2, 0), 0, [2])
        self.assertNotIn(1, path)
        self.assertEqual((path[0], path[-1]), (0, 2))


class BotTests(unittest.TestCase):
    def test_move_emits_attack_and_tracks_state(self) -> None:
        socket = FakeSocket()
        bot = Bot(socket, 0, game_update(armies=[5] + [1] * 8, terrain=[0] + [-1] * 8))
        self.assertTrue(bot.move(Move(0, 1)))
        self.assertEqual(socket.events, [("attack", 0, 1, 0)])
        self.assertEqual((bot.queued_moves, bot.move_count, bot.last_attacked_index), (1, 1, 1))

    def test_invalid_move_is_not_emitted(self) -> None:
        socket = FakeSocket()
        bot = Bot(socket, 0, game_update())
        self.assertFalse(bot.move(Move(0, -1)))
        self.assertEqual(socket.events, [])


class AgentTests(unittest.TestCase):
    @staticmethod
    def observation(turn: int = 1) -> Observation:
        shape = (3, 3)
        armies = np.ones(shape, dtype=int)
        armies[0, 0] = 5
        owned = np.zeros(shape, dtype=bool)
        owned[0, 0] = True
        neutral = ~owned
        generals = np.zeros(shape, dtype=bool)
        generals[0, 0] = True
        empty = np.zeros(shape, dtype=bool)
        return Observation(
            armies=armies,
            generals=generals,
            cities=empty,
            mountains=empty,
            neutral_cells=neutral,
            owned_cells=owned,
            opponent_cells=empty,
            fog_cells=empty,
            structures_in_fog=empty,
            owned_land_count=1,
            owned_army_count=5,
            opponent_land_count=0,
            opponent_army_count=0,
            timestep=turn,
            priority=1,
        )

    @staticmethod
    def line_observation(
        armies: list[int],
        owned_indices: set[int],
        opponent_indices: set[int],
        *,
        turn: int,
        own_general: int = 0,
        enemy_general: int = -1,
        city_indices: set[int] | None = None,
    ) -> Observation:
        width = len(armies)
        shape = (1, width)
        owned = np.zeros(shape, dtype=bool)
        opponent = np.zeros(shape, dtype=bool)
        for index in owned_indices:
            owned[0, index] = True
        for index in opponent_indices:
            opponent[0, index] = True
        neutral = ~(owned | opponent)
        generals = np.zeros(shape, dtype=bool)
        generals[0, own_general] = True
        if enemy_general >= 0:
            generals[0, enemy_general] = True
        cities = np.zeros(shape, dtype=bool)
        for index in city_indices or set():
            cities[0, index] = True
        empty = np.zeros(shape, dtype=bool)
        return Observation(
            armies=np.asarray([armies], dtype=int),
            generals=generals,
            cities=cities,
            mountains=empty,
            neutral_cells=neutral,
            owned_cells=owned,
            opponent_cells=opponent,
            fog_cells=empty,
            structures_in_fog=empty,
            owned_land_count=len(owned_indices),
            owned_army_count=sum(armies[index] for index in owned_indices),
            opponent_land_count=len(opponent_indices),
            opponent_army_count=sum(armies[index] for index in opponent_indices),
            timestep=turn,
            priority=1,
        )

    def test_act_converts_index_move_to_standard_action(self) -> None:
        agent = FlobotAgent()
        agent.act(self.observation())
        agent._bot.pending_moves.append(Move(0, 1))
        action = agent.act(self.observation())
        self.assertEqual(action.tolist(), [0, 0, 0, 3, 0])
        self.assertIn("MOVE turn=1", agent.last_action)
        self.assertIn("source=0(0,0)", agent.last_action)

    def test_act_passes_when_strategy_has_no_move(self) -> None:
        agent = FlobotAgent()
        action = agent.act(self.observation(turn=1))
        self.assertEqual(action.tolist(), [1, 0, 0, 0, 0])
        self.assertIn("PASS turn=1", agent.last_action)
        self.assertIn("land=1", agent.last_action)

    def test_late_game_attacks_after_map_is_fully_explored(self) -> None:
        agent = FlobotAgent()
        observation = self.line_observation(
            [20, 1, 1, 1, 8, 2],
            {0, 1, 2, 3, 4},
            {5},
            turn=251,
        )
        action = agent.act(observation)
        self.assertEqual(action.tolist(), [0, 0, 4, 3, 0])

    def test_visible_threat_causes_general_reinforcement(self) -> None:
        agent = FlobotAgent()
        observation = self.line_observation(
            [8, 10, 20, 0, 0],
            {0, 1},
            {2},
            turn=251,
        )
        action = agent.act(observation)
        self.assertEqual(action.tolist(), [0, 0, 1, 2, 0])

    def test_general_threat_interrupts_queued_offensive_move(self) -> None:
        agent = FlobotAgent()
        agent._bot.pending_moves.append(Move(4, 5))
        observation = self.line_observation(
            [8, 10, 20, 0, 4, 0],
            {0, 1, 4},
            {2},
            turn=251,
        )
        action = agent.act(observation)
        self.assertEqual(action.tolist(), [0, 0, 1, 2, 0])

    def test_general_uses_split_move_to_keep_a_garrison(self) -> None:
        agent = FlobotAgent()
        observation = self.line_observation(
            [30, 0, 0, 0, 0, 2],
            {0},
            {5},
            turn=251,
        )
        action = agent.act(observation)
        self.assertEqual(action.tolist(), [0, 0, 0, 3, 1])

    def test_affordable_neutral_city_can_be_captured(self) -> None:
        agent = FlobotAgent()
        observation = self.line_observation(
            [12, 3, 0],
            {0},
            set(),
            turn=50,
            city_indices={1},
        )
        action = agent.act(observation)
        self.assertEqual(action.tolist(), [0, 0, 0, 3, 1])

    def test_enemy_general_position_is_remembered_out_of_view(self) -> None:
        agent = FlobotAgent()
        visible = self.line_observation(
            [20, 1, 1, 1, 1, 5],
            {0, 1},
            {5},
            turn=100,
            enemy_general=5,
        )
        hidden_again = self.line_observation(
            [21, 1, 1, 1, 1, 5],
            {0, 1},
            {5},
            turn=101,
        )
        agent._to_state(visible)
        state = agent._to_state(hidden_again)
        self.assertEqual(state.enemy_general, 5)

    def test_public_server_removes_legacy_bot_prefix(self) -> None:
        self.assertEqual(normalize_agent_name("[Bot] Flobot", True), "Flobot")

    def test_bot_server_adds_bot_prefix(self) -> None:
        self.assertEqual(normalize_agent_name("Flobot", False), "[Bot] Flobot")

    def test_cli_accepts_explicit_websocket_transport(self) -> None:
        arguments = build_parser().parse_args(["config.json", "--transport", "websocket"])
        self.assertEqual(arguments.transport, "websocket")

    def test_cli_accepts_monitor_settings(self) -> None:
        arguments = build_parser().parse_args(
            ["config.json", "--monitor-host", "127.0.0.1", "--monitor-port", "9000"]
        )
        self.assertEqual(arguments.monitor_host, "127.0.0.1")
        self.assertEqual(arguments.monitor_port, 9000)
        self.assertFalse(arguments.no_monitor)

    def test_large_map_action_indices_do_not_overflow_int8(self) -> None:
        action = Action(to_pass=False, row=14, col=14, direction=2, to_split=False)
        self.assertEqual(action_to_server_indices(action, width=15), (224, 223, 0))

    def test_pass_action_produces_no_server_attack(self) -> None:
        self.assertIsNone(action_to_server_indices(Action(to_pass=True), width=15))

    def test_changed_socket_session_ends_local_game(self) -> None:
        self.assertTrue(game_session_lost("old-sid", "new-sid", True))
        self.assertTrue(game_session_lost("old-sid", None, True))
        self.assertTrue(game_session_lost("old-sid", "old-sid", False))
        self.assertFalse(game_session_lost("same-sid", "same-sid", True))


class MonitorTests(unittest.TestCase):
    @staticmethod
    def _read_exact(connection: socket.socket, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = connection.recv(length - len(data))
            if not chunk:
                raise AssertionError("WebSocket connection closed before a complete frame arrived")
            data.extend(chunk)
        return bytes(data)

    def _start_monitor_with_snapshot(self) -> tuple[BattleMonitor, dict]:
        agent = FlobotAgent("Flobot")
        observation = AgentTests.observation(turn=7)
        action = agent.act(observation)
        server_action = action_to_server_indices(action, width=3)
        monitor = BattleMonitor(port=0)
        monitor.start()
        monitor.begin_game("test-replay", "Flobot")
        snapshot = monitor.publish_turn(agent._bot.game_state, observation, server_action)
        return monitor, snapshot

    def test_polling_endpoint_returns_latest_snapshot(self) -> None:
        monitor, expected = self._start_monitor_with_snapshot()
        try:
            with urlopen(f"http://127.0.0.1:{monitor.port}/api/snapshot", timeout=2) as response:
                payload = json.load(response)
            self.assertEqual(payload["gameId"], "test-replay")
            self.assertEqual(payload["turn"], expected["turn"])
            self.assertEqual((payload["width"], payload["height"]), (3, 3))
            self.assertEqual(len(payload["tiles"]), 9)
        finally:
            monitor.stop()

    def test_finished_snapshot_records_victory_or_defeat(self) -> None:
        monitor, _expected = self._start_monitor_with_snapshot()
        try:
            monitor.finish_game(True)
            self.assertEqual(monitor.get_snapshot()["status"], "finished")
            self.assertEqual(monitor.get_snapshot()["result"], "victory")
            monitor.finish_game(False)
            self.assertEqual(monitor.get_snapshot()["result"], "defeat")
        finally:
            monitor.stop()

    def test_websocket_endpoint_pushes_snapshot_message(self) -> None:
        monitor, _expected = self._start_monitor_with_snapshot()
        connection = socket.create_connection(("127.0.0.1", monitor.port), timeout=2)
        try:
            request = (
                "GET /ws HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{monitor.port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            )
            connection.sendall(request.encode("ascii"))
            response_headers = bytearray()
            while not response_headers.endswith(b"\r\n\r\n"):
                response_headers.extend(self._read_exact(connection, 1))
            self.assertIn(b"101 Switching Protocols", response_headers)

            header = self._read_exact(connection, 2)
            self.assertEqual(header[0] & 0x0F, 0x1)
            length = header[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(connection, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(connection, 8))[0]
            message = json.loads(self._read_exact(connection, length).decode("utf-8"))
            self.assertEqual(message["type"], "snapshot")
            self.assertEqual(message["payload"]["gameId"], "test-replay")
        finally:
            connection.close()
            monitor.stop()

    def test_static_frontend_and_session_control_are_served_together(self) -> None:
        class FakeSessionController:
            def __init__(self) -> None:
                self.payload = None
                self.restart_payload = None

            def start_session(self, payload: dict) -> tuple[int, dict]:
                self.payload = payload
                return 202, {"state": "starting", "roomId": "room"}

            def stop_session(self) -> tuple[int, dict]:
                return 200, {"state": "idle", "roomId": None}

            def restart_session(self, payload: dict) -> tuple[int, dict]:
                self.restart_payload = payload
                return 202, {"state": "starting", "roomId": "room"}

            def get_status(self) -> dict:
                return {"state": "idle", "roomId": None}

        with tempfile.TemporaryDirectory() as directory:
            static_dir = Path(directory)
            (static_dir / "index.html").write_text("<h1>Flobot UI</h1>", encoding="utf-8")
            controller = FakeSessionController()
            monitor = BattleMonitor(port=0, static_dir=static_dir)
            monitor.set_session_controller(controller)
            monitor.start()
            try:
                with urlopen(f"http://127.0.0.1:{monitor.port}/", timeout=2) as response:
                    self.assertIn("Flobot UI", response.read().decode("utf-8"))
                body = json.dumps(
                    {
                        "roomUrl": "https://generals.io/games/room",
                        "userId": "private-id",
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{monitor.port}/api/session/start",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=2) as response:
                    payload = json.load(response)
                self.assertEqual(payload["state"], "starting")
                self.assertEqual(controller.payload["userId"], "private-id")
                request = Request(
                    f"http://127.0.0.1:{monitor.port}/api/session/restart",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=2) as response:
                    payload = json.load(response)
                self.assertEqual(payload["state"], "starting")
                self.assertEqual(controller.restart_payload["userId"], "private-id")
            finally:
                monitor.stop()


class WebAppTests(unittest.TestCase):
    def test_room_url_parser_accepts_only_official_rooms(self) -> None:
        self.assertEqual(
            parse_room_url("https://generals.io/games/my-room"),
            ("my-room", True),
        )
        self.assertEqual(
            parse_room_url("https://bot.generals.io/games/bot-room"),
            ("bot-room", False),
        )
        with self.assertRaises(ValueError):
            parse_room_url("https://example.com/games/stolen")

    def test_web_session_invokes_original_python_agent(self) -> None:
        monitor = BattleMonitor(port=0)
        sessions = BotSessionManager(monitor)
        with mock.patch("flobot.web_app.run_live_agent") as run_agent:
            status, _payload = sessions.start_session(
                {
                    "roomUrl": "https://generals.io/games/my-room",
                    "userId": "private-user-id",
                }
            )
            self.assertEqual(status, 202)
            sessions.shutdown()
        run_agent.assert_called_once()
        call = run_agent.call_args
        self.assertIsInstance(call.args[0], FlobotAgent)
        self.assertEqual(call.kwargs["user_id"], "private-user-id")
        self.assertEqual(call.kwargs["lobby_id"], "my-room")
        self.assertNotIn("private-user-id", json.dumps(sessions.get_status()))

    def test_web_session_can_restart_an_active_game(self) -> None:
        monitor = BattleMonitor(port=0)
        sessions = BotSessionManager(monitor)
        first_started = threading.Event()
        second_started = threading.Event()

        def wait_for_stop(*_args, **kwargs) -> None:
            if first_started.is_set():
                second_started.set()
            else:
                first_started.set()
            kwargs["stop_event"].wait(2)

        connection = {
            "roomUrl": "https://generals.io/games/my-room",
            "userId": "private-user-id",
        }
        with mock.patch("flobot.web_app.run_live_agent", side_effect=wait_for_stop) as run_agent:
            status, _payload = sessions.start_session(connection)
            self.assertEqual(status, 202)
            self.assertTrue(first_started.wait(1))
            status, payload = sessions.restart_session(connection)
            self.assertEqual(status, 202)
            self.assertIn(payload["state"], {"starting", "running"})
            self.assertTrue(second_started.wait(1))
            sessions.shutdown()
        self.assertEqual(run_agent.call_count, 2)
        self.assertNotIn("private-user-id", json.dumps(sessions.get_status()))


if __name__ == "__main__":
    unittest.main()
