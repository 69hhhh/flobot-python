import { BaseGameDataSource } from './GameDataSource'
import type { GameSnapshot } from '../types/game'

export class PollingGameSource extends BaseGameDataSource {
  readonly name = 'HTTP 轮询'
  private timer: number | null = null
  private controller: AbortController | null = null
  private running = false

  constructor(
    private readonly url: string,
    private readonly intervalMs = 1000,
  ) {
    super()
  }

  connect() {
    if (this.running) return
    this.running = true
    this.emitConnection('connecting')
    void this.poll()
  }

  disconnect() {
    this.running = false
    if (this.timer !== null) window.clearTimeout(this.timer)
    this.timer = null
    this.controller?.abort()
    this.controller = null
  }

  private async poll() {
    if (!this.running) return
    this.controller = new AbortController()
    try {
      const response = await fetch(this.url, {
        cache: 'no-store',
        signal: this.controller.signal,
      })
      if (response.status === 204) {
        this.emitConnection('connected')
      } else if (response.ok) {
        const snapshot = await response.json() as GameSnapshot
        this.emitSnapshot(snapshot)
        this.emitConnection('connected')
      } else {
        this.emitConnection('error')
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        this.emitConnection('error')
      }
    } finally {
      this.controller = null
      if (this.running) {
        this.timer = window.setTimeout(() => void this.poll(), this.intervalMs)
      }
    }
  }
}
