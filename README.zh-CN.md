# 钉钉 ↔ Orca 本地桥接

[English](README.md) · 简体中文

在手机钉钉里私聊你自己的 Orca bot。桥接程序跑在开着 Orca 的那台电脑上，
通过钉钉 Stream 模式收消息：不需要公网地址，也不用改 Orca。

> [!IMPORTANT]
> 只支持**一个人**和机器人的**单聊**。群聊和多人共用在协议层面就不安全，
> 不是改配置能解决的，见[白名单与私聊限制](#白名单与私聊限制)。
> 已用 dws v1.0.68 和 Orca CLI 1.4.268 在真实单聊里跑通，其他版本可能有差异。

**适合你，如果**：你在 macOS 或 Linux 上用 Orca 桌面端，并且已经有 bot；能自己建钉钉企业内部应用，
或者有管理员帮你建；那台电脑能一直开着 Orca。

**不适合**：群聊、多人共用一个机器人、Windows、需要在服务器上 7×24 常驻。

[快速开始](#快速开始) · [配置](#配置) · [超时与 pending](#超时与-pending) · [排错](#排错) · [安全边界](#安全边界)

## 工作原理

```text
钉钉单聊 → 钉钉 Stream → dws dev connect（custom 渠道，跑在你的电脑上）
  → python3 bridge.py handle '<消息>' → orca orchestration send → 你的 Orca bot
  → 回复投递到启动桥的那个 Orca 终端的邮箱 → bridge.py 按请求 ID 取回
  → dws 通过回调里的会话 webhook 发回钉钉
```

- `bridge.py start` 是启动器。它检查配置，然后把自己替换成前台运行的 `dws dev connect`。
- 每来一条消息，dws 就运行一次 `bridge.py handle`。消息只作为最后一个参数传入，不经过 shell。
- 同一个钉钉应用、bot 和主人，始终用同一个 Orca chat，bot 能接着上文聊。

## 快速开始

每一步都有「完成标准」，没达到就先别往下走。

### 0. 检查环境

```sh
python3 --version   # 3.10 或更高
orca --version      # 已验证 1.4.268
dws version         # 已验证 v1.0.68
orca bot list       # 列出本机的 bot 和它们的名字
```

Orca 桌面端要在运行，并且已经有一个 bot。

**完成标准**：四条命令都正常输出，`orca bot list` 里有你要接的 bot。记下它的名字。

### 1. 获取代码

```sh
git clone https://github.com/stone16/orca-dingtalk-bridge.git
cd orca-dingtalk-bridge
pwd
```

**完成标准**：`pwd` 输出的路径里没有空格。dws 会按空白切分 agent 命令，所以启动器拒绝带空白的路径。

### 2. 创建钉钉应用

1. 打开[钉钉开发者后台](https://open-dev.dingtalk.com/)，选中你的组织，创建「企业内部应用」，
   名字比如 **Orca Bridge**。
2. 进入「添加应用能力 → 机器人」，把「消息接收模式」设为 **Stream 模式**，保存。
   dws 建立 Stream 连接时会订阅机器人消息回调，回复走回调里的会话 webhook，
   不需要另外申请主动发消息的接口权限。
3. 在「版本管理与发布」里，第一次测试先把「可见范围」设成只有你自己，然后发布。
   你没有发布权限的话，请组织管理员来做。

**完成标准**：应用已发布，可见范围里有你。

### 3. 登录 dws，拿到两个 ID

```sh
dws auth login     # 必要时扫码。登录应用所在的那个组织
dws auth status
dws dev app list --name 'Orca Bridge'
dws contact user get-self --jq '.result[0].orgEmployeeModel.userId'
```

- **unifiedAppId**：`dws dev app list` 输出里的 `unifiedAppId`。dws 凭它自己去取机器人凭证。
- **你的 staff ID**：`get-self` 输出的那串值（去掉两边的引号）。它是你在组织内的 userId，不是工号；
  钉钉回调里的 `senderStaffId` 就是这个值。dws 必须登录在应用所在的组织，否则查到的是别的组织的 ID。

AppSecret 只留在钉钉和 dws 的凭证存储里。不要写进文件或脚本，也不要用 `--robot-client-secret`、
`--client-secret` 这类参数传入：命令行参数会出现在本机的进程列表里。

**完成标准**：两个值都拿到了。

### 4. 在 Orca 终端里自检

在 Orca 里打开这个 checkout，**新建一个普通 shell 终端标签**。不要用 Claude、Codex 等 agent 的面板，
启动器会拒绝。桥要一直在这个标签里前台运行：Orca CLI 需要运行时发放的终端句柄，
bot 的回复也投递到这个终端的邮箱。

```sh
echo "$ORCA_TERMINAL_HANDLE"   # 应输出 term_ 开头的句柄
```

然后只测 Orca 这一半。下面的命令会真的给 bot 发一个问题，但不连钉钉，
用的是合成的白名单值和临时状态目录。括号让这些变量只在子 shell 里生效，不影响第 5 步：

```sh
(
  export DINGTALK_OWNER_USER_ID=synthetic DWS_ALLOWED_USERS=synthetic DWS_ALLOWED_GROUPS=none
  export ORCA_BRIDGE_BOT='你的 bot 名'
  export ORCA_BRIDGE_SCOPE="$(printf '%064d' 1)"
  export ORCA_BRIDGE_STATE_DIR="$(mktemp -d)"
  python3 -I bridge.py handle '--probe: reply with BRIDGE_OK using the question reply command.' </dev/null
)
```

**完成标准**：终端打印出 bot 的回复，里面有 `BRIDGE_OK`。看到 `Bridge error:` 就先查[排错](#排错)。

### 5. 启动桥

还是在这个终端标签里：

```sh
export DINGTALK_OWNER_USER_ID='你的 staff ID'
export DWS_ALLOWED_USERS="$DINGTALK_OWNER_USER_ID"
export ORCA_BRIDGE_BOT='你的 bot 名'
python3 bridge.py start '你的 unifiedAppId'
```

`ORCA_BRIDGE_BOT` 实际上是必填的：不设时默认是 `Sto`，那是作者自己的 bot 名。

**完成标准**：终端里没有出现 `Bridge error:`，进程停在前台，由 dws 保持 Stream 连接。
按 Ctrl-C 停止。

### 6. 发第一条私聊

在钉钉里找到这个机器人（搜应用名），打开和它的单聊，发一个无害的问题。

**完成标准**：收到 bot 的回复。200 个字符以内的回复是纯文本，更长的按 Markdown 渲染。
回复不用 AI 卡片。

## 配置

所有配置都来自环境变量，在启动前设置。改了之后要 Ctrl-C 停掉再重新 `start`。

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `DINGTALK_OWNER_USER_ID` | 是 | — | 唯一允许使用的 staff ID，只能有一个，不能带逗号 |
| `DWS_ALLOWED_USERS` | 是 | — | dws 的用户白名单，必须和 `DINGTALK_OWNER_USER_ID` 完全一致 |
| `ORCA_BRIDGE_BOT` | 实际必填 | `Sto` | 要对话的 Orca bot 名，用 `orca bot list` 查 |
| `ORCA_BRIDGE_TIMEOUT` | 否 | `300` | 每条消息最多等多少秒，必须是正整数。dws 侧的 agent 超时会设成这个值加 15 秒 |
| `ORCA_BRIDGE_STATE_DIR` | 否 | `~/.orca-dingtalk-bridge` | 状态目录，放一个只有你能读的位置 |
| `DWS_ALLOWED_GROUPS` | 不要设 | — | 只能不设或设为 `none`。启动器总会把它设成 `none` |
| `DINGTALK_ALLOWED_USERS` | 不要设 | — | 旧版本的变量，设了会拒绝启动 |
| `ORCA_BRIDGE_GROUPS` | 不要设 | — | 旧版本的变量，设了会拒绝启动 |
| `ORCA_TERMINAL_HANDLE` | 自动 | — | Orca 终端自动设置，不要手动改 |
| `ORCA_BRIDGE_SCOPE` | 自动 | — | 启动器设置的状态键。只在第 4 步自检时手动设 |

状态按「钉钉应用 + bot 名 + 主人」区分。换了 bot 名或应用，就是一份新状态，下一条消息会开一个新的 Orca chat。

## 白名单与私聊限制

**谁能问：只有你一个人。** 检查有三层：

1. 启动器在启动 dws 之前检查：`DWS_ALLOWED_USERS` 必须恰好等于 `DINGTALK_OWNER_USER_ID`，
   不能为空，不能有多个，不能设旧变量。
2. dws 收到回调后，先拿回调里的 `senderStaffId` 对照 `DWS_ALLOWED_USERS`。名单外的人发来的消息，
   dws 不会交给桥。
3. 桥每次处理消息时，再检查一遍同样的配置。

桥自己看不到发送者。dws 的 custom 渠道只把消息文本作为最后一个参数传给桥，stdin 是关闭的，
不提供发送者 ID，也不提供会话 ID。所以发送者校验完全依赖 dws 的白名单。

**只能私聊。** 启动器总是把 dws 的群白名单设成 `none`，群里的消息不会触发桥。
原因是 custom 渠道不给可信的会话 ID：如果允许多人或群聊，一条迟到的回复可能被发给下一个提问的人。
这是这个渠道的硬限制，只有换成能提供可信会话信息的通道，才能安全地支持多人或群聊。
**不要为了给同事用而放宽白名单**，启动器也会拒绝这样的配置。

应用的「可见范围」是钉钉那一侧的设置，决定谁能看到这个机器人；真正限制谁能触发桥的是上面的白名单。

从旧版本升级时，先 `unset DINGTALK_ALLOWED_USERS ORCA_BRIDGE_GROUPS`，
`DWS_ALLOWED_GROUPS` 不设或设成 `none`。

## 超时与 pending

Orca 是异步收问题的：桥发出问题后拿到一个请求 ID，然后只在启动桥的那个终端的邮箱里，按请求 ID 找回复。
同一时间只处理一条消息，处理期间再来的消息会被拒收，不会转给 bot。

每条消息最多等 `ORCA_BRIDGE_TIMEOUT` 秒（默认 300）。要改这个值，必须在启动前设置，改完后重启桥才会生效。等不到时分三种情况：

**问题已送达，只是还没答完。** 第一次等待超时时，钉钉会收到
`Orca has not answered yet. Send any message later to collect the reply; that message will not be forwarded. ...`
提示，bot 在 Orca 里继续做。如果下一条消息到来时 bot 仍在运行，会收到
`The earlier Orca request is still running, so this message was not forwarded. ...` 提示。
这两种情况都会记下一条 pending 记录：

- 你发的**下一条消息不会转给 bot**。桥只借这次机会去取上一条的回复。
- 取到了，会回「**Earlier Orca reply** (this message was not forwarded)」加上那条回复；
  取不到，就再提示一次仍在运行的 pending 状态。
- 取回之后，再发的新消息才开始新的一轮。所以长任务做完后，先随便发一条（比如「取回」）拿结果，
  再重发你真正想问的。

确认 Orca 里的旧请求已经结束后，可以在钉钉发送一条单独的 `/reset` 或 `重置`，立即清掉 pending。
这条消息只会收到确认，不会转给 bot。只有白名单里的发送者能触发这个命令。

**发送结果不确定。** 比如 Orca CLI 超时，或者返回了无法确认的结果。桥不知道 bot 有没有收到，
为了不让同一件事执行两遍，它不会重发。之后每条消息都会收到 unconfirmed 的提示，直到记录过期。
先确认 Orca bot chat 里的结果，再发送 `/reset` 或 `重置` 可以提前清除这条记录；清除后这条消息不会被转发，请求也不会重发。

**Orca 明确拒收。** 比如 bot 名不对。桥会清掉记录，修好配置后直接重发即可。
如果是保存的 Orca chat 已经不存在，下一条消息会自动开一个新 chat。

pending 记录 24 小时后过期。过期后的第一条消息只会清掉记录并回一条 expired 提示，这条消息本身也不转发；
之后的消息恢复正常。那个旧请求可能还在 Orca 里运行，重发之前先去 bot 的 chat 里看一眼：

```sh
orca bot chats --bot '你的 bot 名'
```

确认 Orca 里的旧请求已经结束后，发送 `/reset` 或 `重置` 会立即清掉 unconfirmed pending，保留已有的 Orca chat。
如果钉钉无法使用，或状态文件损坏，才需要手动清掉记录。先在 Orca 里确认旧请求已经结束，然后：

1. 在桥的终端按 Ctrl-C 停止；
2. 把状态目录里的 `bridge-state-<64 位十六进制>.json` 挪走（建议改名备份，不要直接删）；
3. 重新 `start`。下一条消息会开一个新的 Orca chat。

调大 `ORCA_BRIDGE_TIMEOUT` 能少遇到 pending，但每条消息占着桥的时间也会变长，这期间别的消息都会被拒收。
pending 期间换一个终端标签重启桥，Orca 1.4.268 仍能读取已关闭旧终端的邮箱并取回迟到回复。

## 排错

报错都以 `Bridge error:` 开头，后面是固定的英文原文，可以直接搜。启动阶段的报错打印在终端里；
对话阶段的报错由 dws 发回钉钉，dws v1.0.68 会转发最多 300 个字符的 stderr，
前面带「本地 custom agent 调用失败，」。

### 启动时（终端）

| 报错原文 | 原因 | 处理 |
|---|---|---|
| `Usage: python3 bridge.py start <dws unified app ID>` | 参数不对 | 用 `python3 bridge.py start '<unifiedAppId>'` |
| `Set DWS_ALLOWED_USERS to exactly the staff ID in DINGTALK_OWNER_USER_ID.` | 两个变量不一致、为空、带逗号，或设了旧的 `DINGTALK_ALLOWED_USERS` | 按[第 5 步](#5-启动桥)重新设置 |
| `This bridge supports direct chats only.` | `DWS_ALLOWED_GROUPS` 不是 `none`，或设了 `ORCA_BRIDGE_GROUPS` | `unset` 这两个变量 |
| `Start the bridge in a dedicated Orca terminal.` | 不在 Orca 终端里，没有 `ORCA_TERMINAL_HANDLE` | 在 Orca 里新建普通 shell 终端标签再启动 |
| `Set ORCA_BRIDGE_TIMEOUT to a positive number of seconds.` | 超时不是正整数，比如写成了 `2m` | 改成秒数，比如 `300` |
| `Move the bridge checkout to a path without whitespace.` | checkout 路径里有空白 | 把仓库挪到不含空格的路径 |
| `Start the bridge in a live, plain-shell Orca terminal.` | 在 agent 面板里启动，或终端句柄对不上 | 新建普通 shell 终端标签 |
| `Orca refused the request before delivery. Check the bot and terminal settings.` | 终端句柄已失效 | 新建终端标签重新启动 |
| `Orca returned an unconfirmed result. Check the Orca bot chat before retrying.` | Orca 桌面端没运行，或 CLI 连不上运行时 | 打开 Orca，确认 `orca --version` 正常后重试 |
| `Orca or local state failed. Check the bot chat before retrying.` | `orca` 不在 PATH，或 CLI 输出无法解析 | 确认在这个终端里能运行 `orca --version` |

### 对话时（钉钉）

| 报错原文 | 原因 | 处理 |
|---|---|---|
| `Start dws through the bridge launcher so its allowlists are enforced.` | 手动运行了 `dws dev connect`，没走启动器 | 停掉它，改用 `python3 bridge.py start` |
| `Orca refused the request before delivery. Check the bot and terminal settings.` | bot 名不对，或者启动桥的终端已失效。问题没有发出去 | 用 `orca bot list` 核对 `ORCA_BRIDGE_BOT`，必要时重新启动 |
| `The saved Orca chat is unavailable. The next message will start a new chat.` | 保存的 Orca chat 被删了 | 直接再发一次 |
| `The bridge is busy with another message. This message was not forwarded.` | 上一条还在处理 | 等它回复后再发 |
| `The previous send is unconfirmed, so this message was not forwarded. Its pending record expires after 24 hours. Check the Orca bot chat before repeating the request.` | 上一次发送结果不确定 | 先去 Orca 确认，记录过期前不会重发 |
| `The earlier Orca request is still running, so this message was not forwarded. Send any message later to collect the reply; that message will not be forwarded. The request will not be resent and expires after 24 hours. Send /reset or 重置 after checking Orca to clear it.` | 上一条问题仍在运行 | 稍后发消息取回，或确认 Orca 后发 `/reset` 清除 |
| `Orca has not answered yet. Send any message later to collect the reply; that message will not be forwarded. The request will not be resent and expires after 24 hours. Send /reset or 重置 after checking Orca to clear it.` | 等待超时，问题已送达 | 稍后再发一条来取回，或确认 Orca 后发 `/reset` 清除，见[超时与 pending](#超时与-pending) |
| `Orca returned an unconfirmed result. Check the Orca bot chat before retrying.` | Orca 的结果无法确认 | 先到 Orca 的 bot chat 里看那条问题有没有收到，再决定要不要重发 |
| `The previous request expired and was not resent. Check Orca before continuing.` | pending 超过 24 小时，已清除，这条消息没有转发 | 去 Orca 确认旧请求的结果，然后重发 |
| `Orca or local state failed. Check the bot chat before retrying.` | 其他意外：`orca` 不在 PATH、CLI 输出无法解析、状态文件损坏等 | 先查 bot chat；一直出现就按上文挪走状态文件 |

### 没有报错，但不对劲

- **私聊机器人完全没反应**：先看桥的终端还在不在运行。然后核对 staff ID 是否和第 3 步查到的一致
  （名单外的消息 dws 不会交给桥），应用是否已发布、可见范围里有没有你，dws 是否登录在应用所在的组织。
- **群里 @ 机器人没反应**：设计如此，只支持单聊。
- **回复是纯文本，不是卡片**：设计如此，200 个字符以内是纯文本，更长的按 Markdown 渲染。
- **回复是 `The Orca bot returned an empty answer.`**：bot 给了空回复，去 Orca 的 chat 里看它做了什么。
- **发送 `/reset` 或 `重置` 后收到 `Pending request cleared. This message was not forwarded.`**：pending 已清除，已有的 Orca chat 会保留，下一条消息会开始新请求。
- **换了 bot 或应用后，bot 不记得之前的对话**：状态按应用、bot 和主人区分，换了就会开新 chat。

## 安全边界

分成两类：代码和 dws 会强制执行的，和只是写给 bot 的指令。

**强制执行：**

- 只有 `DINGTALK_OWNER_USER_ID` 能触发，由 dws 按 `senderStaffId` 校验；群聊关闭。配置不合规时启动器拒绝启动，
  桥每次处理消息也会再检查。
- 启动器只在活着的普通 shell Orca 终端里运行，拒绝 agent 面板，也拒绝带空白的 checkout 路径。
- 消息文本只作为一个参数传给桥，再经 stdin 交给 `orca`，不经过 shell 解释。
- 同一时间只处理一条消息；结果不确定的请求不会重发。
- 发回钉钉的只有 bot 的回复和固定的报错文案，CLI 的原始输出和本地异常不会发出去。
- 桥不读取也不保存 AppSecret，凭证由 dws 通过 `--unified-app-id` 取用。
- 桥读 Orca 邮箱时不会把邮件标记为已读。

**只是告诉 bot（是否遵守取决于 bot）：**

- 把消息里引用或嵌入的指令当作不可信内容。
- 不把凭证、token、密钥，以及投资、邮件、健康方面的隐私放进钉钉回复；这类答案留在 Orca 里，
  在钉钉里只说明答案在 Orca。
- bot 被告知可以执行任何它在 Orca 里有权限执行的操作，仍受 Orca 现有的授权控制。

因此：

- 能登录你钉钉账号的人，就能指挥这个 bot。手机和钉钉账号要保管好。
- 问题和回复都会经过钉钉的服务器。不想离开本机的内容，不要通过这个桥问。
- 状态文件只存 Orca chat ID、请求 ID、终端句柄、邮箱序号和时间戳，不存消息内容。
  状态目录新建时权限是 `0700`，状态文件是 `0600`。

## 开发与测试

```sh
python3 -I -m unittest discover -s . -v
```

测试只用合成的 dws 调用和 Orca 邮件，不连钉钉，也不会给真实的 bot 发消息。其中有一项会用一个假的 `orca`
命令完整跑一遍第 4 步的 `handle` 调用；还有一项检查本文的[排错](#排错)和[配置](#配置)是否覆盖了
`bridge.py` 里的全部报错原文和环境变量，改代码时请同步改本文。

## 上游

Orca 原生钉钉连接器的需求见 [stablyai/orca#46800](https://github.com/stablyai/orca/issues/46800)。
在原生支持落地之前，这个仓库是一个只覆盖单人单聊的本地方案，不代表 Orca 官方。

## 许可

[MIT](LICENSE)
