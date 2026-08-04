"""Python implementation of the Flobot generals.io bot."""

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .agent import FlobotAgent
from .bot import Bot, Move
from .game_map import GameMap, Tile
from .game_state import GameState

__all__ = ["Bot", "FlobotAgent", "GameMap", "GameState", "Move", "Tile"]
__version__ = "7.0.0"
