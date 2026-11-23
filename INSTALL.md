# Agent setup guide

This guide is for a coding agent (Claude Code, Codex, or similar) running in
Orca on the human's Mac. Follow the steps in order. Do not move on until a
step's **Done when** check passes. At each **STOP**, ask the human the question
shown, wait for the answer, and then continue.

Rules for the whole run:

- Never ask for, print, store, or pass the DingTalk AppSecret (Client Secret).
  dws reads the robot credentials itself through `--unified-app-id`. Do not run
  `dws dev app credentials get`, and do not use `--robot-client-secret` or
  `--client-secret`.
- Do not write the staff ID, the unified app ID, or any secret into files in
  the checkout.
- Use only the commands in this guide and in the READMEs. If a command prints
  a `Bridge error:` line, find that text in the troubleshooting table
  ([README.zh-CN.md#排错](README.zh-CN.md#排错); the error strings there are
  the exact English text) before trying anything else. Step numbers in that
  table refer to the Chinese README, not to this guide.
- Do not upgrade, install, or reconfigure dws or Orca unless the human asks.

## 1. Check prerequisites

```sh
sw_vers -productName   # macOS
python3 --version      # 3.10 or later
orca --version         # verified with 1.4.268
dws version            # verified with v1.0.68
orca bot list          # bots on this Mac
```

If `dws` is missing, STOP and ask the human to install the DingTalk Workspace
CLI (`dws`). If `orca` is missing, STOP and ask the human to start Orca and put
its CLI on PATH. Other versions may work but were not verified; tell the human
if yours differ.

If `dws version` suggests an upgrade, mention it to the human but do not run
`dws upgrade` yourself.

**Done when:** `sw_vers` prints `macOS`, Python is 3.10 or later, the other
commands print a version or a list, and `orca bot list` shows at least one bot.
If Python is older than 3.10, STOP and ask the human to install a newer
`python3`.

**STOP:** show the human the bot names from `orca bot list` and ask: "Which
Orca bot should answer your DingTalk messages?" Remember the answer as the bot
name.

## 2. Get the code

Skip the clone if you are already in a checkout of this repository.

```sh
git clone https://github.com/stone16/orca-dingtalk-bridge.git
cd orca-dingtalk-bridge
pwd
```

**Done when:** the `pwd` output contains no whitespace. The launcher refuses a
checkout path with whitespace.

## 3. Create the DingTalk app (human only)

**STOP:** ask the human to do this in the
[DingTalk Developer Console](https://open-dev.dingtalk.com/) and tell you when
it is done:

1. Select the organization and create an enterprise internal app
   (企业内部应用), for example **Orca Bridge**.
2. Open **Add Capability → Robot** (添加应用能力 → 机器人), set the message
   receiving mode (消息接收模式) to **Stream**, and save.
3. In **Version Management and Publishing** (版本管理与发布), set the
   visibility (可见范围) to only the human for the first test, then publish. An organization
   administrator may have to publish it.

Ask: "Is the app created, its robot set to Stream mode, and the app published
with you in its visibility? What is the app's name?"

**Done when:** the human confirms all three and gives the app name.

## 4. Log in to dws (human only)

```sh
dws auth status --readonly
```

If this shows no valid login for the app's organization, **STOP** and ask the
human to run `dws auth login` themselves in a terminal and finish the browser
authorization or QR scan, logged into the organization that owns the app.
Then run `dws auth status` again.

**Done when:** `dws auth status` shows a valid login for the app's
organization.

## 5. Look up the two IDs

```sh
dws dev app list --name 'Orca Bridge'   # use the app name from step 3
dws contact user get-self --jq '.result[0].orgEmployeeModel.userId'
```

- The **unified app ID** is the `unifiedAppId` field of the app in the first
  output. If more than one app matches the name, **STOP** and ask the human
  which one they created in step 3.
- The **staff ID** is the value from the second command, without quotes.

If the app is missing from the list, **STOP** and ask the human to check that
the app is published, that they are in its visibility, and that dws is logged
into the same organization.

**STOP:** show the human the staff ID and ask: "This is the only DingTalk
account that will be allowed to message the bridge. Is it yours?" If they say
no, dws is logged into the wrong account or organization; go back to step 4.

**Done when:** you have the unified app ID and a staff ID the human confirmed.

## 6. Open a dedicated Orca terminal (human only)

The bridge must run in the foreground of a **plain-shell** Orca terminal tab.
It refuses to start in an agent pane, including the one you are running in.
Agent panes also have a `term_` handle, so you cannot tell the two apart from
your own pane.

**STOP:** ask the human to create a new plain-shell terminal tab in Orca (not
a Claude, Codex, or other agent tab), keep it open, and run the commands you
give them in steps 7 and 8 there.

**Done when:** the human confirms the tab is a plain shell and this prints a
handle that starts with `term_`:

```sh
echo "$ORCA_TERMINAL_HANDLE"
```

If the tab is an agent pane after all, step 8 fails with
`Start the bridge in a live, plain-shell Orca terminal.`

## 7. Self-check the Orca half

In steps 7 and 8, every `<...>` placeholder is inside single quotes. If a value
contains a single quote, write it as `'\''` so the command stays valid.

Fill in the bot name and the checkout path, then give the human this block to
paste into the new tab. It sends one real question to the bot, with synthetic
allowlist values and a temporary state directory. It does not connect to
DingTalk.

```sh
cd '<checkout path>'
(
  export DINGTALK_OWNER_USER_ID=synthetic DWS_ALLOWED_USERS=synthetic DWS_ALLOWED_GROUPS=none
  export ORCA_BRIDGE_BOT='<bot name>'
  export ORCA_BRIDGE_SCOPE="$(printf '%064d' 1)"
  export ORCA_BRIDGE_STATE_DIR="$(mktemp -d)"
  python3 -I bridge.py handle '--probe: reply with BRIDGE_OK using the question reply command.' </dev/null
)
```

**Done when:** the bot's reply, printed in that terminal, contains
`BRIDGE_OK`. It can take up to 300 seconds. On a `Bridge error:` line, look up
the exact text in either half of the troubleshooting table; the
startup-time causes are the likely ones here.

## 8. Start the bridge

Fill in the staff ID, bot name, and unified app ID, then give the human this
block to paste into the same tab:

```sh
export DINGTALK_OWNER_USER_ID='<staff ID>'
export DWS_ALLOWED_USERS="$DINGTALK_OWNER_USER_ID"
export ORCA_BRIDGE_BOT='<bot name>'
python3 bridge.py start '<unified app ID>'
```

Set `ORCA_BRIDGE_BOT` even if the bot is called `Sto`; the default is the
author's bot name.

**Done when:** the human reports that no `Bridge error:` line appeared and the
process stays in the foreground, held by dws's Stream connection. Ctrl-C in that tab stops the bridge.

## 9. Final check (human only)

**STOP:** ask the human to find the robot in DingTalk (search for the app
name), open a 1:1 chat with it, and send a harmless question.

**Done when:** the human gets the bot's reply in that DingTalk chat. Replies
of 200 characters or fewer are plain text; longer ones are Markdown.

If nothing comes back, check that the bridge tab is still running, that the
staff ID matches step 5, that the app is published with the human in its
visibility, and that dws is logged into the app's organization. For a
`Bridge error:` reply, use the troubleshooting table. A late reply is not an
error: the bridge waits up to 5 minutes, and the next message collects a late
reply. Sending `重置` clears a stuck request after checking Orca.

Tell the human that setup is complete, and that group chats and other users
are not supported by design.
