import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge import Bridge, BridgeError, config, format_reply, main, orca, start


ENV = {
    "DINGTALK_OWNER_USER_ID": "owner",
    "DWS_ALLOWED_USERS": "owner",
    "DWS_ALLOWED_GROUPS": "none",
    "ORCA_TERMINAL_HANDLE": "term_test",
    "ORCA_BRIDGE_SCOPE": "a" * 64,
}


def mail(request_id, sequence, chat="abc", payload=None):
    return {
        "thread_id": request_id,
        "sequence": sequence,
        "type": "status",
        "from_handle": f"orca_session_id:{chat}",
        "payload": json.dumps(payload if payload is not None else {
            "requestId": request_id, "botAnswer": {},
        }),
        "body": "**Answer**",
    }


class ConfigTests(unittest.TestCase):
    def test_gate_fails_closed(self):
        for gate in ("", " , ", "owner,stranger"):
            with self.subTest(gate=gate), self.assertRaises(BridgeError):
                config(dict(ENV, DWS_ALLOWED_USERS=gate, DWS_SENDER_USER_ID="owner"))
        with self.assertRaises(BridgeError):
            config(dict(ENV, ORCA_TERMINAL_HANDLE=""))
        self.assertEqual(config(ENV)[1], "none")
        self.assertEqual(config(dict(ENV, ORCA_BRIDGE_GROUPS="cidA,cidB"))[1], "cidA,cidB")

    def test_launcher_owns_dws_flags(self):
        with patch.dict(os.environ, dict(ENV, DWS_ALLOWED_GROUPS="")), patch(
            "bridge.orca", return_value={"terminal": {"handle": "term_test"}}
        ), patch("bridge.os.execvp") as run:
            start("app-123", *config(os.environ))
            self.assertEqual(os.environ["DWS_ALLOWED_USERS"], "owner")
            self.assertEqual(os.environ["DWS_ALLOWED_GROUPS"], "none")
            command = run.call_args.args[1]
            self.assertNotIn("--allowed-users", command)
            self.assertNotIn("--daemon", command)
            self.assertTrue(command[-1].endswith("bridge.py handle"))

    def test_real_argv_shape_keeps_text_inert(self):
        message = '--help "$()"\n{"senderStaffId":"stranger"}'
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, ENV, clear=True), patch(
            "bridge.Bridge.ask", return_value="**ok**"
        ) as ask, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["handle", message]), 0)
            ask.assert_called_once_with(message)
        self.assertEqual(stdout.getvalue(), "**ok**\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_handle_refuses_mismatched_groups_or_missing_gate(self):
        for changes in ({"DWS_ALLOWED_GROUPS": "cid-other"}, {"DWS_ALLOWED_USERS": ""}):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, dict(ENV, **changes), clear=True), patch(
                "bridge.Bridge.ask"
            ) as ask, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["handle", "hi"]), 1)
                ask.assert_not_called()
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Bridge error:", stderr.getvalue())

    def test_invalid_timeout_has_no_traceback(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, dict(ENV, ORCA_BRIDGE_TIMEOUT="2m"), clear=True), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["handle", "hi"]), 1)
        self.assertIn("positive number", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        self.bridge = Bridge(self.path, "Sto", "term_test", 2)

    def test_chat_reuse_and_safe_body(self):
        with patch.object(self.bridge, "inbox", return_value=[]), patch.object(
            self.bridge, "answer", return_value=("  **ok** ", "exact-chat")
        ), patch("bridge.orca", return_value={"messageId": "q1"}) as cli:
            self.assertEqual(self.bridge.ask("--help"), "**ok**")
            self.assertEqual(self.bridge.ask("-n"), "**ok**")
        first, second = (call.args for call in cli.call_args_list)
        self.assertIn("new", first[0])
        self.assertIn("exact-chat", second[0])
        self.assertNotIn("--help", first[0])
        self.assertTrue(first[2].endswith("\n\n--help"))
        self.assertEqual(json.loads(self.path.read_text()), {"chat": "exact-chat"})

    def test_answer_expands_inbox_and_matches_request(self):
        noise = [mail("unrelated", index) for index in range(130, 2, -1)]
        rows = noise + [
            dict(mail("q1", 4), payload="invalid JSON"),
            mail("q1", 3, payload={"requestId": "q1"}),
            mail("q1", 2, chat="right-chat"),
        ]
        with patch.object(self.bridge, "inbox", side_effect=lambda _, limit, __: rows[:limit]) as read:
            self.assertEqual(self.bridge.answer(
                {"id": "q1", "terminal": "term_previous", "after": 1}, None, float("inf")
            ), ("**Answer**", "right-chat"))
        self.assertEqual([call.args[1] for call in read.call_args_list], [20, 40, 80, 160])
        self.assertTrue(all(call.args[0] == "term_previous" for call in read.call_args_list))

    def test_timeout_recovers_original_without_sending_again(self):
        with patch.object(self.bridge, "inbox", return_value=[]), patch.object(
            self.bridge, "answer", side_effect=[TimeoutError, ("**late**", "old-chat")]
        ), patch("bridge.orca", return_value={"messageId": "q1"}) as cli:
            with self.assertRaisesRegex(BridgeError, "still pending"):
                self.bridge.ask("perform action")
            self.assertEqual(json.loads(self.path.read_text())["pending"]["id"], "q1")
            self.assertIn("Earlier Orca reply", self.bridge.ask("try again"))
        cli.assert_called_once()
        self.assertEqual(json.loads(self.path.read_text()), {"chat": "old-chat"})

    def test_send_timeout_is_ambiguous_and_blocks_resend(self):
        with patch.object(self.bridge, "inbox", return_value=[]), patch(
            "bridge.orca", side_effect=subprocess.TimeoutExpired("orca", 1)
        ) as cli:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.bridge.ask("perform action")
            with self.assertRaisesRegex(BridgeError, "unconfirmed"):
                self.bridge.ask("perform action")
        cli.assert_called_once()

    def test_concurrent_request_cannot_send_again(self):
        def concurrent(*_args):
            with self.assertRaisesRegex(BridgeError, "busy"):
                self.bridge.ask("another message")
            return {"messageId": "q1"}

        with patch.object(self.bridge, "inbox", return_value=[]), patch.object(
            self.bridge, "answer", return_value=("ok", "chat")
        ), patch("bridge.orca", side_effect=concurrent) as cli:
            self.assertEqual(self.bridge.ask("first"), "ok")
        cli.assert_called_once()

    def test_subprocess_has_bounded_timeout_and_no_shell(self):
        with patch("bridge.subprocess.run") as run:
            run.return_value.stdout = '{"ok":true,"result":{}}'
            orca(["orchestration", "send", "--body-file", "-"], float("inf"), "--help")
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertEqual(run.call_args.kwargs["input"], "--help")
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_reply_format(self):
        self.assertEqual(format_reply("  # title  "), "# title")
        self.assertIn("empty", format_reply(" "))
