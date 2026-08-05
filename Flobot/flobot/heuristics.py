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
    """Choose a useful enemy border without becoming idle on a fully explored map."""
    candidates = list(state.enemy_tiles)
    if not candidates:
        return None

    exposed = [
        index for index in candidates if game_map.is_adjacent_to_player(state, index)
    ]
    frontier = [
        index for index in candidates if game_map.is_adjacent_to_fog(state, index)
    ]
    frontier_set = set(frontier)
    exposed_frontier = [index for index in exposed if index in frontier_set]
    pool = exposed_frontier or exposed or frontier or candidates
    general = state.own_general
    return min(
        pool,
        key=lambda index: (
            state.enemy_tiles[index],
            game_map.manhattan_distance(general, index) if general >= 0 else 0,
        ),
    )


def choose_neutral_city_target(state: GameState, game_map: GameMap) -> int | None:
    """Return the cheapest visible city that is not already owned."""
    candidates = [
        index
        for index in state.cities
        if 0 <= index < state.size
        and state.terrain[index] != state.player_index
        and game_map.is_walkable(state, index)
    ]
    if not candidates:
        return None
    general = state.own_general
    return min(
        candidates,
        key=lambda index: (
            state.armies[index],
            game_map.manhattan_distance(general, index) if general >= 0 else 0,
        ),
    )


def capture_weight(player_index: int, terrain_value: int) -> int:
    if terrain_value == player_index:
        return 0
    if terrain_value in (Terrain.EMPTY, Terrain.FOG):
        return 1
    if terrain_value >= 0:
        return 3
    return 0
