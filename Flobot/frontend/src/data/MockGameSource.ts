import { BaseGameDataSource } from './GameDataSource'
import { createInitialSnapshot } from './mockData'
import type { GameSnapshot, MoveRecord, PlayerState, TileState } from '../types/game'

const DIRECTIONS = [-1, 1, -16, 16]

const isAdjacent = (from: TileState, to: TileState, width: number) => {
  const rowGap = Math.abs(from.row - to.row)
  const columnGap = Math.abs(from.column - to.column)
  return rowGap + columnGap === 1 && Math.abs(from.index - to.index) <= width
}

const recalculatePlayers = (players: PlayerState[], tiles: TileState[]) =>
  players.map((player) => {
    const owned = tiles.filter((tile) => tile.ownerId === player.id)
    return {
      ...player,
      land: owned.length,
      army: owned.reduce((total, tile) => total + tile.army, 0),
      alive: owned.length > 0,
    }
  })

export class MockGameSource extends BaseGameDataSource {
  readonly name = '演练数据'
  private snapshot: GameSnapshot = createInitialSnapshot()
  private timer: number | null = null
  private connectTimer: number | null = null
  private cursor = 0

  connect() {
    if (this.timer !== null) return
    this.emitConnection('connecting')
    this.snapshot = {
      ...this.snapshot,
      players: recalculatePlayers(this.snapshot.players, this.snapshot.tiles),
      updatedAt: Date.now(),
    }

    this.connectTimer = window.setTimeout(() => {
      this.emitConnection('connected')
      this.emitSnapshot(this.snapshot)
      this.connectTimer = null
    }, 280)

    this.timer = window.setInterval(() => this.advance(), 1100)
  }

  disconnect() {
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }
    if (this.connectTimer !== null) {
      window.clearTimeout(this.connectTimer)
      this.connectTimer = null
    }
    this.emitConnection('disconnected')
  }

  private advance() {
    const playerId = this.cursor % this.snapshot.players.length
    const tiles = this.snapshot.tiles.map((tile) => ({ ...tile }))
    const candidates = tiles.filter((tile) => tile.ownerId === playerId && tile.army > 2)
    const from = candidates[(this.cursor * 7) % Math.max(candidates.length, 1)]

    if (!from) {
      this.cursor += 1
      return
    }

    const neighbors = DIRECTIONS
      .map((offset) => tiles[from.index + offset])
      .filter((tile): tile is TileState => Boolean(tile))
      .filter((tile) => isAdjacent(from, tile, this.snapshot.width))
      .filter((tile) => tile.kind !== 'mountain' && tile.kind !== 'fog-obstacle')

    const preferred = neighbors.find((tile) => tile.ownerId !== playerId) ?? neighbors[0]
    if (!preferred) return

    const wasOwnTile = preferred.ownerId === playerId
    const force = Math.max(1, from.army - 1)
    from.army = 1
    if (preferred.ownerId === playerId) {
      preferred.army += force
    } else if (force > preferred.army) {
      preferred.ownerId = playerId
      preferred.army = force - preferred.army
      if (playerId === this.snapshot.observerPlayerId) {
        preferred.discovered = true
        if (preferred.kind === 'fog') preferred.kind = 'plain'
      }
    } else {
      preferred.army -= force
    }

    tiles.forEach((tile) => {
      if (tile.ownerId !== null && tile.kind !== 'mountain') {
        tile.army += tile.kind === 'city' || tile.kind === 'general' ? 1 : this.cursor % 4 === 0 ? 1 : 0
      }
      if (tile.ownerId === 0) tile.discovered = true
    })

    const turn = this.snapshot.turn + 1
    const move: MoveRecord = {
      id: `${turn}-${playerId}`,
      turn,
      playerId,
      from: from.index,
      to: preferred.index,
      description: wasOwnTile ? '部队调动' : '向边境推进',
    }

    this.snapshot = {
      ...this.snapshot,
      turn,
      elapsedSeconds: this.snapshot.elapsedSeconds + 2,
      tiles,
      players: recalculatePlayers(this.snapshot.players, tiles),
      lastMove: move,
      recentMoves: [move, ...this.snapshot.recentMoves].slice(0, 5),
      updatedAt: Date.now(),
    }
    this.cursor += 1
    this.emitSnapshot(this.snapshot)
  }
}
