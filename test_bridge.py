import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge import Bridge, allowed_user, format_reply, parse_event


class BridgeTests(unittest.TestCase):
    def test_parse_synthetic_direct_event(self):
        event = parse_event([], {}, json.dumps({"text": "hello", "senderStaffId": "u1", "openConversationId": "c1"}))
        self.assertEqual(event["text"], "hello")
        self.assertEqual(event["conversation_id"], "c1")

    def test_group_requires_mention(self):
        event = parse_event([], {}, json.dumps({"text": "hello", "senderUserId": "u1", "openConversationId": "g1", "isGroup": True}))
        self.assertTrue(event["ignore"])

    def test_allowlist_defaults_to_owner_and_explicit_list(self):
        self.assertTrue(allowed_user("owner", {"DINGTALK_OWNER_USER_ID": "owner"}))
        self.assertFalse(allowed_user("other", {"DINGTALK_OWNER_USER_ID": "owner"}))
        self.assertTrue(allowed_user("u2", {"DINGTALK_ALLOWED_USERS": "u1,u2"}))

    def test_mapping_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            bridge = Bridge(path, timeout=0.01)
            with patch.object(bridge, "_send", side_effect=["r1", "r2"]) as send, patch.object(
                bridge, "_answer", return_value="**ok**"
            ), patch("subprocess.run") as run:
                run.return_value.stdout = json.dumps({"result": {"chats": [{"id": "chat-1", "title": "DingTalk bridge"}]}})
                self.assertEqual(bridge.ask("c1", "first"), "**ok**")
                self.assertEqual(bridge.ask("c1", "second"), "**ok**")
                self.assertEqual(send.call_args_list[1].args[0], "second")
                self.assertIn("chat-1", path.read_text())

    def test_reply_format(self):
        self.assertEqual(format_reply("  # hello  "), "# hello")


if __name__ == "__main__":
    unittest.main()
