# Flobot Python 版

Python 版保留了原机器人的地图查询、BFS/Dijkstra/A*、开局探索、扩张、集结、渗透和将军冲锋策略。实时通信改用 `generals-bots` 的 `GeneralsIOClient`，决策通过标准的 `Agent.act(observation)` 接口返回。

## 安装

需要 Python 3.11 或更高版本：

```powershell
cd D:\python\generals2\Flobot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item config.json.example config.json
```

继续沿用原来的 `config.json`。`redisConfig` 是旧版遗留字段，Python 版不会读取它。

普通服配置使用 `wss://ws.generals.io/`，机器人服配置使用 `wss://botws.generals.io/`。当前普通服禁止用户名自行使用 `[Bot]` 前缀，CLI 会把旧配置中的 `[Bot] Flobot` 自动转换成 `Flobot`；机器人服则会自动补上该前缀。

## 运行

```powershell
python -m flobot config.json
```

调试模式和连续对局：

```powershell
python -m flobot config.json --debug --number-of-games 10
```

使用 `--debug` 时，终端会显示每回合的 `[turn]`、`[action]`、`[queue]` 和 `[network]` 记录，并同时追加写入项目目录下的 `flobot-diagnostics.log`。可以另选文件：

```powershell
python -m flobot config.json --debug --diagnostics-file logs\my-game.log
```

诊断记录包含土地和军队数量、PASS 原因、移动起止坐标、攻击载荷、Socket.IO SID，以及断线前最后一个回合和动作；不会记录 `userId`。

可以固定 Socket.IO 传输方式做对照实验：

```powershell
python -m flobot config.json --debug --transport websocket
python -m flobot config.json --debug --transport polling
```

日志开头的 `requested_transport` 和 `active_transport` 会确认实际使用的传输方式。默认值 `auto` 由 python-socketio 自动协商。

第一次运行会通过 `GeneralsIOClient.register_agent()` 注册配置中的机器人用户名。若该身份已经注册、不希望再次设置名字，可使用：

```powershell
python -m flobot config.json --no-register-username
```

如果 `userId` 已经绑定用户名且账号不是 Supporter，服务器会拒绝改名。程序会保留服务器上的现有用户名并继续加入房间；配置中的 `username` 此时只作为 Agent 的内部名称。

项目内的远程客户端还覆盖了 `generals-bots 2.5.0` 的动作索引转换，先把 `numpy.int8` 行列值转换成 Python `int`，避免较大地图出现整数溢出和错误攻击坐标。

对局客户端会关闭 Socket.IO 自动重连，因为 generals.io 无法把新会话恢复到旧对局。循环还会以 10 秒为接收超时检查会话 ID；连接断开或会话被替换时，本地循环会明确报告并结束，不会永久等待旧对局事件。

安装后也可以运行：

```powershell
flobot-python config.json
```

## 测试

核心测试不需要连接 generals.io、Redis 或网络：

```powershell
python -m unittest discover -s tests -v
```
