from __future__ import annotations

from dataclasses import dataclass

from .constants import Terrain
from .game_state import GameState


@dataclass(frozen=True)
class Tile:
    index: int
    value: int


class GameMap:
    def __init__(self, width: int, height: int, player_index: int):
        self.width = width
        self.height = height
        self.size = width * height
        self.player_index = player_index

    def is_walkable(self, state: GameState, tile: Tile | int) -> bool:
        if isinstance(tile, int):
            if not 0 <= tile < self.size:
                return False
            tile = Tile(tile, state.terrain[tile])
        return tile.value not in {
            Terrain.FOG_OBSTACLE,
            Terrain.OFF_LIMITS,
            Terrain.MOUNTAIN,
        } and not self.is_city(state, tile)

    @staticmethod
    def is_city(state: GameState, tile: Tile | int) -> bool:
        index = tile if isinstance(tile, int) else tile.index
        return index in state.cities

    def is_enemy(self, state: GameState, index: int) -> bool:
        return 0 <= index < self.size and state.terrain[index] >= 0 and state.terrain[index] != self.player_index

    def adjacent_tiles(self, state: GameState, index: int) -> tuple[Tile, ...]:
        if not 0 <= index < self.size:
            return ()
        x, y = self.coordinates(index)
        candidates = ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
        tiles = []
        for next_x, next_y in candidates:
            if 0 <= next_x < self.width and 0 <= next_y < self.height:
                next_index = next_y * self.width + next_x
                tiles.append(Tile(next_index, state.terrain[next_index]))
        return tuple(tiles)

    def is_adjacent_to_fog(self, state: GameState, index: int) -> bool:
        return any(not state.discovered_tiles[tile.index] for tile in self.adjacent_tiles(state, index))

    def is_adjacent_to_enemy(self, state: GameState, index: int) -> bool:
        return any(self.is_enemy(state, tile.index) for tile in self.adjacent_tiles(state, index))

    @staticmethod
    def moveable_tiles(state: GameState) -> list[int]:
        return [index for index, armies in state.own_tiles.items() if armies > 1]

    @staticmethod
    def remaining_armies_after_attack(state: GameState, start: int, end: int) -> int:
        if 0 <= start < state.size and 0 <= end < state.size:
            return state.armies[start] - 1 - state.armies[end]
        return 0

    def edge_weight(self, index: int) -> int:
        x, y = self.coordinates(index)
        return min(y, self.height - 1 - y) * min(x, self.width - 1 - x)

    def manhattan_distance(self, first: int, second: int) -> int:
        x1, y1 = self.coordinates(first)
        x2, y2 = self.coordinates(second)
        return abs(x1 - x2) + abs(y1 - y2)

    def coordinates(self, index: int) -> tuple[int, int]:
        return index % self.width, index // self.width
