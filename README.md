# DingTalk ↔ Orca local bridge

This is a small, open-source local adapter. It lets a DingTalk Stream robot pass an allowed user's direct message, or a group @-mention, to one Orca bot and prints the bot's Markdown answer for `dws` to send back. It is not an official Orca connector, does not modify Orca, and does not use Stably's closed cloud service.

## Prerequisites

- macOS or Linux with Python 3.10+
- Orca CLI installed and logged in, with a bot such as `Sto`
- `dws` v1.0.68 or newer
- A DingTalk enterprise internal app with a robot using Stream mode

The verified `dws` contract is `dws dev connect --channel custom --agent-cmd "<command>"`: each incoming question is appended as the command's final argument, and the command's stdout is sent to DingTalk through the Stream session webhook. `dws --dry-run` describes this as `收到消息 → 运行 <你的命令> "用户问题" → stdout 作为回复`.

The bridge invokes `orca orchestration send --to bot:<name> --chat <id|new> --type question`. Orca returns a request ID immediately and delivers the bot answer as mail. The bridge polls `orca orchestration inbox --json --full` for that request ID. This is a local synchronous wait, with a configurable timeout.

## DingTalk app setup

In DingTalk Developer Console, create one enterprise internal app and add a robot. Enable Stream mode for the robot and subscribe to robot message events. Grant the robot's message receive and send permissions requested by the console. Publish the app to the organization, then obtain its AppKey and AppSecret or the credentials supported by your installed `dws` version. Keep credentials in `dws`'s config or environment, never in this repository.

Creating or publishing an app requires the organization's administrator. This repository does not create the app and the live test was not run against DingTalk.

## Configure and run

Set an allowlist. The explicit list wins. If it is absent, `DINGTALK_OWNER_USER_ID` (or `DWS_OWNER_USER_ID`) is the sole allowed user. With no owner configured, all users are refused.

```sh
export DINGTALK_OWNER_USER_ID='your-staff-id'
# Optional: export DINGTALK_ALLOWED_USERS='your-staff-id,another-staff-id'
export ORCA_BRIDGE_BOT='Sto'                 # default Sto
export ORCA_BRIDGE_STATE_FILE="$HOME/.orca-dingtalk-bridge/state.json"
export ORCA_BRIDGE_TIMEOUT=120               # seconds

dws dev connect --channel custom \
  --allowed-users "$DINGTALK_OWNER_USER_ID" \
  --agent-cmd "python3 /absolute/path/to/bridge.py" \
  --unified-app-id '<dws unified app id>'
```

The `--allowed-users` flag is an additional dws-side gate and should be set whenever the dws version supports it. The bridge repeats the check when sender metadata is available to the command.

Use `--robot-client-id` and `--robot-client-secret` when that is how your `dws` installation is configured. The state file maps each DingTalk conversation to an Orca bot chat and is created atomically. It is ignored by Git. `DWS_SESSION_ID` is used as a fallback conversation key when a custom adapter does not provide an open conversation ID. For synthetic integrations, pass a JSON event on stdin with `text`, `senderStaffId`, `openConversationId`, and optional group/mention fields.

## Tests

```sh
python3 -m unittest -v
```

The tests cover event normalization, group mention filtering, allowlist behavior, Markdown reply formatting, and persistent conversation-to-chat reuse. The live Orca path was verified separately with a real `orca orchestration send --to bot:Sto --chat new` request and the matching mail answer. DingTalk delivery remains untested until an administrator creates and publishes the app.

## Limits

The bridge is intentionally local and single-process. It does not provide a web server, queue, retries across crashes, attachments, cards, rich media, or multi-bot routing. Orca's mail inbox is polled by request ID, so a long-running bot response waits up to `ORCA_BRIDGE_TIMEOUT`. Protect the state file and host because it identifies conversation-to-chat mappings.
