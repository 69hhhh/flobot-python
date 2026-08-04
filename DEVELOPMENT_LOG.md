# 开发记录

本文记录本次 Flobot Python 重构、在线联调和暂停时的项目状态，方便后续继续开发。

## 目标

最初目标是理解并运行原始 Flobot，随后将核心逻辑重构为 Python，并让机器人通过标准 `generals-bots` 接口进入 generals.io 私人房间。

## 已完成工作

### 1. 梳理原始实现

检查了原始 TypeScript/JavaScript 模块：

- Socket.IO 游戏入口 `app.ts`
- 地图 diff 更新
- `GameState` 和 `GameMap`
- BFS、Dijkstra 和 A*
- Discover、Spread、Collect、Infiltrate 和 RushGeneral 策略

同时发现原实现中的若干缺陷，包括路径结果混入整数、索引 0 被排除、A* 启发值使用错误、对象与索引混用，以及多人局将军识别不准确。

### 2. Python 核心重构

创建 `Flobot/flobot/` Python 包，包含：

- 地图和状态模型
- diff patcher
- BFS、最短路径、加权 A* 和决策树
- 策略调度及各阶段策略
- 动作队列和边界检查
- 命令行入口

原始 Node.js 代码保留，便于行为对照。

### 3. 改用 generals-bots 标准接口

最初 Python 版直接实现了 Socket.IO runner，之后根据在线框架改为：

- `FlobotAgent(Agent)`
- `FlobotAgent.act(observation)`
- `GeneralsIOClient`
- 标准五元素 `Action`

Observation 被转换为原策略可使用的一维地图视图；一维 `Move(start, end)` 被转换为二维行列和方向动作。

### 4. 普通服连接兼容

联调过程中发现：

- 不带机器人密钥连接普通 NA 服会被明确拒绝。
- `generals-bots 2.5.0` 支持通过 `public_server=True` 和内置 `bot_key` 连接普通服。
- 库内注释要求用户名以 `[Bot]` 开头，但当前服务器反而禁止用户自行使用该前缀。
- 已有用户名的非 Supporter 账号不能再次改名。

项目现在会：

- 普通服自动移除旧的 `[Bot]` 前缀。
- 机器人服自动补充前缀。
- 已绑定用户名时保留服务器现有名称并继续运行。

### 5. 修复动作索引溢出

`generals-bots 2.5.0` 使用 `numpy.int8` 保存 Action。在较大地图上执行：

```text
row * width + column
```

可能发生整数溢出，产生错误或负数攻击索引。项目覆盖了远程动作转换，在计算前先转换为 Python `int`，并加入大地图回归测试。

### 6. 修复断线后终端假死

原客户端断线后会自动重连，但 generals.io 无法把新 SID 恢复到旧对局。结果是网页显示玩家退出，而终端继续等待旧对局事件。

项目现在会：

- 关闭底层自动重连。
- 使用 10 秒接收超时。
- 检查当前 SID 是否仍属于本局。
- 会话丢失时输出最后回合和动作，并正常结束本地循环。

### 7. 加入诊断系统

诊断日志同时写到终端和文件，记录：

- 回合、土地、军队和敌方数据
- PASS/MOVE 决策
- 动作起止坐标和方向
- 被丢弃的队列动作及原因
- 请求和实际传输方式
- Socket.IO SID
- 接收超时、游戏结束和会话丢失

日志不会记录 `userId`。

### 8. 加入传输方式开关

CLI 现支持：

```text
--transport auto
--transport polling
--transport websocket
```

用于区分高速 polling 断线和动作频率问题。

## 已完成实验

### 普通服基础连接

- 成功连接 `ws.generals.io`
- 成功加入私人房间
- 成功开始和完成对局
- 成功生成 generals.io 回放

### AFK 假设

诊断日志显示一次断开前：

```text
turn=365
land=63
持续 MOVE
SID 最终变为 None
```

因此已排除一般性 AFK。该局没有收到 `game_lost`、`game_won` 或 `gio_error`，属于 Socket.IO 会话终止。

### 实验 1：低速 polling

条件：

- `customGameSpeed = 1`
- 默认/当前 polling 传输
- 另一个浏览器使用另一个账号进行对战

结果：运行稳定，没有复现断线。

结论：同账号会话冲突、一般性 AFK 和低负载 polling 基本排除。问题与速度 4 下的高更新频率、动作频率或 polling 压力相关。

## 当前暂停点

配置已经恢复：

```json
"customGameSpeed": 4
```

实验 2 的代码准备已经完成，但尚未执行。

运行命令：

```powershell
cd Flobot
python -m flobot config.json --debug `
  --transport websocket `
  --diagnostics-file .\logs\exp2-speed4-websocket.log
```

实验时暂时不要加入动作限频，因为要先单独判断传输方式的影响。

## 后续建议

1. 重复两到三次速度 4 + WebSocket 实验。
2. 如果稳定，确认高速 polling 是主要原因。
3. 如果仍断线，新增动作发送间隔和重复动作抑制开关。
4. 分别测试“每回合动作”“每两回合动作”和“状态未变化时不重复动作”。
5. 记录底层 disconnect reason，进一步区分服务器主动关闭和本地网络故障。
6. 在连接问题解决后，再优化策略质量和多人局支持。

## 验证状态

暂停前已经完成：

```powershell
python -m compileall -q flobot tests
python -m unittest discover -s tests -v
python -m flobot --help
```

测试结果：17 项测试通过。

## 隐私与上传检查

- `Flobot/config.json` 已被忽略。
- `Flobot/flobot-diagnostics.log` 已被忽略。
- `Flobot/logs/` 已被忽略。
- 文档没有写入实际 `userId`。

上传前仍应执行：

```powershell
git status --short
git grep -n "实际 userId"
```

确保敏感身份从未进入提交历史。
