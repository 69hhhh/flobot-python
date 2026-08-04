import unittest

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
from flobot.patcher import patch


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


class BotTests(unittest.TestCase):
    def test_move_emits_attack_and_tracks_state(self) -> None:
        socket = FakeSocket()
        bot = Bot(socket, 0, game_update(armies=[5] + [1] * 8, terrain=[0] + [-1] * 8))
        self.assertTrue(bot.move(Move(0, 1)))
        self.assertEqual(socket.events, [("attack", 0, 1)])
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

    def test_public_server_removes_legacy_bot_prefix(self) -> None:
        self.assertEqual(normalize_agent_name("[Bot] Flobot", True), "Flobot")

    def test_bot_server_adds_bot_prefix(self) -> None:
        self.assertEqual(normalize_agent_name("Flobot", False), "[Bot] Flobot")

    def test_cli_accepts_explicit_websocket_transport(self) -> None:
        arguments = build_parser().parse_args(["config.json", "--transport", "websocket"])
        self.assertEqual(arguments.transport, "websocket")

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


if __name__ == "__main__":
    unittest.main()
