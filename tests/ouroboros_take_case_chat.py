"""Verify that a bare CasePilot case_id triggers the operator workflow in Chat."""

from __future__ import annotations

import asyncio
import json
import uuid

import websockets


async def main() -> None:
    message_id = f"take-case-{uuid.uuid4().hex[:8]}"
    async with websockets.connect(
        "ws://127.0.0.1:8765/ws",
        max_size=16 * 1024 * 1024,
        ping_timeout=60,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "chat",
                    "content": "VAL-DC-002",
                    "sender_session_id": "codex-casepilot-test",
                    "client_message_id": message_id,
                    "chat_id": 915,
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=420)
            message = json.loads(raw)
            if message.get("type") != "chat" or message.get("role") != "assistant":
                continue
            content = str(message.get("content") or "").strip()
            expected = (
                "VAL-DC-002",
                "Подтверждаю",
                "Изменить:",
                "Беру вручную",
            )
            if content and all(marker in content for marker in expected):
                print(content)
                print(
                    "TAKE_CASE_CHAT_OK "
                    + json.dumps(
                        {
                            "task_id": message.get("task_id"),
                            "client_message_id": message_id,
                        }
                    )
                )
                return


if __name__ == "__main__":
    asyncio.run(main())

