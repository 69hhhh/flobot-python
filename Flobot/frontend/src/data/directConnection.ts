export interface DirectConnectionConfig {
  roomUrl: string
  userId: string
}

export interface ParsedDirectConnection extends DirectConnectionConfig {
  roomId: string
}

const OFFICIAL_HOSTS = new Set(['generals.io', 'www.generals.io', 'bot.generals.io'])

export function parseDirectConnection(config: DirectConnectionConfig): ParsedDirectConnection {
  let url: URL
  try {
    url = new URL(config.roomUrl.trim())
  } catch {
    throw new Error('请输入完整房间网址，例如 https://generals.io/games/房间ID')
  }

  if (!OFFICIAL_HOSTS.has(url.hostname.toLowerCase()) || url.protocol !== 'https:') {
    throw new Error('出于 user_id 安全考虑，只允许 generals.io 官方 HTTPS 房间网址')
  }

  const pathParts = url.pathname.split('/').filter(Boolean)
  const gamesIndex = pathParts.indexOf('games')
  const roomId = gamesIndex >= 0 ? pathParts[gamesIndex + 1] : undefined
  if (!roomId) {
    throw new Error('网址中没有找到房间 ID，请使用 /games/房间ID 格式')
  }

  const userId = config.userId.trim()
  if (!userId) {
    throw new Error('请输入 user_id')
  }

  return {
    ...config,
    roomUrl: url.toString(),
    roomId: decodeURIComponent(roomId),
    userId,
  }
}
