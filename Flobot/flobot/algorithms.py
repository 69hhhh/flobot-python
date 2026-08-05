from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass
from math import inf

from .bot_types import Move
from .constants import Terrain
from .game_map import GameMap
from .game_state import GameState
from .heuristics import capture_weight


@dataclass(frozen=True)
class ReachableTile:
    index: int
    general_distance: int


def breadth_first_search(
    state: GameState, game_map: GameMap, start: int, radius: int
) -> list[ReachableTile]:
    visited = {start}
    queue = deque([(start, 0)])
    found: list[ReachableTile] = []
    while queue:
        current, distance = queue.popleft()
        if distance:
            found.append(ReachableTile(current, distance))
        if distance >= radius:
            continue
        for tile in game_map.adjacent_tiles(state, current):
            if tile.index not in visited and game_map.is_walkable(state, tile):
                visited.add(tile.index)
                queue.append((tile.index, distance + 1))
    return found


def shortest_path(state: GameState, game_map: GameMap, start: int, end: int) -> list[Move]:
    if start == end:
        return []
    previous: dict[int, int | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for tile in game_map.adjacent_tiles(state, current):
            if tile.index in previous or not game_map.is_walkable(state, tile):
                continue
            previous[tile.index] = current
            if tile.index == end:
                nodes = _reconstruct_nodes(previous, end)
                return [Move(first, second) for first, second in zip(nodes, nodes[1:])]
            queue.append(tile.index)
    return []


def a_star(
    state: GameState, game_map: GameMap, start: int, ends: list[int] | set[int]
) -> list[int]:
    targets = set(ends)
    if not targets or not 0 <= start < game_map.size:
        return []
    if start in targets:
        return [start]

    def heuristic(index: int) -> int:
        return min(game_map.manhattan_distance(index, target) for target in targets)

    sequence = 0
    queue: list[tuple[int, int, int, int]] = [(heuristic(start), -state.armies[start], sequence, start)]
    costs = {start: 0}
    previous: dict[int, int | None] = {start: None}
    closed: set[int] = set()

    while queue:
        _, _, _, current = heapq.heappop(queue)
        if current in closed:
            continue
        if current in targets:
            return _reconstruct_nodes(previous, current)
        closed.add(current)

        for tile in game_map.adjacent_tiles(state, current):
            if tile.index in closed or not game_map.is_walkable(state, tile):
                continue
            step_cost = 1
            if game_map.is_city(state, tile) and tile.value != state.player_index:
                step_cost += state.armies[tile.index]
            elif tile.value >= 0 and tile.value != state.player_index:
                step_cost += state.armies[tile.index]
            elif tile.value == Terrain.EMPTY:
                step_cost += 1
            new_cost = costs[current] + step_cost
            if new_cost < costs.get(tile.index, inf):
                costs[tile.index] = new_cost
                previous[tile.index] = current
                sequence += 1
                heapq.heappush(
                    queue,
                    (new_cost + heuristic(tile.index), -state.armies[tile.index], sequence, tile.index),
                )
    return []


def _reconstruct_nodes(previous: dict[int, int | None], end: int) -> list[int]:
    nodes = [end]
    while previous[nodes[-1]] is not None:
        nodes.append(previous[nodes[-1]])  # type: ignore[arg-type]
    nodes.reverse()
    return nodes


def decision_tree_search(
    state: GameState, game_map: GameMap, starts: list[int], turns: int
) -> Move | None:
    if not starts:
        return None

    def search(current: int, remaining: int, weight: int = 0) -> Move:
        if remaining == 0:
            return Move(current, -1, weight)
        possibilities = [
            search(tile.index, remaining - 1, capture_weight(game_map.player_index, tile.value))
            for tile in game_map.adjacent_tiles(state, current)
            if game_map.is_walkable(state, tile)
        ]
        possibilities.append(search(current, remaining - 1))
        best = max(possibilities, key=lambda move: move.weight)
        return Move(current, best.start, weight + best.weight)

    return max((search(start, turns) for start in starts), key=lambda move: move.weight)
