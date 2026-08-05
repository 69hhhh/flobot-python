import type { ConnectionState, GameSnapshot } from '../types/game'

export interface GameDataSource {
  readonly name: string
  connect(): void
  disconnect(): void
  restart?(): Promise<void>
  subscribe(listener: (snapshot: GameSnapshot) => void): () => void
  subscribeConnection(listener: (state: ConnectionState) => void): () => void
}

export abstract class BaseGameDataSource implements GameDataSource {
  abstract readonly name: string
  private snapshotListeners = new Set<(snapshot: GameSnapshot) => void>()
  private connectionListeners = new Set<(state: ConnectionState) => void>()

  abstract connect(): void
  abstract disconnect(): void

  subscribe(listener: (snapshot: GameSnapshot) => void) {
    this.snapshotListeners.add(listener)
    return () => this.snapshotListeners.delete(listener)
  }

  subscribeConnection(listener: (state: ConnectionState) => void) {
    this.connectionListeners.add(listener)
    return () => this.connectionListeners.delete(listener)
  }

  protected emitSnapshot(snapshot: GameSnapshot) {
    this.snapshotListeners.forEach((listener) => listener(snapshot))
  }

  protected emitConnection(state: ConnectionState) {
    this.connectionListeners.forEach((listener) => listener(state))
  }
}
