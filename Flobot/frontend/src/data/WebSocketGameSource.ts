import { BaseGameDataSource } from './GameDataSource'
import type { GameSnapshot } from '../types/game'

interface SnapshotMessage {
  type: 'snapshot'
  payload: GameSnapshot
}

export class WebSocketGameSource extends BaseGameDataSource {
  readonly name = '实时对局'
  private socket: WebSocket | null = null
  private retryTimer: number | null = null
  private shouldReconnect = false

  constructor(private readonly url: string) {
    super()
  }

  connect() {
    if (this.socket?.readyState === WebSocket.OPEN) return
    this.shouldReconnect = true
    this.emitConnection('connecting')
    this.socket = new WebSocket(this.url)
    this.socket.addEventListener('open', () => this.emitConnection('connected'))
    this.socket.addEventListener('message', (event) => {
      try {
        const message = JSON.parse(event.data) as SnapshotMessage
        if (message.type === 'snapshot') this.emitSnapshot(message.payload)
      } catch {
        this.emitConnection('error')
      }
    })
    this.socket.addEventListener('close', () => {
      this.emitConnection('disconnected')
      if (this.shouldReconnect) {
        this.retryTimer = window.setTimeout(() => this.connect(), 2000)
      }
    })
    this.socket.addEventListener('error', () => this.emitConnection('error'))
  }

  disconnect() {
    this.shouldReconnect = false
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer)
    this.retryTimer = null
    this.socket?.close()
    this.socket = null
  }
}
