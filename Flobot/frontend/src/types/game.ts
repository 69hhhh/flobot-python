export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export type TileKind = 'plain' | 'mountain' | 'city' | 'general' | 'fog' | 'fog-obstacle'

export interface PlayerState {
  id: number
  name: string
  color: string
  army: number
  land: number
  alive: boolean
}

export interface TileState {
  index: number
  row: number
  column: number
  kind: TileKind
  ownerId: number | null
  army: number
  discovered: boolean
}

export interface MoveRecord {
  id: string
  turn: number
  playerId: number
  from: number
  to: number
  description: string
}

export interface GameSnapshot {
  gameId: string
  turn: number
  width: number
  height: number
  status: 'waiting' | 'playing' | 'finished'
  elapsedSeconds: number
  observerPlayerId: number
  players: PlayerState[]
  tiles: TileState[]
  lastMove: MoveRecord | null
  recentMoves: MoveRecord[]
  updatedAt: number
}
