/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GAME_WS_URL?: string
  readonly VITE_GAME_POLL_URL?: string
  readonly VITE_GAME_POLL_INTERVAL?: string
  readonly VITE_GAME_TRANSPORT?: 'direct' | 'mock' | 'websocket' | 'polling'
  readonly VITE_BOT_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
