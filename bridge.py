#!/usr/bin/env python3
"""Small stdlib bridge between dws custom Stream commands and an Orca bot."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REFUSAL = "抱歉，你没有权限使用这个机器人。"
NO_MENTION = ""


def _first(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_event(argv: list[str], env: dict[str, str] | None = None, stdin: str = "") -> dict[str, Any]:
    """Normalize a synthetic JSON event or dws's final argv prompt."""
    env = env or os.environ
    raw = stdin.strip()
    event: dict[str, Any] = {}
    if raw:
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, dict):
                event = candidate
        except json.JSONDecodeError:
            pass
    text = _first(event, "text", "content", "message") or (argv[-1] if argv else "")
    user_id = _first(event, "senderStaffId", "senderUserId", "userId", "sender_id") or _first(
        env, "DINGTALK_SENDER_USER_ID", "DWS_SENDER_USER_ID", "DWS_USER_ID"
    )
    conversation_id = _first(
        event, "openConversationId", "conversationId", "conversation_id", "chatId"
    ) or _first(env, "DINGTALK_OPEN_CONVERSATION_ID", "DWS_OPEN_CONVERSATION_ID", "DWS_SESSION_ID")
    is_group = bool(event.get("isInAtList") is not None and event.get("isInAtList")) or bool(
        event.get("conversationType") in ("2", 2, "group")
    ) or bool(event.get("isGroup"))
    mentioned = bool(event.get("isInAtList") or event.get("atBot") or event.get("mentioned"))
    if is_group and not mentioned:
        return {"text": text, "user_id": user_id, "conversation_id": conversation_id, "ignore": True}
    return {"text": text, "user_id": user_id, "conversation_id": conversation_id, "ignore": False}


def allowed_user(user_id: str, env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    configured = env.get("DINGTALK_ALLOWED_USERS", "").strip()
    if configured:
        allowed = {item.strip() for item in configured.split(",") if item.strip()}
    else:
        owner = env.get("DINGTALK_OWNER_USER_ID") or env.get("DWS_OWNER_USER_ID", "")
        allowed = {owner.strip()} if owner.strip() else set()
    return bool(user_id and user_id in allowed)


def format_reply(answer: str) -> str:
    """Return bot output as Markdown while avoiding accidental blank replies."""
    answer = answer.strip()
    return answer or "机器人没有返回内容。"


class Bridge:
    def __init__(self, state_file: Path, bot: str = "Sto", timeout: float = 120.0):
        self.state_file = state_file
        self.bot = bot
        self.timeout = timeout

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"conversations": {}}
        except (FileNotFoundError, json.JSONDecodeError):
            return {"conversations": {}}

    def _save(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="state-", dir=self.state_file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.state_file)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _send(self, text: str, chat: str | None) -> str:
        subject = "DingTalk bridge"
        command = ["orca", "orchestration", "send", "--to", f"bot:{self.bot}", "--type", "question", "--subject", subject, "--body", text, "--json"]
        command += ["--chat", chat or "new"]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        return str(payload["result"]["messageId"])

    def _answer(self, request_id: str) -> str:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["orca", "orchestration", "inbox", "--json", "--full", "--limit", "100"],
                check=True,
                capture_output=True,
                text=True,
            )
            messages = json.loads(result.stdout).get("result", {}).get("messages", [])
            for message in messages:
                payload = message.get("payload")
                try:
                    payload = json.loads(payload) if isinstance(payload, str) else payload
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict) and payload.get("requestId") == request_id:
                    return str(message.get("body", ""))
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for Orca request {request_id}")

    def ask(self, conversation_id: str, text: str) -> str:
        state = self._load()
        conversations = state.setdefault("conversations", {})
        entry = conversations.get(conversation_id, {})
        chat = entry.get("chat_id")
        request_id = self._send(text, chat)
        answer = self._answer(request_id)
        if not chat:
            chats = subprocess.run(
                ["orca", "bot", "chats", "--bot", self.bot, "--json"],
                check=True,
                capture_output=True,
                text=True,
            )
            rows = json.loads(chats.stdout).get("result", {}).get("chats", [])
            matching = [row for row in rows if row.get("title") == "DingTalk bridge"]
            if matching:
                conversations[conversation_id] = {"chat_id": matching[-1]["id"]}
                self._save(state)
        return format_reply(answer)


def main() -> int:
    event = parse_event(sys.argv[1:], stdin=sys.stdin.read())
    if event.get("ignore"):
        return 0
    if not allowed_user(event["user_id"]):
        print(REFUSAL)
        return 0
    conversation_id = event["conversation_id"] or event["user_id"]
    if not conversation_id:
        print("无法识别会话。请配置 DINGTALK_OPEN_CONVERSATION_ID。")
        return 0
    state_file = Path(os.environ.get("ORCA_BRIDGE_STATE_FILE", "~/.orca-dingtalk-bridge/state.json")).expanduser()
    bot = os.environ.get("ORCA_BRIDGE_BOT", "Sto")
    timeout = float(os.environ.get("ORCA_BRIDGE_TIMEOUT", "120"))
    try:
        print(Bridge(state_file, bot, timeout).ask(conversation_id, event["text"]))
    except (OSError, subprocess.SubprocessError, ValueError, TimeoutError, KeyError) as exc:
        print(f"桥接暂时不可用：{type(exc).__name__}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
