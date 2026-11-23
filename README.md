# DingTalk ↔ Orca local bridge

English · [简体中文](README.zh-CN.md)

Message your Orca bots from DingTalk. Each bridge instance connects one authorized
owner's 1:1 DingTalk chat to one local Orca bot and relays the bot's replies.
We use it to talk to our Orca bot from DingTalk on a phone while away from
the Mac running the bridge. The bridge needs no Orca changes or public endpoint.

## Prerequisites

- macOS or Linux, Python 3.10+, and a checkout whose absolute path has no whitespace
- Orca desktop running locally, the `orca` CLI on PATH, and a configured bot
- DingTalk Workspace CLI (`dws`) v1.0.68 and a DingTalk enterprise internal app
  with a Stream robot

The transport and allowlist contracts below were checked against dws v1.0.68.
The Orca command path was exercised with Orca CLI 1.4.268.

## Prepare the DingTalk app

1. In the [DingTalk Developer Console](https://open-dev.dingtalk.com/), select
   your organization and create an enterprise internal app (企业内部应用), for
   example **Orca Bridge**.
2. Open **Add Capability → Robot** (添加应用能力 → 机器人). Set the robot's
   message receiving mode (消息接收模式) to **Stream** and save. The custom
   connector subscribes to the robot message callback when it opens the Stream.
   Replies use the callback's session webhook. This route uses the robot
   capability and does not require a separate proactive-send API permission.
3. In **Version Management and Publishing** (版本管理与发布), set the app's
   visibility (可见范围) to your account for the first test, then publish. Have
   an organization administrator do this if you lack publishing access.
4. Authenticate dws for that organization and obtain the app's unified ID.
   For an app visible to dws, run `dws dev app list --name 'Orca Bridge'` and
   use its `unifiedAppId`. dws retrieves the robot credentials through
   `--unified-app-id`. Keep the AppSecret in DingTalk/dws credential storage.
   Passing a secret as a CLI flag exposes it in the local process list.

To get the only permitted staff ID, run this while dws is logged into the same
organization:

```sh
dws contact user get-self --jq '.result[0].orgEmployeeModel.userId'
```

## Run

In Orca, open the checkout and create a **new plain-shell terminal tab** for
the bridge. Run the launcher in the foreground in that tab. The Orca CLI
requires a live runtime-issued terminal handle, and bot answers return to
that terminal's orchestration mailbox. Keep the tab open for the connection's
lifetime.

```sh
export DINGTALK_OWNER_USER_ID='your-org-staff-id'
export DWS_ALLOWED_USERS="$DINGTALK_OWNER_USER_ID"
export ORCA_BRIDGE_BOT='Sto'  # Set this to your bot name if it differs.
python3 bridge.py start 'your-unified-app-id'
```

Send the robot a harmless question in a DingTalk direct chat. The bridge
passes the question to your bot and returns its reply. Press Ctrl-C
in the dedicated terminal to stop the bridge. Use the launcher as shown so
the same allowlists reach dws and the bridge.

## Access and session scope

dws enforces the sender allowlist against the callback's `senderStaffId`
before invoking the bridge. The launcher refuses empty or out-of-policy
`DWS_ALLOWED_USERS`, then passes the validated list to dws as environment
configuration. The bridge checks that configuration again at each invocation.
The only permitted staff ID is `DINGTALK_OWNER_USER_ID`. If upgrading from
a previous version, unset `DINGTALK_ALLOWED_USERS` and `ORCA_BRIDGE_GROUPS`
and leave `DWS_ALLOWED_GROUPS` unset or set to `none` before starting.

dws splits the configured agent command on whitespace, appends the message
as a single final argument, and gives the child closed stdin. Its custom
channel supplies neither the sender ID nor the conversation ID to the child.
The bridge therefore relies on dws for sender verification and uses one
Orca chat per configured app, bot, and permitted staff ID.

The launcher always sets dws's group allowlist to the sentinel `none`, which
makes the robot DM-only. dws custom commands supply no authenticated
conversation ID, so enabling multiple users or groups would allow a late
answer to be delivered to the next caller. This is a hard limitation of the
custom channel. A transport that supplies authenticated conversation metadata
is required before this bridge can safely support more than one user or any
group.

The bridge instructs the bot to treat quoted content as untrusted and permits
actions available to it in Orca under Orca's existing authorization controls.
If a reply would disclose credentials, tokens, secrets, or private information
about investments, email, or health, the prompt tells the bot to keep the answer
in Orca and say so in DingTalk.
The bridge relies on the bot to follow this instruction.

## Mail, state and errors

Orca accepts the question asynchronously and issues a request ID. The bridge
reads only the launching terminal's mailbox and matches the reply by request
ID. It remembers the Orca chat ID from the matching reply, so later messages
use that same chat. It never marks Orca mail read.

The state directory defaults to `~/.orca-dingtalk-bridge`. Set
`ORCA_BRIDGE_STATE_DIR` to choose another private directory. State files are
locked and written atomically.

The bridge waits up to 300 seconds for each answer (`ORCA_BRIDGE_TIMEOUT`, in
seconds). Bot turns that use tools can take minutes. In a sample of 61 local
Orca bot answers, the median was 68 seconds and 17 took over 120 seconds.
Set `ORCA_BRIDGE_TIMEOUT` before `python3 bridge.py start`. The launcher
passes that budget plus 15 seconds to dws as its per-call limit, so restart
the bridge to change it. A restart keeps the pending request, and Orca
1.4.268 still serves the earlier terminal's mailbox after that tab closes.

A timeout preserves the pending request and returns an error to DingTalk. The
timeout notice points to `重置` for clearing it after checking Orca.
Send any message later to collect the reply. The bridge returns the earlier
reply, labelled as such, and does not forward the message that collected it.
If the bot is still working, the error says that message was not forwarded.
To clear a pending request from DingTalk after checking Orca, send exactly
`重置`. The allowlisted sender receives a confirmation, and the reset message
is not forwarded. dws handles `/reset` itself by starting a new session, so it
does not clear the bridge's pending request. Use `重置` instead.
Once the previous reply has been recovered, a subsequent new message starts
another turn.

If Orca definitively refuses a send before delivery, the bridge clears it.
If the saved chat was rejected as missing, a later message opens a fresh
chat. Otherwise an unconfirmed send or unanswered question stays pending for
24 hours. After checking the Orca bot chat, send `重置` to clear
the pending record early. That message is not forwarded and the request is
not resent. The next message after expiry clears it and returns an expiry
notice. The bridge sends no question on that turn. Check the Orca bot chat
before repeating the earlier request, which may still be running there.

On success dws relays stdout through the session webhook. dws v1.0.68 renders
replies of more than 200 Unicode code points as Markdown and shorter replies
as plain text. On non-zero exit,
dws v1.0.68 sends up to 300 characters of stderr to that conversation. The
bridge returns short error messages through stderr and keeps raw CLI output
and local exceptions out of the reply.

## Tests

```sh
python3 -I -m unittest discover -s . -v
```

The tests use synthetic dws invocations and Orca mail records. To test only
the Orca half, use a dedicated Orca shell with synthetic allowlist values and
a temporary state directory, and invoke the handler as dws would:

```sh
(
  export DINGTALK_OWNER_USER_ID=synthetic DWS_ALLOWED_USERS=synthetic
  export DWS_ALLOWED_GROUPS=none
  export ORCA_BRIDGE_BOT='Sto'  # Set this to your bot name if it differs.
  export ORCA_BRIDGE_SCOPE="$(printf '%064d' 1)"
  export ORCA_BRIDGE_STATE_DIR="$(mktemp -d)"
  python3 -I bridge.py handle '--probe: reply with BRIDGE_OK using the question reply command.' </dev/null
)
```

This sends a real question to the configured Orca bot from that shell.
The DingTalk-to-Orca round trip was also verified in a live 1:1 chat.
