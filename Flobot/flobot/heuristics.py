from __future__ import annotations

from .algorithms_types import Reachable
from .constants import Terrain
from .game_map import GameMap
from .game_state import GameState


def choose_discover_tile(game_map: GameMap, tiles: list[Reachable]) -> int | None:
    if not tiles:
        return None
    maximum_distance = max(tile.general_distance for tile in tiles)
    candidates = [tile.index for tile in tiles if tile.general_distance == maximum_distance]
    return max(candidates, key=game_map.edge_weight)


def choose_enemy_target_by_lowest_army(state: GameState, game_map: GameMap) -> int | None:
    candidates = [index for index in state.enemy_tiles if game_map.is_adjacent_to_fog(state, index)]
    return min(candidates, key=state.enemy_tiles.__getitem__) if candidates else None


def capture_weight(player_index: int, terrain_value: int) -> int:
    if terrain_value == player_index:
        return 0
    if terrain_value in (Terrain.EMPTY, Terrain.FOG):
        return 1
    if terrain_value >= 0:
        return 3
    return 0
