import { useEffect, useState } from 'react'
import type { GameDataSource } from '../data/GameDataSource'
import type { ConnectionState, GameSnapshot } from '../types/game'

export const useGameStream = (source: GameDataSource | null) => {
  const [snapshot, setSnapshot] = useState<GameSnapshot | null>(null)
  const [connection, setConnection] = useState<ConnectionState>('connecting')

  useEffect(() => {
    setSnapshot(null)
    setConnection('connecting')
    if (!source) return
    const unsubscribeSnapshot = source.subscribe(setSnapshot)
    const unsubscribeConnection = source.subscribeConnection(setConnection)
    source.connect()
    return () => {
      unsubscribeSnapshot()
      unsubscribeConnection()
      source.disconnect()
    }
  }, [source])

  return { snapshot, connection }
}
