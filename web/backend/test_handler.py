"""Tests for the browser-to-AgentCore adapter."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import handler


class Stream:
    def __init__(self, lines):
        self.lines = lines

    def iter_lines(self, chunk_size=1024):
        return iter(self.lines)


class FakeAgentCoreClient:
    def invoke_agent_runtime(self, **kwargs):
        self.request = kwargs
        return {
            "response": Stream(
                [
                    b'data: {"event":{"contentBlockDelta":{"delta":{"text":"Your cost is "}}}}',
                    b'data: {"event":{"contentBlockDelta":{"delta":{"text":"$1.23."}}}}',
                ]
            )
        }


class HandlerTests(unittest.TestCase):
    def test_extract_answer_uses_only_text_deltas(self):
        result = handler.extract_answer(
            Stream(
                [
                    b'data: {"event":{"messageStart":{"role":"assistant"}}}',
                    b'data: {"event":{"contentBlockDelta":{"delta":{"text":"Hello"}}}}',
                    b'',
                    b'data: {"event":{"contentBlockDelta":{"delta":{"text":" world"}}}}',
                ]
            )
        )
        self.assertEqual(result, "Hello world")

    def test_handler_invokes_agentcore_with_user_scoped_session(self):
        client = FakeAgentCoreClient()
        event = {
            "body": '{"prompt":"What is my AWS month-to-date cost?", "sessionId":"browser-session"}',
            "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-123"}}}},
        }
        fake_boto = SimpleNamespace(client=lambda *_args, **_kwargs: client)

        with patch.object(handler, "boto3", fake_boto), patch.dict(
            handler.os.environ,
            {"AGENTCORE_REGION": "us-west-2", "AGENT_RUNTIME_ARN": "runtime-arn"},
            clear=False,
        ):
            result = handler.handler(event, None)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], '{"answer": "Your cost is $1.23."}')
        self.assertEqual(client.request["agentRuntimeArn"], "runtime-arn")
        self.assertEqual(client.request["qualifier"], "DEFAULT")
        self.assertEqual(client.request["runtimeSessionId"], handler.runtime_session_id("user-123", "browser-session"))

    def test_handler_rejects_an_empty_prompt(self):
        result = handler.handler({"body": '{"prompt":" "}'}, None)
        self.assertEqual(result["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
