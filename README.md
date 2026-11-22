# DingTalk ↔ Orca local bridge

Relay DingTalk robot messages to a local Orca bot and return its answer as
Markdown in the originating DingTalk chat. The bridge runs on your machine as
an independent integration and needs no Orca changes or public endpoint.

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
passes the question to your bot and returns its Markdown reply. Press Ctrl-C
in the dedicated terminal to stop the bridge. Use the launcher as shown so
the same allowlists reach dws and the bridge.

## Access and session scope

dws enforces the sender allowlist against the callback's `senderStaffId`
before invoking the bridge. The launcher refuses empty or out-of-policy
`DWS_ALLOWED_USERS`, then passes the validated list to dws as environment
configuration. The bridge checks that configuration again at each invocation.
By default the bridge allowlist contains only `DINGTALK_OWNER_USER_ID`. To
authorize more staff IDs, set `DINGTALK_ALLOWED_USERS` to a comma-separated
list and set `DWS_ALLOWED_USERS` to the members of that list who should have
access.

dws splits the configured agent command on whitespace, appends the message
as a single final argument, and gives the child closed stdin. Its custom
channel supplies neither the sender ID nor the conversation ID to the child.
The bridge therefore relies on dws for sender verification and shares one
Orca chat per configured app, bot, and set of allowed users and groups.
Separate DingTalk conversation history requires a transport that supplies
authenticated conversation metadata.

The default group allowlist is the sentinel `none`, which makes the robot
DM-only. To allow group @-mentions, set `ORCA_BRIDGE_GROUPS` to a
comma-separated list of DingTalk group `openConversationId` values and restart.
Every member of an enabled group can see replies there, and context from
other enabled entry points can influence those replies. Use a dedicated bot
with permissions appropriate to that audience. An allowed sender can reach
the bot with the bot's configured capabilities.

## Mail, state and errors

Orca accepts the question asynchronously and issues a request ID. The bridge
reads only the launching terminal's mailbox and matches the reply by request
ID. It remembers the Orca chat ID from the matching reply, so later messages
use that same chat. It never marks Orca mail read.

The state directory defaults to `~/.orca-dingtalk-bridge`. Set
`ORCA_BRIDGE_STATE_DIR` to choose another private directory. State files are
locked and written atomically. The wait budget defaults to 120 seconds
(`ORCA_BRIDGE_TIMEOUT`, in seconds). Timeouts preserve the pending request.
When another DingTalk message arrives, the bridge checks for the earlier
reply and labels it as such. That incoming message is not forwarded. Once
the previous reply has been recovered, a subsequent new message starts
another turn.

If the previous send is unconfirmed, the bot chat was closed, or the saved
mailbox is no longer accessible, stop the connector and inspect the Orca bot
chat before resetting state. Once you have accounted for the earlier request,
move the old state directory aside or select a fresh private state directory
and restart. The next turn creates a new Orca chat.

On success dws relays stdout through the session webhook. On non-zero exit,
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
export DINGTALK_OWNER_USER_ID=synthetic DWS_ALLOWED_USERS=synthetic
export DWS_ALLOWED_GROUPS=none
export ORCA_BRIDGE_SCOPE="$(printf '%064d' 1)"
export ORCA_BRIDGE_STATE_DIR="$(mktemp -d)"
python3 -I bridge.py handle '--probe: reply with BRIDGE_OK using the question reply command.' </dev/null
```

This sends a real question to the configured Orca bot from that shell.
A live DingTalk round trip is still pending a configured app.
