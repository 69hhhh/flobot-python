import type { GameSnapshot } from '../types/game'

interface ScoreboardProps {
  snapshot: GameSnapshot
}

export function Scoreboard({ snapshot }: ScoreboardProps) {
  const ranking = [...snapshot.players].sort((a, b) => b.army - a.army)
  const maxArmy = Math.max(...ranking.map((player) => player.army), 1)

  return (
    <section className="panel scoreboard" aria-labelledby="scoreboard-title">
      <div className="panel__heading">
        <div>
          <span className="eyebrow">势力态势</span>
          <h2 id="scoreboard-title">战力排行</h2>
        </div>
        <span className="panel__count">{ranking.filter((player) => player.alive).length} 存活</span>
      </div>

      <div className="ranking-list">
        {ranking.map((player, index) => (
          <article className={`ranking${player.id === snapshot.observerPlayerId ? ' ranking--observer' : ''}`} key={player.id}>
            <span className="ranking__place">{String(index + 1).padStart(2, '0')}</span>
            <span className="ranking__color" style={{ background: player.color }} />
            <div className="ranking__identity">
              <div className="ranking__name-row">
                <strong>{player.name}</strong>
                {player.id === snapshot.observerPlayerId && <span className="you-badge">我方</span>}
              </div>
              <div className="ranking__bar" aria-hidden="true">
                <span style={{ width: `${Math.max(8, (player.army / maxArmy) * 100)}%`, background: player.color }} />
              </div>
            </div>
            <div className="ranking__stats">
              <strong>{player.army}</strong>
              <span>{player.land} 格</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
