"""Send one bounded smoke-test message to a local Ouroboros chat."""

from __future__ import annotations

import asyncio
import json
import uuid

import websockets


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8765/ws") as websocket:
        message_id = f"smoke-{uuid.uuid4().hex[:8]}"
        await websocket.send(
            json.dumps(
                {
                    "type": "chat",
                    "content": "Ответь ровно одним словом: РАБОТАЕТ",
                    "sender_session_id": "codex-smoke",
                    "client_message_id": message_id,
                    "chat_id": 1,
                }
            )
        )
        while True:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=90)
            message = json.loads(raw_message)
            if message.get("type") != "chat" or message.get("role") != "assistant":
                continue
            content = str(message.get("content") or "").strip()
            if content:
                print(content[:500])
                return


if __name__ == "__main__":
    asyncio.run(main())
