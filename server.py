from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import time
import httpx
import os
from dotenv import load_dotenv

from model_manager import ModelManager, APIRecord

load_dotenv()

app = FastAPI()
thought_signatures: dict[str, str] = {}
THOUGHT_SIGNATURE_SENTINEL = "skip_thought_signature_validator"

model_manager = ModelManager()

def inject_signatures(body: dict) -> None:
    for message in body.get("messages", []):
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls", []) or []:
            signature = thought_signatures.get(tool_call.get("id"), THOUGHT_SIGNATURE_SENTINEL)
            if signature == THOUGHT_SIGNATURE_SENTINEL:
                print("WARNING: Falling back to sentinel")
            tool_call.setdefault("extra_content", {}).setdefault("google", {})["thought_signature"] = signature

def capture_signatures(parsed_chunk: dict, index_to_id: dict):
    choices = parsed_chunk.get("choices", [])

    if not choices:
        return
    
    for tc in choices[0].get("delta", {}).get("tool_calls", []) or []:
        idx = tc.get("index")
        if "id" in tc:
            index_to_id[idx] = tc["id"]
        sig = tc.get("extra_content", {}).get("google", {}).get("thought_signature")
        if (sig):
            tc_id = tc.get("id") or index_to_id.get(idx)
            if tc_id:
                thought_signatures[tc_id] = sig

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    inject_signatures(body)

    # Gemini endpoint that is compatible with the OpenAI schema
    GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"

    # After reserving we need to return the APIRecord with used tokens
    api_record: APIRecord = model_manager.reserve_best_model()

    body["model"] = api_record.model
    headers = {
        "Authorization": f"Bearer {api_record.key}",
        "Content-Type": "application/json"
    }
    body["stream_options"] = {"include_usage": True}

    async def stream_request(record):
        index_to_id: dict[int, str] = {}
        total_tokens = 0
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    GEMINI_OPENAI_URL,
                    json=body,
                    headers=headers,
                    timeout=60.0
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        print(f"GEMINI ERROR {response.status_code}: {error_body.decode()}")
                        return
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                capture_signatures(json.loads(line[6:]), index_to_id)
                            except json.JSONDecodeError:
                                pass
                        yield (line + "\n").encode()
        finally:
            # add some error checking later
            model_manager.finalize(record, total_tokens)

    return StreamingResponse(stream_request(api_record), media_type="text/event-stream")