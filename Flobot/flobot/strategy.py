from __future__ import annotations

import math

from .algorithms import a_star, breadth_first_search, decision_tree_search
from .bot import Bot
from .bot_types import Move
from .constants import (
    GENERAL_DEFENSE_RADIUS,
    GENERAL_MIN_GARRISON,
    INITIAL_WAIT_TURNS,
    MAX_GENERAL_GARRISON,
    OFFENSIVE_SOURCE_LIMIT,
    REINFORCEMENT_INTERVAL,
    RUSH_COLLECT_TURNS,
    SPREADING_TIMES,
    Terrain,
)
from .heuristics import (
    choose_discover_tile,
    choose_enemy_target_by_lowest_army,
    choose_neutral_city_target,
)


def pick_strategy(bot: Bot) -> None:
    turn = bot.game_state.turn
    if _defend_general(bot):
        return
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
            nodes = a_star(
                bot.game_state,
                bot.game_map,
                bot.game_state.own_general,
                [destination],
            )
            bot.queue_moves(
                [Move(start, end) for start, end in zip(nodes, nodes[1:])]
            )
    elif bot.queued_moves == 0:
        depth = math.ceil((INITIAL_WAIT_TURNS + 1) / 4)
        move = decision_tree_search(
            bot.game_state, bot.game_map, bot.game_map.moveable_tiles(bot.game_state), depth
        )
        if move:
            bot.move(move)


def _mid_game(bot: Bot, turn: int) -> None:
    del turn  # Mid-game decisions are driven by the board, not a fixed turn window.
    target = _choose_strategic_target(bot)
    if target is None:
        bot.is_collecting = False
        _spread(bot)
        return

    if _advance_toward_target(bot, target):
        bot.is_collecting = False
        return

    bot.collect_area = _path_from_general(bot, target)
    bot.is_collecting = True
    if bot.queued_moves == 0:
        _collect(bot)


def _spread(bot: Bot) -> None:
    possible: list[dict[str, int | list[int]]] = []
    for index in bot.game_map.moveable_tiles(bot.game_state):
        destinations = [
            tile.index
            for tile in bot.game_map.adjacent_tiles(bot.game_state, index)
            if tile.value == Terrain.EMPTY
            and (
                not bot.game_map.is_city(bot.game_state, tile)
                or bot.game_state.armies[index] - 1 > bot.game_state.armies[tile.index]
            )
        ]
        if destinations:
            possible.append({"index": index, "moves": destinations})

    while possible:
        possible.sort(key=lambda candidate: len(candidate["moves"]), reverse=True)  # type: ignore[arg-type]
        current = possible.pop(0)
        destinations = current["moves"]
        assert isinstance(destinations, list)
        chosen = destinations[0]
        _issue_move(bot, int(current["index"]), chosen)
        for candidate in possible:
            moves = candidate["moves"]
            assert isinstance(moves, list)
            candidate["moves"] = [destination for destination in moves if destination != chosen]
        possible = [candidate for candidate in possible if candidate["moves"]]


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
        _issue_move(bot, source, path[1])


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
        _issue_move(bot, source, destination)


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
        _issue_move(bot, path[0], path[1])


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
        if _move_to_general(bot, bot.game_state.own_general):
            bot.rush_collect_turns_left = -1
    else:
        _move_to_general(bot, bot.last_attacked_index)


def _move_to_general(bot: Bot, start: int) -> bool:
    path = a_star(bot.game_state, bot.game_map, start, [bot.game_state.enemy_general])
    if len(path) > 2:
        return _issue_move(bot, start, path[1])
    else:
        bot.rush_collect_turns_left = RUSH_COLLECT_TURNS
    return False


def _try_to_kill_general(bot: Bot) -> bool:
    enemy_general = bot.game_state.enemy_general
    neighbours = [
        tile.index
        for tile in bot.game_map.adjacent_tiles(bot.game_state, enemy_general)
        if tile.value == bot.game_state.player_index and bot.game_state.armies[tile.index] > 1
    ]
    for index in neighbours:
        next_gain = 1 if bot.game_state.turn % 2 != 0 else 0
        if _available_attack_armies(bot, index) > bot.game_state.armies[enemy_general] + next_gain:
            _issue_move(bot, index, enemy_general)
            bot.is_infiltrating = False
            return True

    if len(neighbours) > 1:
        available = sum(_available_attack_armies(bot, index) for index in neighbours)
        if available > bot.game_state.armies[enemy_general]:
            strongest = max(neighbours, key=bot.game_state.armies.__getitem__)
            _issue_move(bot, strongest, enemy_general, allow_sacrifice=True)
            return True
    return False


def _choose_strategic_target(bot: Bot) -> int | None:
    enemy = choose_enemy_target_by_lowest_army(bot.game_state, bot.game_map)
    if enemy is not None:
        return enemy
    return choose_neutral_city_target(bot.game_state, bot.game_map)


def _path_from_general(bot: Bot, target: int) -> list[int]:
    general = bot.game_state.own_general
    if general < 0:
        return []
    return a_star(bot.game_state, bot.game_map, general, [target])


def _general_reserve(bot: Bot) -> int:
    return min(
        MAX_GENERAL_GARRISON,
        GENERAL_MIN_GARRISON + bot.game_state.turn // 100,
    )


def _available_attack_armies(bot: Bot, source: int) -> int:
    armies = bot.game_state.armies[source]
    if source == bot.game_state.own_general and bot.game_state.turn >= REINFORCEMENT_INTERVAL:
        return armies // 2
    return max(0, armies - 1)


def _issue_move(
    bot: Bot, start: int, end: int, *, allow_sacrifice: bool = False
) -> bool:
    """Issue a move while retaining a scalable garrison on the general."""
    split = False
    if start == bot.game_state.own_general and bot.game_state.turn >= REINFORCEMENT_INTERVAL:
        if bot.game_state.armies[start] // 2 < _general_reserve(bot):
            return False
        split = True
    if (
        not allow_sacrifice
        and bot.game_state.terrain[end] != bot.game_state.player_index
        and _available_attack_armies(bot, start) <= bot.game_state.armies[end]
    ):
        return False
    return bot.move(Move(start, end, split=split))


def _route_resistance(bot: Bot, path: list[int]) -> int:
    resistance = 0
    for index in path[1:]:
        owner = bot.game_state.terrain[index]
        if owner == bot.game_state.player_index:
            continue
        if bot.game_map.is_city(bot.game_state, index) or owner >= 0:
            resistance += bot.game_state.armies[index] + 1
        else:
            resistance += 1
    return resistance


def _advance_toward_target(bot: Bot, target: int) -> bool:
    candidates = [
        index for index, armies in bot.game_state.own_tiles.items() if armies > 1
    ]
    candidates.sort(key=bot.game_state.armies.__getitem__, reverse=True)
    candidates = candidates[:OFFENSIVE_SOURCE_LIMIT]

    plans: list[tuple[tuple[int, int, int], int, list[int]]] = []
    for source in candidates:
        available = _available_attack_armies(bot, source)
        if available <= 0:
            continue
        if source == bot.game_state.own_general and (
            bot.game_state.armies[source] // 2 < _general_reserve(bot)
        ):
            continue
        path = a_star(bot.game_state, bot.game_map, source, [target])
        if len(path) <= 1:
            continue
        general_penalty = _general_reserve(bot) if source == bot.game_state.own_general else 0
        score = (
            available - _route_resistance(bot, path) - general_penalty,
            -len(path),
            available,
        )
        plans.append((score, source, path))

    if not plans:
        return False
    _, source, path = max(plans, key=lambda plan: plan[0])
    destination = path[1]
    destination_owner = bot.game_state.terrain[destination]
    destination_armies = bot.game_state.armies[destination]
    available = _available_attack_armies(bot, source)
    bot.collect_area = path

    if destination_owner == bot.game_state.player_index:
        return _issue_move(bot, source, destination)
    if available <= destination_armies:
        return False

    moved = _issue_move(bot, source, destination)
    if moved and destination == target and destination in bot.game_state.enemy_tiles:
        bot.is_infiltrating = True
    return moved


def _general_threats(bot: Bot) -> list[tuple[int, int, int]]:
    general = bot.game_state.own_general
    if general < 0 or general not in bot.game_state.own_tiles:
        return []
    general_armies = bot.game_state.armies[general]
    threats: list[tuple[int, int, int]] = []
    for index, armies in bot.game_state.enemy_tiles.items():
        distance = bot.game_map.manhattan_distance(general, index)
        if distance > GENERAL_DEFENSE_RADIUS:
            continue
        if distance == 1 or armies >= max(3, general_armies // 2):
            threats.append((distance, -armies, index))
    threats.sort()
    return threats


def general_is_threatened(bot: Bot) -> bool:
    """Allow the agent to cancel stale queued moves before emergency defense."""
    return bool(_general_threats(bot))


def _defend_general(bot: Bot) -> bool:
    """Intercept credible visible threats and otherwise hold the general in place."""
    general = bot.game_state.own_general
    threats = _general_threats(bot)
    if not threats:
        return False

    # Prefer eliminating a threat with a non-general tile so the general stays covered.
    for _, _, threat in threats:
        attackers = [
            tile.index
            for tile in bot.game_map.adjacent_tiles(bot.game_state, threat)
            if tile.value == bot.game_state.player_index
            and tile.index != general
            and _available_attack_armies(bot, tile.index)
            > bot.game_state.armies[threat]
        ]
        if attackers:
            strongest = max(attackers, key=bot.game_state.armies.__getitem__)
            return _issue_move(bot, strongest, threat)

    reinforcements: list[tuple[int, int, int, list[int]]] = []
    for source, armies in bot.game_state.own_tiles.items():
        if source == general or armies <= 1:
            continue
        path = a_star(bot.game_state, bot.game_map, source, [general])
        if 1 < len(path) <= GENERAL_DEFENSE_RADIUS + 2:
            reinforcements.append((len(path), -armies, source, path))
    if reinforcements:
        _, _, source, path = min(reinforcements)
        return _issue_move(bot, source, path[1])

    # A split counterattack is safe only when the retained half meets the reserve.
    adjacent = [threat for distance, _, threat in threats if distance == 1]
    if adjacent:
        weakest = min(adjacent, key=bot.game_state.armies.__getitem__)
        if _available_attack_armies(bot, general) > bot.game_state.armies[weakest]:
            return _issue_move(bot, general, weakest)

    # Returning true deliberately suppresses offensive moves for this turn.
    return True
