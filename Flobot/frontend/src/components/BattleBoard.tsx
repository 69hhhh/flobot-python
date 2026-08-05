import type { GameSnapshot, TileState } from '../types/game'

interface BattleBoardProps {
  snapshot: GameSnapshot
}

const tileSymbol = (tile: TileState) => {
  if (tile.kind === 'mountain' || tile.kind === 'fog-obstacle') return '▲'
  if (tile.kind === 'general') return '★'
  if (tile.kind === 'city') return '◆'
  return ''
}

const tileName = (tile: TileState) => {
  if (!tile.discovered) return tile.kind === 'fog-obstacle' ? '迷雾中的障碍' : '未探索区域'
  if (tile.kind === 'mountain') return '山脉'
  if (tile.kind === 'general') return '将军'
  if (tile.kind === 'city') return '城市'
  return '平原'
}

export function BattleBoard({ snapshot }: BattleBoardProps) {
  const playerColors = new Map(snapshot.players.map((player) => [player.id, player.color]))
  const movingFrom = snapshot.lastMove?.from
  const movingTo = snapshot.lastMove?.to

  return (
    <div
      className="battle-board"
      style={{ '--board-columns': snapshot.width } as React.CSSProperties}
      role="grid"
      aria-label={`当前战场，共 ${snapshot.width} 列 ${snapshot.height} 行`}
    >
      {snapshot.tiles.map((tile) => {
        const ownerColor = tile.ownerId === null ? undefined : playerColors.get(tile.ownerId)
        const isMovingFrom = tile.index === movingFrom
        const isMovingTo = tile.index === movingTo
        return (
          <div
            className={`tile tile--${tile.kind}${isMovingFrom ? ' tile--moving-from' : ''}${isMovingTo ? ' tile--moving-to' : ''}`}
            style={{ '--owner-color': ownerColor ?? '#27313d' } as React.CSSProperties}
            key={tile.index}
            role="gridcell"
            title={`${tileName(tile)}${tile.army ? ` · ${tile.army} 兵力` : ''}`}
            aria-label={`第 ${tile.row + 1} 行第 ${tile.column + 1} 列，${tileName(tile)}${tile.army ? `，${tile.army} 兵力` : ''}`}
          >
            <span className="tile__symbol" aria-hidden="true">{tileSymbol(tile)}</span>
            {tile.discovered && tile.kind !== 'mountain' && tile.army > 0 && (
              <span className="tile__army">{tile.army}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
