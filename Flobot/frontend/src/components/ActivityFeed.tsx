import type { GameSnapshot } from '../types/game'

interface ActivityFeedProps {
  snapshot: GameSnapshot
}

export function ActivityFeed({ snapshot }: ActivityFeedProps) {
  return (
    <section className="panel activity" aria-labelledby="activity-title">
      <div className="panel__heading">
        <div>
          <span className="eyebrow">行动记录</span>
          <h2 id="activity-title">前线动态</h2>
        </div>
      </div>
      <div className="activity-list" aria-live="polite">
        {snapshot.recentMoves.length === 0 ? (
          <p className="activity__empty">正在等待第一条行动数据…</p>
        ) : snapshot.recentMoves.map((move) => {
          const player = snapshot.players.find((item) => item.id === move.playerId)
          return (
            <div className="activity-item" key={move.id}>
              <span className="activity-item__dot" style={{ background: player?.color }} />
              <div>
                <strong>{player?.name}</strong>
                <p>{move.description} · {move.from} → {move.to}</p>
              </div>
              <time>T{move.turn}</time>
            </div>
          )
        })}
      </div>
    </section>
  )
}
