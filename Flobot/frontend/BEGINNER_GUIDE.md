# Flobot 网页应用：零基础使用指南

这份指南假设你没有命令行、Python 或前端基础。日常使用不需要修改代码，也不需要分别启动前端和机器人。

## 1. 当前程序是怎样工作的

程序由两部分组成：

- 浏览器网页：填写房间信息、显示棋盘、启动或停止机器人；
- 原版 Python Flobot：接收网页指令、连接 Generals.io、计算策略并发送行动。

浏览器中不包含另一套机器人。所有真正的决策都由项目原有的 `FlobotAgent` 完成。

启动器会把两部分一起启动，所以日常使用时只需要执行一次操作。

## 2. 第一次使用前的准备

电脑需要安装：

- Python 3.11 或更高版本；
- Node.js LTS 版本；
- 可以访问 Generals.io 的网络。

项目位置应当是：

```text
D:\python\generals2\Flobot
```

首次安装 Python 依赖时，可以打开 PowerShell 执行：

```powershell
cd D:\python\generals2\Flobot
python -m pip install -e .
```

如果之前已经运行过 Python Flobot，则通常不需要再次安装。

## 3. 最简单的启动方式

打开文件资源管理器，进入：

```text
D:\python\generals2\Flobot
```

双击：

```text
start-ui.cmd
```

随后会出现一个命令窗口。启动器会自动：

1. 安装缺少的网页依赖；
2. 构建最新网页；
3. 启动本地 Python 服务和原版 Flobot；
4. 打开浏览器页面。

第一次运行可能需要几十秒。看到下面类似内容表示成功：

```text
Flobot 网页已启动：http://127.0.0.1:8765/
按 Ctrl+C 可关闭网页和机器人。
```

如果浏览器没有自动打开，可以手动访问：

```text
http://127.0.0.1:8765/
```

不要关闭命令窗口，它正在维持本地网页和机器人服务。

## 4. 使用 PowerShell 启动

如果双击没有反应，可以打开 PowerShell，复制执行：

```powershell
cd D:\python\generals2\Flobot
powershell -ExecutionPolicy Bypass -File .\start-ui.ps1
```

这个命令与双击 `start-ui.cmd` 的效果相同。

## 5. 加入 Generals.io 房间

页面打开后会显示两个输入框。

### 房间网址

必须使用类似下面的官方 HTTPS 网址：

```text
https://generals.io/games/房间ID
```

程序也支持 `https://bot.generals.io/games/房间ID`。其他域名会被拒绝，以免把私人凭据发送给陌生服务器。

### USER_ID

`user_id` 是 Generals.io 的私人身份凭据。请注意：

- 不要发给其他人；
- 不要截图公开；
- 不要填写到陌生网站；
- 不要让两个机器人同时使用同一个 user_id。

填写完成后，点击：

```text
调用原版 Flobot 加入房间
```

网页会把信息发送到本机 `127.0.0.1`，然后由 Python 启动原版 Flobot。网页不会自己计算机器人行动。

## 6. 等待房间和查看战况

启动机器人后，页面可能显示：

```text
原版 Flobot 已启动，正在等待房间或回合数据
```

这表示本地机器人已经启动，但房间还没开始，或者正在等待其他玩家。

对局开始后，页面会显示：

- 当前回合；
- 我方总兵力和领地；
- 棋盘上每格兵力；
- 山脉、城市、将军和战争迷雾；
- 对手兵力与领地；
- 原版 Flobot 最近发送的行动。

## 7. 看懂棋盘

- 蓝色领地：我方 Flobot；
- 红色领地：对手；
- 格子中的数字：该格兵力；
- `★`：将军；
- `◆`：城市；
- `▲`：山脉；
- 深色区域：战争迷雾；
- 白色闪动边框：机器人最新移动。

把鼠标放在格子上，可以查看该格的类型和兵力提示。

## 8. 停止机器人

对局中点击页面右上角的“停止机器人”，程序会向 Python 服务发送停止请求并尝试安全离开房间。

要关闭整个应用，请回到命令窗口并按：

```text
Ctrl + C
```

也就是按住 `Ctrl`，再按字母 `C`。应用会停止机器人，然后关闭本地网页服务。

推荐使用“停止机器人”或 `Ctrl + C`，不要直接强制结束进程。

## 9. user_id 如何处理

数据流是：

```text
浏览器表单
    ↓ 只发送到 127.0.0.1
本机 Python 服务
    ↓
Generals.io
```

程序不会把 user_id 写入：

- localStorage；
- `config.json`；
- 项目源代码；
- 战况快照；
- 应用日志。

机器人运行期间，Python 内存必须暂时持有 user_id。会话结束后不再保存。

## 10. 页面上的其他数据模式

除了“原版”模式，页面还保留：

- `演练`：使用模拟数据，不连接真实游戏；
- `WebSocket`：只查看已经由本地 Python 服务发布的战况；
- `Polling`：每秒读取一次本地最新战况。

只有“原版”模式会从网页启动 Flobot。演练模式不需要真实房间。

## 11. 常见问题

### 双击 start-ui.cmd 后立即关闭

在 PowerShell 中运行下面的命令，这样可以看到具体错误：

```powershell
cd D:\python\generals2\Flobot
powershell -ExecutionPolicy Bypass -File .\start-ui.ps1
```

### 提示找不到 Python

安装 Python 3.11 或更高版本，安装时勾选“Add Python to PATH”，然后重新打开命令窗口。

### 提示找不到 npm 或 Node.js

安装 Node.js LTS，安装完成后重新打开命令窗口。

### 提示缺少 Python 模块

执行：

```powershell
cd D:\python\generals2\Flobot
python -m pip install -e .
```

### 浏览器显示无法访问 127.0.0.1:8765

确认启动命令窗口仍然打开，并且其中显示了“Flobot 网页已启动”。

### 端口 8765 被占用

通常表示另一个 Flobot 网页服务仍在运行。关闭旧窗口后重试。

### 网页提示无法启动原版 Flobot

依次确认：

1. 房间网址是完整的官方 HTTPS 地址；
2. user_id 没有多余空格；
3. 相同 user_id 没被其他机器人使用；
4. 网络可以访问 Generals.io；
5. 房间仍然存在。

### 页面一直等待回合数据

机器人可能已经加入大厅，但房间尚未开始。确认有足够玩家，并在 Generals.io 房间中开始对局。

### 看到黄色 WARNING

只要后面出现网页启动地址或 `built`，黄色警告通常不会阻止运行。红色错误或窗口直接退出才需要处理。

## 12. 开发者手动运行方式

普通使用者可以跳过本节。

构建前端：

```powershell
cd D:\python\generals2\Flobot\frontend
npm install
npm run build
```

启动统一 Python 网页服务：

```powershell
cd D:\python\generals2\Flobot
python -m flobot.web_app
```

只修改前端时可以运行 `npm run dev`，同时在另一个窗口运行：

```powershell
python -m flobot.web_app --no-browser
```

## 13. 第一次使用检查表

- [ ] 已安装 Python 3.11 或更高版本；
- [ ] 已安装 Node.js LTS；
- [ ] 已安装项目 Python 依赖；
- [ ] 已运行 `start-ui.cmd`；
- [ ] 命令窗口保持打开；
- [ ] 浏览器打开 `http://127.0.0.1:8765/`；
- [ ] 填写了官方房间网址；
- [ ] 填写了未被其他程序使用的 user_id；
- [ ] 页面显示原版 Flobot 已启动。
