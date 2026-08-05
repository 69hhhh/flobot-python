import { BaseGameDataSource } from './GameDataSource'
import type { ParsedDirectConnection } from './directConnection'
import type { GameSnapshot } from '../types/game'

interface SnapshotMessage {
  type: 'snapshot'
  payload: GameSnapshot
}

const getApiBase = () => {
  const configured = import.meta.env.VITE_BOT_API_URL
  if (configured) return configured.replace(/\/$/, '')
  return import.meta.env.DEV ? 'http://127.0.0.1:8765' : window.location.origin
}

export class ManagedBotGameSource extends BaseGameDataSource {
  readonly name = '原版 Python Flobot'
  private readonly apiBase = getApiBase()
  private socket: WebSocket | null = null
  private request: AbortController | null = null
  private active = false
  private retryTimer: number | null = null
  private statusTimer: number | null = null

  constructor(private readonly config: ParsedDirectConnection) {
    super()
  }

  connect() {
    if (this.active) return
    this.active = true
    this.emitConnection('connecting')
    window.addEventListener('beforeunload', this.stopOnUnload)
    this.request = new AbortController()
    void fetch(`${this.apiBase}/api/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roomUrl: this.config.roomUrl, userId: this.config.userId }),
      signal: this.request.signal,
    }).then(async (response) => {
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { error?: string }
        throw new Error(payload.error || '无法启动机器人')
      }
      if (this.active) {
        this.openSocket()
        void this.pollSessionStatus()
      }
    }).catch((error) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        this.emitConnection('error')
      }
    }).finally(() => {
      this.request = null
    })
  }

  disconnect() {
    this.active = false
    window.removeEventListener('beforeunload', this.stopOnUnload)
    this.request?.abort()
    this.request = null
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer)
    this.retryTimer = null
    if (this.statusTimer !== null) window.clearTimeout(this.statusTimer)
    this.statusTimer = null
    this.socket?.close()
    this.socket = null
    void this.stopSession()
  }

  private openSocket() {
    const websocketBase = this.apiBase.replace(/^http/, 'ws')
    const socket = new WebSocket(`${websocketBase}/ws`)
    this.socket = socket
    socket.addEventListener('open', () => this.emitConnection('connected'))
    socket.addEventListener('message', (event) => {
      try {
        const message = JSON.parse(event.data) as SnapshotMessage
        if (message.type === 'snapshot') this.emitSnapshot(message.payload)
      } catch {
        this.emitConnection('error')
      }
    })
    socket.addEventListener('error', () => this.emitConnection('error'))
    socket.addEventListener('close', () => {
      this.socket = null
      if (this.active) {
        this.emitConnection('disconnected')
        this.retryTimer = window.setTimeout(() => this.openSocket(), 1500)
      }
    })
  }

  private stopSession() {
    return fetch(`${this.apiBase}/api/session/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      keepalive: true,
    }).catch(() => undefined)
  }

  private async pollSessionStatus() {
    if (!this.active) return
    try {
      const response = await fetch(`${this.apiBase}/api/session`, { cache: 'no-store' })
      if (response.ok) {
        const status = await response.json() as { state?: string }
        if (status.state === 'error') this.emitConnection('error')
        else if (status.state === 'idle') this.emitConnection('disconnected')
      }
    } catch {
      this.emitConnection('error')
    } finally {
      if (this.active) {
        this.statusTimer = window.setTimeout(() => void this.pollSessionStatus(), 1000)
      }
    }
  }

  private readonly stopOnUnload = () => {
    const body = new Blob(['{}'], { type: 'application/json' })
    navigator.sendBeacon(`${this.apiBase}/api/session/stop`, body)
  }
}
