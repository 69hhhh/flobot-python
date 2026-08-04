from __future__ import annotations

import math

from .algorithms import a_star, breadth_first_search, decision_tree_search, shortest_path
from .bot import Bot
from .bot_types import Move
from .constants import (
    ATTACK_TURNS_BEFORE_REINFORCEMENTS,
    INITIAL_WAIT_TURNS,
    REINFORCEMENT_INTERVAL,
    RUSH_COLLECT_TURNS,
    SPREADING_TIMES,
    Terrain,
)
from .heuristics import choose_discover_tile, choose_enemy_target_by_lowest_army


def pick_strategy(bot: Bot) -> None:
    turn = bot.game_state.turn
    if bot.game_state.enemy_general != -1:
        _end_game(bot)
    elif bot.is_infiltrating:
        _infiltrate(bot)
    elif turn % REINFORCEMENT_INTERVAL == 0 and (
        turn // REINFORCEMENT_INTERVAL <= SPREADING_TIMES or not bot.game_state.enemy_tiles
    ):
        _spread(bot)
    elif turn < REINFORCEMENT_INTERVAL:
        _early_game(bot, turn)
    else:
        _mid_game(bot, turn)


def _early_game(bot: Bot, turn: int) -> None:
    if turn <= INITIAL_WAIT_TURNS:
        return
    if turn == INITIAL_WAIT_TURNS + 1:
        radius = (INITIAL_WAIT_TURNS + 1) // 2 + 1
        reachable = breadth_first_search(
            bot.game_state, bot.game_map, bot.game_state.own_general, radius
        )
        destination = choose_discover_tile(bot.game_map, reachable)
        if destination is not None:
            bot.queue_moves(
                shortest_path(
                    bot.game_state, bot.game_map, bot.game_state.own_general, destination
                )
            )
    elif bot.queued_moves == 0:
        depth = math.ceil((INITIAL_WAIT_TURNS + 1) / 4)
        move = decision_tree_search(
            bot.game_state, bot.game_map, bot.game_map.moveable_tiles(bot.game_state), depth
        )
        if move:
            bot.move(move)


def _mid_game(bot: Bot, turn: int) -> None:
    should_advance = (
        bool(bot.game_state.enemy_tiles)
        and len(bot.collect_area) > 1
        and (
            turn + ATTACK_TURNS_BEFORE_REINFORCEMENTS + len(bot.collect_area) - 1
        )
        % REINFORCEMENT_INTERVAL
        == 0
    )
    if should_advance:
        if len(bot.collect_area) == 2:
            bot.is_infiltrating = True
        start = bot.collect_area.pop(0)
        bot.move(Move(start, bot.collect_area[0]))
    elif not bot.is_infiltrating:
        bot.collect_area = _get_collect_area(bot)
        if bot.queued_moves == 0:
            _collect(bot)


def _spread(bot: Bot) -> None:
    possible: list[dict[str, int | list[int]]] = []
    for index in bot.game_map.moveable_tiles(bot.game_state):
        destinations = [
            tile.index
            for tile in bot.game_map.adjacent_tiles(bot.game_state, index)
            if tile.value == Terrain.EMPTY and not bot.game_map.is_city(bot.game_state, tile)
        ]
        if destinations:
            possible.append({"index": index, "moves": destinations})

    while possible:
        possible.sort(key=lambda candidate: len(candidate["moves"]), reverse=True)  # type: ignore[arg-type]
        current = possible.pop(0)
        destinations = current["moves"]
        assert isinstance(destinations, list)
        chosen = destinations[0]
        bot.move(Move(int(current["index"]), chosen))
        for candidate in possible:
            moves = candidate["moves"]
            assert isinstance(moves, list)
            candidate["moves"] = [destination for destination in moves if destination != chosen]
        possible = [candidate for candidate in possible if candidate["moves"]]


def _get_collect_area(bot: Bot) -> list[int]:
    bot.is_collecting = True
    target = choose_enemy_target_by_lowest_army(bot.game_state, bot.game_map)
    if target is not None:
        path = a_star(bot.game_state, bot.game_map, bot.game_state.own_general, [target])
        if path:
            return path
    return [bot.game_state.own_general]


def _collect(bot: Bot) -> None:
    excluded = set(bot.collect_area)
    candidates = [
        (armies, index)
        for index, armies in bot.game_state.own_tiles.items()
        if armies > 1 and index not in excluded
    ]
    if not candidates:
        bot.is_collecting = False
        return
    _, source = max(candidates)
    path = a_star(bot.game_state, bot.game_map, source, bot.collect_area)
    if len(path) > 1:
        bot.move(Move(source, path[1]))


def _infiltrate(bot: Bot) -> None:
    source = bot.last_attacked_index
    if source == -1 or bot.game_state.terrain[source] != bot.game_state.player_index:
        bot.is_infiltrating = False
        return

    adjacent_targets = [
        tile.index
        for tile in bot.game_map.adjacent_tiles(bot.game_state, source)
        if bot.game_map.is_enemy(bot.game_state, tile.index)
        and bot.game_map.is_walkable(bot.game_state, tile)
        and bot.game_map.is_adjacent_to_fog(bot.game_state, tile.index)
    ]
    if adjacent_targets:
        destination = min(adjacent_targets, key=bot.game_state.armies.__getitem__)
    else:
        targets = [
            index
            for index in bot.game_state.enemy_tiles
            if bot.game_map.is_adjacent_to_fog(bot.game_state, index)
        ]
        path = a_star(bot.game_state, bot.game_map, source, targets)
        destination = path[1] if len(path) > 1 else -1

    remaining = bot.game_map.remaining_armies_after_attack(
        bot.game_state, source, destination
    )
    if destination == -1 or remaining <= 1:
        bot.is_infiltrating = False
    if destination != -1 and remaining >= 1:
        bot.move(Move(source, destination))


def _end_game(bot: Bot) -> None:
    if not bot.is_infiltrating:
        _rush(bot)
        return
    if _try_to_kill_general(bot):
        return
    path = a_star(
        bot.game_state,
        bot.game_map,
        bot.last_attacked_index,
        [bot.game_state.enemy_general],
    )
    if len(path) <= 2 or (
        len(path) > 1
        and bot.game_map.remaining_armies_after_attack(bot.game_state, path[0], path[1]) <= 1
    ):
        bot.is_infiltrating = False
    if len(path) > 2:
        bot.move(Move(path[0], path[1]))


def _rush(bot: Bot) -> None:
    if _try_to_kill_general(bot):
        return
    if bot.rush_collect_turns_left > 0:
        bot.collect_area = a_star(
            bot.game_state,
            bot.game_map,
            bot.game_state.own_general,
            [bot.game_state.enemy_general],
        )
        if bot.collect_area:
            bot.collect_area.pop()
        _collect(bot)
        bot.rush_collect_turns_left -= 1
    elif bot.rush_collect_turns_left == 0:
        _move_to_general(bot, bot.game_state.own_general)
        bot.rush_collect_turns_left = -1
    else:
        _move_to_general(bot, bot.last_attacked_index)


def _move_to_general(bot: Bot, start: int) -> None:
    path = a_star(bot.game_state, bot.game_map, start, [bot.game_state.enemy_general])
    if len(path) > 2:
        bot.move(Move(start, path[1]))
    else:
        bot.rush_collect_turns_left = RUSH_COLLECT_TURNS


def _try_to_kill_general(bot: Bot) -> bool:
    enemy_general = bot.game_state.enemy_general
    neighbours = [
        tile.index
        for tile in bot.game_map.adjacent_tiles(bot.game_state, enemy_general)
        if tile.value == bot.game_state.player_index and bot.game_state.armies[tile.index] > 1
    ]
    for index in neighbours:
        next_gain = 1 if bot.game_state.turn % 2 != 0 else 0
        if bot.game_state.armies[index] - 1 > bot.game_state.armies[enemy_general] + next_gain:
            bot.move(Move(index, enemy_general))
            bot.is_infiltrating = False
            return True

    if len(neighbours) > 1:
        available = sum(bot.game_state.armies[index] - 1 for index in neighbours)
        if available > bot.game_state.armies[enemy_general]:
            strongest = max(neighbours, key=bot.game_state.armies.__getitem__)
            bot.move(Move(strongest, enemy_general))
            return True
    return False
