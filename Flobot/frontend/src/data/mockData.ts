import type { GameSnapshot, PlayerState, TileKind, TileState } from '../types/game'

const WIDTH = 16
const HEIGHT = 11

const seededNoise = (index: number) => {
  const value = Math.sin(index * 12.9898 + 78.233) * 43758.5453
  return value - Math.floor(value)
}

const distance = (a: number, b: number) => {
  const ax = a % WIDTH
  const ay = Math.floor(a / WIDTH)
  const bx = b % WIDTH
  const by = Math.floor(b / WIDTH)
  return Math.abs(ax - bx) + Math.abs(ay - by)
}

const playerSeeds = [17, 30, 145, 158]

const initialPlayers: PlayerState[] = [
  { id: 0, name: 'Flobot', color: '#4f9cff', army: 0, land: 0, alive: true },
  { id: 1, name: '红隼', color: '#ff5d73', army: 0, land: 0, alive: true },
  { id: 2, name: '苔原', color: '#38d39f', army: 0, land: 0, alive: true },
  { id: 3, name: '琥珀', color: '#f4b84a', army: 0, land: 0, alive: true },
]

const makeTile = (index: number): TileState => {
  const row = Math.floor(index / WIDTH)
  const column = index % WIDTH
  const noise = seededNoise(index)
  let kind: TileKind = 'plain'
  let ownerId: number | null = null
  let army = 0

  if (noise > 0.88) {
    kind = 'mountain'
  } else if (noise > 0.82) {
    kind = 'city'
    army = 38 + Math.floor(seededNoise(index + 7) * 14)
  }

  const closestSeed = playerSeeds
    .map((seed, playerId) => ({ seed, playerId, distance: distance(index, seed) }))
    .sort((a, b) => a.distance - b.distance)[0]

  if (closestSeed.distance <= 2 && kind !== 'mountain') {
    ownerId = closestSeed.playerId
    army = index === closestSeed.seed ? 34 : 4 + Math.floor(seededNoise(index + 21) * 13)
  }

  if (playerSeeds.includes(index)) {
    kind = 'general'
  }

  const observerDistance = distance(index, playerSeeds[0])
  const discovered = observerDistance <= 6 || ownerId === 0
  if (!discovered) {
    kind = kind === 'mountain' ? 'fog-obstacle' : 'fog'
  }

  return { index, row, column, kind, ownerId, army, discovered }
}

export const createInitialSnapshot = (): GameSnapshot => ({
  gameId: '训练局 · ALPHA-07',
  turn: 84,
  width: WIDTH,
  height: HEIGHT,
  status: 'playing',
  elapsedSeconds: 168,
  observerPlayerId: 0,
  players: initialPlayers.map((player) => ({ ...player })),
  tiles: Array.from({ length: WIDTH * HEIGHT }, (_, index) => makeTile(index)),
  lastMove: null,
  recentMoves: [],
  updatedAt: Date.now(),
})
