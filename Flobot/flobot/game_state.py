from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .patcher import patch


@dataclass
class GameState:
    data: dict[str, Any]
    player_index: int
    cities: list[int] = field(default_factory=list, init=False)
    raw_map: list[int] = field(default_factory=list, init=False)
    discovered_tiles: list[bool] = field(default_factory=list, init=False)
    own_tiles: dict[int, int] = field(default_factory=dict, init=False)
    enemy_tiles: dict[int, int] = field(default_factory=dict, init=False)
    own_general: int = field(default=-1, init=False)
    enemy_general: int = field(default=-1, init=False)
    generals: list[int] = field(default_factory=list, init=False)
    armies: list[int] = field(default_factory=list, init=False)
    terrain: list[int] = field(default_factory=list, init=False)
    width: int = field(default=0, init=False)
    height: int = field(default=0, init=False)
    size: int = field(default=0, init=False)
    turn: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        initial_map = patch([], self.data["map_diff"])
        if len(initial_map) < 2:
            raise ValueError("map_diff did not contain map dimensions")
        self.discovered_tiles = [False] * (initial_map[0] * initial_map[1])
        self.update(self.data)

    def update(self, data: dict[str, Any]) -> None:
        self.cities = patch(self.cities, data["cities_diff"])
        self.raw_map = patch(self.raw_map, data["map_diff"])
        self.generals = list(data.get("generals", []))
        self.turn = int(data["turn"])

        self.width, self.height = self.raw_map[:2]
        self.size = self.width * self.height
        expected = 2 + self.size * 2
        if len(self.raw_map) != expected:
            raise ValueError(f"invalid map length: expected {expected}, got {len(self.raw_map)}")
        self.armies = self.raw_map[2 : self.size + 2]
        self.terrain = self.raw_map[self.size + 2 : expected]
        self._update_player_tiles()
        self._update_discovered_tiles()
        self._update_generals()

    def _update_player_tiles(self) -> None:
        self.own_tiles.clear()
        self.enemy_tiles.clear()
        for index, owner in enumerate(self.terrain):
            if owner == self.player_index:
                self.own_tiles[index] = self.armies[index]
            elif owner >= 0:
                self.enemy_tiles[index] = self.armies[index]

    def _update_discovered_tiles(self) -> None:
        for index in self.own_tiles.keys() | self.enemy_tiles.keys():
            self.discovered_tiles[index] = True

    def _update_generals(self) -> None:
        if self.player_index < len(self.generals) and self.generals[self.player_index] != -1:
            self.own_general = self.generals[self.player_index]
        visible_enemies = [
            general
            for index, general in enumerate(self.generals)
            if index != self.player_index and general != -1
        ]
        self.enemy_general = visible_enemies[0] if visible_enemies else -1
