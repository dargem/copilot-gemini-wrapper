from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import time
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()

    GEMINI_API_KEY = os.getenv("KEY_0")

    # Gemini endpoint that is compatible with the OpenAI schema
    GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Add proper selection later
    GEMINI_MODEL = "gemini-3.5-flash"
    body["model"] = GEMINI_MODEL

    async def stream_request():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                GEMINI_OPENAI_URL,
                json=body,
                headers=headers,
                timeout=60.0
            ) as response:
                async for chunk in response.aiter_bytes():
                    print(chunk)
                    yield chunk

    return StreamingResponse(stream_request(), media_type="text/event-stream")