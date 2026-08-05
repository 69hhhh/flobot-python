import type { GameDataSource } from './GameDataSource'
import { ManagedBotGameSource } from './ManagedBotGameSource'
import { MockGameSource } from './MockGameSource'
import { PollingGameSource } from './PollingGameSource'
import { WebSocketGameSource } from './WebSocketGameSource'
import type { ParsedDirectConnection } from './directConnection'

export type DataMode = 'direct' | 'mock' | 'websocket' | 'polling'

export const createGameSource = (
  mode: DataMode,
  directConfig: ParsedDirectConnection | null = null,
): GameDataSource | null => {
  if (mode === 'direct') {
    return directConfig ? new ManagedBotGameSource(directConfig) : null
  }
  if (mode === 'websocket') {
    return new WebSocketGameSource(import.meta.env.VITE_GAME_WS_URL ?? 'ws://127.0.0.1:8765/ws')
  }
  if (mode === 'polling') {
    const configuredInterval = Number(import.meta.env.VITE_GAME_POLL_INTERVAL ?? 1000)
    const interval = Number.isFinite(configuredInterval) ? Math.max(250, configuredInterval) : 1000
    return new PollingGameSource(
      import.meta.env.VITE_GAME_POLL_URL ?? 'http://127.0.0.1:8765/api/snapshot',
      interval,
    )
  }
  return new MockGameSource()
}
