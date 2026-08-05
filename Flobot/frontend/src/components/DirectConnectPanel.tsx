import { useState, type FormEvent } from 'react'
import {
  parseDirectConnection,
  type ParsedDirectConnection,
} from '../data/directConnection'

interface DirectConnectPanelProps {
  onConnect: (config: ParsedDirectConnection) => void
  onUseDemo: () => void
}

export function DirectConnectPanel({ onConnect, onUseDemo }: DirectConnectPanelProps) {
  const [roomUrl, setRoomUrl] = useState('')
  const [userId, setUserId] = useState('')
  const [error, setError] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    try {
      const parsed = parseDirectConnection({ roomUrl, userId })
      setError('')
      onConnect(parsed)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '连接信息无效')
    }
  }

  return (
    <main className="connect-screen">
      <section className="connect-card" aria-labelledby="connect-title">
        <div className="connect-card__brand">
          <div className="brand__mark" aria-hidden="true"><span /><span /><span /><span /></div>
          <span>FLOBOT / LOCAL CONTROL</span>
        </div>
        <span className="eyebrow">原版 Python 机器人</span>
        <h1 id="connect-title">接入 Generals.io 对战</h1>
        <p className="connect-card__intro">输入私人房间网址和 user_id，网页会调用本机原版 Python Flobot 加入房间并自动作战。</p>

        <form className="connect-form" onSubmit={submit}>
          <label>
            <span>房间网址</span>
            <input
              type="url"
              value={roomUrl}
              onChange={(event) => setRoomUrl(event.target.value)}
              placeholder="https://generals.io/games/房间ID"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
          <label>
            <span>USER_ID</span>
            <input
              type="password"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="输入你的私人 user_id"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
          {error && <p className="connect-form__error" role="alert">{error}</p>}
          <button className="connect-form__submit" type="submit">调用原版 Flobot 加入房间</button>
        </form>

        <div className="connect-card__security">
          <strong>凭据保护</strong>
          <p>只允许官方 generals.io HTTPS 房间；user_id 只发送给本机 127.0.0.1 服务，不写入配置文件或浏览器存储。</p>
        </div>
        <button className="connect-card__demo" type="button" onClick={onUseDemo}>暂不接入，查看演练棋盘</button>
      </section>
    </main>
  )
}
