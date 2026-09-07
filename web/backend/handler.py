"""Authenticated browser API for the AWS Cost Assistant.

The Lambda function validates a small request shape, creates an AgentCore
session that is unique to the signed-in user, and turns the runtime's SSE
response into one JSON answer for the browser. The browser has no AWS keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # Lets the parser helpers be tested without an AWS SDK installed.
    boto3 = None
    BotoCoreError = ClientError = Exception


MAX_PROMPT_LENGTH = 1_000
SESSION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body),
    }


def runtime_session_id(user_id: str, browser_session_id: str) -> str:
    """Create a stable, opaque AgentCore session ID scoped to one user."""
    return hashlib.sha256(f"{user_id}:{browser_session_id}".encode("utf-8")).hexdigest()


def extract_answer(runtime_response: Any) -> str:
    """Extract Strands text deltas from AgentCore's text/event-stream response."""
    text_parts: list[str] = []
    for raw_line in runtime_response.iter_lines(chunk_size=1024):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:]).get("event", {})
        except json.JSONDecodeError:
            continue
        delta = event.get("contentBlockDelta", {}).get("delta", {})
        if isinstance(delta.get("text"), str):
            text_parts.append(delta["text"])
    return "".join(text_parts).strip()


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})

    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return response(400, {"error": "Enter a question about AWS cost."})
    if len(prompt) > MAX_PROMPT_LENGTH:
        return response(400, {"error": f"Questions must be {MAX_PROMPT_LENGTH} characters or fewer."})

    browser_session_id = body.get("sessionId") or str(uuid.uuid4())
    if not isinstance(browser_session_id, str) or not SESSION_KEY_PATTERN.fullmatch(browser_session_id):
        return response(400, {"error": "Invalid browser session."})

    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        return response(401, {"error": "Sign in before asking a question."})

    if boto3 is None:
        return response(500, {"error": "The API is missing its AWS SDK dependency."})

    try:
        client = boto3.client("bedrock-agentcore", region_name=os.environ["AGENTCORE_REGION"])
        runtime_response = client.invoke_agent_runtime(
            agentRuntimeArn=os.environ["AGENT_RUNTIME_ARN"],
            runtimeSessionId=runtime_session_id(user_id, browser_session_id),
            payload=json.dumps({"prompt": prompt.strip()}).encode("utf-8"),
            qualifier="DEFAULT",
        )
        answer = extract_answer(runtime_response["response"])
    except (BotoCoreError, ClientError, KeyError) as error:
        print(f"AgentCore invocation failed: {error}")
        return response(502, {"error": "The cost assistant could not answer right now. Try again shortly."})

    if not answer:
        return response(502, {"error": "The cost assistant returned an empty response. Try again shortly."})

    return response(200, {"answer": answer})
