# Flobot 本地网页应用

网页本身不包含机器人策略。它通过 `127.0.0.1` 控制接口调用项目原有的 Python `FlobotAgent`，并通过 WebSocket 或 polling 显示战况。

## 推荐启动方式

在 Windows 中双击：

```text
Flobot/start-ui.cmd
```

启动器会依次：

1. 检查并安装前端依赖；
2. 构建 React 页面；
3. 启动原版 Python Flobot 与本地控制服务；
4. 自动打开 `http://127.0.0.1:8765/`。

也可以在 PowerShell 中运行：

```powershell
cd D:\python\generals2\Flobot
powershell -ExecutionPolicy Bypass -File .\start-ui.ps1
```

## 使用流程

页面输入：

- `https://generals.io/games/房间ID` 格式的官方私人房间网址；
- 该玩家的私人 `user_id`。

点击“调用原版 Flobot 加入房间”后，浏览器只把信息发送给本机 `127.0.0.1` 服务。Python 服务创建原有 `FlobotAgent`，连接 Generals.io、运行完整策略并发布战局快照。

`user_id` 不写入 localStorage、项目配置或应用日志。不要让其他机器人同时使用相同 `user_id`。

## 架构

```text
React 网页
  ├─ POST /api/session/start  启动原版 FlobotAgent
  ├─ POST /api/session/stop   安全停止机器人
  ├─ WS /ws                   接收实时战况
  └─ GET /api/snapshot        polling 获取最新战况
                 ↓
         Python FlobotAgent
                 ↓
            Generals.io
```

## 本地接口

```text
GET  http://127.0.0.1:8765/api/health
GET  http://127.0.0.1:8765/api/session
POST http://127.0.0.1:8765/api/session/start
POST http://127.0.0.1:8765/api/session/stop
GET  http://127.0.0.1:8765/api/snapshot
WS   ws://127.0.0.1:8765/ws
```

## 前端开发模式

只有修改前端代码时才需要：

```powershell
cd D:\python\generals2\Flobot\frontend
npm install
npm run dev
```

开发模式仍需同时运行 `python -m flobot.web_app --no-browser`，页面才能启动原版机器人。普通使用请直接运行 `start-ui.cmd`。
