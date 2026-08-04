# Flobot Python

Flobot 是一个用于 [generals.io](https://generals.io/) 的启发式机器人。本仓库保留原始 Node.js/TypeScript 实现，并新增 Python 版本。Python 版通过 `generals-bots` 提供的 `GeneralsIOClient` 与在线服务器通信，通过标准的 `Agent.act(observation)` 接口执行决策。

> 当前状态：功能可运行，正在诊断速度 4 下的连接稳定性。速度 1 + polling 的对照实验已经稳定完成；WebSocket 对照实验尚待执行。

## 功能

- generals.io 地图状态转换与战争迷雾记忆
- BFS、最短路径和加权 A* 寻路
- 开局探索、扩张、兵力收集、渗透和攻击将军策略
- 标准 `Agent.act(observation)` 动作接口
- 普通服和机器人服连接
- polling、WebSocket 和自动协商三种传输模式
- 回合、动作、队列、SID、超时和断线诊断日志
- 针对 `generals-bots 2.5.0` 的大地图动作索引溢出修复

## 目录结构

```text
generals2/
├── README.md                 # 项目说明
├── DEVELOPMENT_LOG.md        # 本次开发和实验记录
└── Flobot/
    ├── flobot/               # Python 包
    │   ├── agent.py          # Agent.act 适配及在线客户端
    │   ├── algorithms.py     # BFS、最短路径和 A*
    │   ├── game_map.py       # 地图查询
    │   ├── game_state.py     # 原协议状态处理
    │   ├── strategy.py       # 策略调度
    │   └── cli.py            # 命令行入口
    ├── tests/                # Python 单元测试
    ├── scripts/              # 原始 JavaScript 策略
    ├── app.ts                # 原始 Node.js 入口
    ├── config.json.example   # 配置示例
    └── pyproject.toml        # Python 包配置
```

## 环境要求

- Windows、Linux 或 macOS
- Python 3.11 或更高版本
- 网络可以访问 generals.io

本项目已在 Python 3.12.4 和 `generals-bots 2.5.0` 下测试。

## 安装

Windows PowerShell：

```powershell
cd Flobot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.json.example config.json
```

如果直接使用全局 Python：

```powershell
cd Flobot
python -m pip install -e .
Copy-Item config.json.example config.json
```

## 配置

编辑 `Flobot/config.json`：

```json
{
  "gameConfig": {
    "GAME_SERVER_URL": "wss://ws.generals.io/",
    "MAX_TURNS": 5000,
    "BOT_ID_PREFIX": "flobot",
    "userId": "YOUR_PRIVATE_USER_ID",
    "username": "YourAgentName",
    "customGameId": "your-room-id",
    "customGameSpeed": 1,
    "warCry": []
  },
  "redisConfig": {
    "ENABLED": false
  }
}
```

重要说明：

- `userId` 是私密身份标识，不要提交或公开。
- `config.json` 已加入 `.gitignore`，不会上传到 GitHub。
- 普通服使用 `wss://ws.generals.io/`。
- 机器人服使用 `wss://botws.generals.io/`。
- 普通服当前禁止用户名自行使用 `[Bot]` 前缀；CLI 会自动兼容旧配置。
- 已绑定用户名的非 Supporter 账号无法改名，程序会保留服务器现有名称继续运行。
- Python 版不使用旧配置中的 Redis 遥测字段。

## 运行

进入项目目录：

```powershell
cd Flobot
```

基本运行：

```powershell
python -m flobot config.json
```

开启详细诊断：

```powershell
python -m flobot config.json --debug
```

跳过用户名注册：

```powershell
python -m flobot config.json --debug --no-register-username
```

固定传输方式：

```powershell
python -m flobot config.json --debug --transport websocket
python -m flobot config.json --debug --transport polling
```

单独保存实验日志：

```powershell
python -m flobot config.json --debug `
  --transport websocket `
  --diagnostics-file .\logs\experiment-websocket.log
```

## 诊断日志

默认日志文件为 `Flobot/flobot-diagnostics.log`。日志文件和 `logs/` 目录均不会提交到 Git。

主要记录类型：

- `[turn]`：回合数、土地、军队、敌方数据和策略状态
- `[action]`：PASS 原因或移动起止坐标
- `[queue]`：过期动作及其丢弃原因
- `[network]`：传输方式、Socket.IO SID、攻击载荷、超时和断线

查看最后 50 行：

```powershell
Get-Content .\flobot-diagnostics.log -Tail 50
```

## 当前连接实验

已经完成：

- 速度 1 + polling：运行稳定
- 两个浏览器账号使用不同的 `userId`，已排除同账号会话冲突
- 断开时土地数为 63、持续发送动作，已排除 AFK

下一项实验：

1. 将 `customGameSpeed` 设为 `4`。
2. 强制使用 WebSocket。
3. 暂时不限制动作频率，确保一次只改变一个变量。

```powershell
python -m flobot config.json --debug `
  --transport websocket `
  --diagnostics-file .\logs\exp2-speed4-websocket.log
```

结果判断：

- WebSocket 稳定：问题更可能来自高速 polling。
- WebSocket 仍在相似回合断开：下一步测试动作限频和重复动作抑制。
- WebSocket 无法建立：本地网络或代理可能不支持该传输。

## 测试

```powershell
cd Flobot
python -m unittest discover -s tests -v
```

当前共有 17 项单元测试，覆盖地图 diff、边界、寻路、动作转换、CLI 传输选项和会话丢失判断。

## 已知限制

- 当前策略会在高速对局中频繁发送动作，部分动作会连续重复。
- `generals-bots 2.5.0` 的在线客户端与 2026 年服务器用户名规则存在差异，本项目已做兼容处理。
- generals.io 无法把新的 Socket.IO 会话恢复到已开始的旧对局，因此对局中断线后本地循环会结束。
- 原始策略主要面向 1v1，超过两个玩家时的观察和敌方建模能力有限。

## 安全

提交前确认以下文件未进入 Git：

```powershell
git check-ignore -v Flobot\config.json Flobot\flobot-diagnostics.log
```

如果 `userId` 曾经被提交，应立即更换身份，而不只是删除最新版本中的字符串。

## 来源与许可证

原始 Flobot 由 Corsair Coalition 开发，采用 Apache License 2.0。原始许可证保存在 `Flobot/LICENSE`。Python 重构延续该项目的算法思路，并保留原始实现供对照。
