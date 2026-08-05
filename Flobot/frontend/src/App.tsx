import { useMemo, useState } from 'react'
import { ActivityFeed } from './components/ActivityFeed'
import { BattleBoard } from './components/BattleBoard'
import { DirectConnectPanel } from './components/DirectConnectPanel'
import { Scoreboard } from './components/Scoreboard'
import { createGameSource, type DataMode } from './data/createGameSource'
import type { ParsedDirectConnection } from './data/directConnection'
import { useGameStream } from './hooks/useGameStream'
import type { ConnectionState } from './types/game'

const connectionCopy: Record<ConnectionState, string> = {
  connecting: '正在连接',
  connected: '数据同步中',
  disconnected: '连接已断开',
  error: '数据异常',
}

const modeCopy: Record<DataMode, string> = {
  direct: '原版',
  mock: '演练',
  websocket: 'WebSocket',
  polling: 'Polling',
}

const readInitialMode = (): DataMode => {
  const configured = import.meta.env.VITE_GAME_TRANSPORT
  if (configured) return configured
  const stored = window.localStorage.getItem('flobot-data-mode')
  return stored === 'direct' || stored === 'websocket' || stored === 'polling' || stored === 'mock'
    ? stored
    : 'direct'
}

const formatElapsed = (seconds: number) => {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

interface TransportSelectorProps {
  mode: DataMode
  onChange: (mode: DataMode) => void
}

function TransportSelector({ mode, onChange }: TransportSelectorProps) {
  return (
    <div className="transport-selector" aria-label="数据接入方式">
      {(Object.keys(modeCopy) as DataMode[]).map((item) => (
        <button
          className={item === mode ? 'transport-selector__button transport-selector__button--active' : 'transport-selector__button'}
          key={item}
          type="button"
          aria-pressed={item === mode}
          onClick={() => item !== mode && onChange(item)}
        >
          {modeCopy[item]}
        </button>
      ))}
    </div>
  )
}

function LoadingState({
  mode,
  connection,
  onChange,
  onResetDirect,
}: TransportSelectorProps & { connection: ConnectionState; onResetDirect: () => void }) {
  const message = connection === 'error'
    ? mode === 'direct'
      ? '无法启动原版 Flobot，请确认本地应用正在运行并检查连接信息'
      : '无法连接本地数据服务，请确认机器人已经启动'
    : connection === 'connected'
      ? mode === 'direct'
        ? '原版 Flobot 已启动，正在等待房间或回合数据'
        : '数据服务已连接，正在等待机器人进入对局'
      : '正在建立战场链路'
  return (
    <main className="loading-state">
      <div className="loading-state__mark"><span /></div>
      <p>{message}</p>
      <TransportSelector mode={mode} onChange={onChange} />
      {mode === 'direct' && (
        <button className="loading-state__reset" type="button" onClick={onResetDirect}>修改房间信息</button>
      )}
    </main>
  )
}

export default function App() {
  const [mode, setMode] = useState<DataMode>(readInitialMode)
  const [directConfig, setDirectConfig] = useState<ParsedDirectConnection | null>(null)
  const source = useMemo(() => createGameSource(mode, directConfig), [mode, directConfig])
  const { snapshot, connection } = useGameStream(source)

  const changeMode = (nextMode: DataMode) => {
    if (mode === 'direct' || nextMode === 'direct') setDirectConfig(null)
    window.localStorage.setItem('flobot-data-mode', nextMode)
    setMode(nextMode)
  }

  if (mode === 'direct' && directConfig === null) {
    return (
      <DirectConnectPanel
        onConnect={setDirectConfig}
        onUseDemo={() => changeMode('mock')}
      />
    )
  }

  if (!snapshot) {
    return (
      <LoadingState
        mode={mode}
        connection={connection}
        onChange={changeMode}
        onResetDirect={() => setDirectConfig(null)}
      />
    )
  }

  const totalLand = snapshot.tiles.filter((tile) => tile.ownerId !== null).length
  const observer = snapshot.players.find((player) => player.id === snapshot.observerPlayerId)
  const visibleTiles = snapshot.tiles.filter((tile) => tile.discovered).length
  const visibility = Math.round((visibleTiles / snapshot.tiles.length) * 100)

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand__mark" aria-hidden="true"><span /><span /><span /><span /></div>
          <div>
            <strong>FLOBOT</strong>
            <span>TACTICAL OBSERVER</span>
          </div>
        </div>
        <div className="topbar__meta">
          <TransportSelector mode={mode} onChange={changeMode} />
          {mode === 'direct' && (
            <button className="disconnect-button" type="button" onClick={() => setDirectConfig(null)}>停止机器人</button>
          )}
          <span className="game-id">{snapshot.gameId}</span>
          <span className={`connection connection--${connection}`}>
            <i aria-hidden="true" />{connectionCopy[connection]}
          </span>
        </div>
      </header>

      <main className="dashboard">
        <section className="mission-heading">
          <div>
            <span className="eyebrow">实时观测 / {source?.name}</span>
            <h1>当前战局</h1>
            <p>以我方视野追踪领地、兵力与前线变化</p>
          </div>
          <div className="mission-heading__time">
            <span>对局时长</span>
            <strong>{formatElapsed(snapshot.elapsedSeconds)}</strong>
          </div>
        </section>

        <section className="metrics" aria-label="战局摘要">
          <article className="metric metric--primary">
            <span>当前回合</span>
            <strong>{snapshot.turn}</strong>
            <small>TURN INDEX</small>
          </article>
          <article className="metric">
            <span>我方兵力</span>
            <strong>{observer?.army ?? 0}</strong>
            <small>{observer?.land ?? 0} 格领地</small>
          </article>
          <article className="metric">
            <span>已占领区域</span>
            <strong>{totalLand}</strong>
            <small>全场有效领地</small>
          </article>
          <article className="metric">
            <span>战场可见度</span>
            <strong>{visibility}<em>%</em></strong>
            <small>{visibleTiles} / {snapshot.tiles.length} 格</small>
          </article>
        </section>

        <div className="content-grid">
          <section className="panel map-panel" aria-labelledby="map-title">
            <div className="panel__heading map-panel__heading">
              <div>
                <span className="eyebrow">作战地图</span>
                <h2 id="map-title">北境战区</h2>
              </div>
              <div className="map-scale"><span />1 格 = 1 战术单位</div>
            </div>

            <div className="board-frame">
              <span className="board-corner board-corner--tl" />
              <span className="board-corner board-corner--tr" />
              <span className="board-corner board-corner--bl" />
              <span className="board-corner board-corner--br" />
              <BattleBoard snapshot={snapshot} />
            </div>

            <div className="legend" aria-label="地图图例">
              <span><i className="legend__icon legend__icon--general">★</i> 将军</span>
              <span><i className="legend__icon legend__icon--city">◆</i> 城市</span>
              <span><i className="legend__icon legend__icon--mountain">▲</i> 山脉</span>
              <span><i className="legend__icon legend__icon--fog" /> 战争迷雾</span>
              <span><i className="legend__icon legend__icon--route" /> 最新行动</span>
            </div>
          </section>

          <aside className="sidebar">
            <Scoreboard snapshot={snapshot} />
            <ActivityFeed snapshot={snapshot} />
          </aside>
        </div>
      </main>

      <footer className="footer">
        <span>{mode === 'direct' ? '原版 Python Flobot 自动作战' : '只读观察模式'}</span>
        <span>最后同步 {new Date(snapshot.updatedAt).toLocaleTimeString('zh-CN', { hour12: false })}</span>
        <span>FLOBOT MONITOR / v0.1</span>
      </footer>
    </div>
  )
}
