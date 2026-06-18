from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import httpx
from dotenv import load_dotenv
from logger import Logger, LogLevel
from model_manager import ModelManager, APIRecord
from contextlib import asynccontextmanager

load_dotenv()

app = FastAPI()
thought_signatures: dict[str, str] = {}
THOUGHT_SIGNATURE_SENTINEL = "skip_thought_signature_validator"

model_manager = ModelManager()
logger = Logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logger.log(LogLevel.INFO, "Shutting down and saving models")
    model_manager.save()

app = FastAPI(lifespan=lifespan)
# def shutdown_hook():
#     logger.log(LogLevel.INFO, "Shutting down and saving models")
#     model_manager.save()

# atexit.register(shutdown_hook)

# def signal_handler(signum, frame):
#     logger.log(LogLevel.INFO, f"Interrupted by system signal: {signum} delegating shutdown to hook")

# signal.signal(signal.SIGINT, signal_handler)
# signal.signal(signal.SIGTERM, signal_handler)


def inject_signatures(body: dict) -> None:
    for message in body.get("messages", []):
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls", []) or []:
            signature = thought_signatures.get(tool_call.get("id"), THOUGHT_SIGNATURE_SENTINEL)
            if signature == THOUGHT_SIGNATURE_SENTINEL:
                logger.log(LogLevel.WARNING, "Falling back to sentinel for a function signature")
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
    logger.log(LogLevel.INFO, "Starting chat completion request")
    body = await request.json()
    inject_signatures(body)

    # Gemini endpoint that is compatible with the OpenAI schema
    GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"

    def record_errors(record: APIRecord, error: str, status_code):
        known_error_noted = False

        if "GenerateRequestsPerDay" in error:
            known_error_noted = True
            record.record.RPD_error = True
        if "GenerateRequestsPerMinute" in error:
            known_error_noted = True
            record.record.RPM_error = True
        if ("GenerateContentInputTokens") in error:
            known_error_noted = True
            record.record.TPM_error = True

        if not known_error_noted:
            logger.log(LogLevel.ERROR, f"Streaming interrupted, Gemini Error Code {status_code}: {error}")

    async def stream_request():
        while True:
            record = model_manager.reserve_best_model()
            logger.log(LogLevel.INFO, f"Streaming response with {record.model}")

            if record == None:
                yield b'data: {"error": {"message": "All keys exhausted"}}\n\n'
                return

            body["model"] = record.model
            headers = {
                "Authorization": f"Bearer {record.key}",
                "Content-Type": "application/json"
            }

            index_to_id: dict[int, str] = {}
            total_tokens = 0

            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    GEMINI_OPENAI_URL,
                    json=body,
                    headers=headers,
                    timeout=180.0
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        record_errors(record, error_body.decode(), response.status_code)
                        model_manager.finalize(record, total_tokens)
                        continue

                    try:
                        async for line in response.aiter_lines():
                            if line.startswith("data: ") and line != "data: [DONE]":
                                try:
                                    capture_signatures(json.loads(line[6:]), index_to_id)
                                except json.JSONDecodeError:
                                    pass
                            yield (line + "\n").encode()
                    finally:
                        model_manager.finalize(record, total_tokens)
                    return

    return StreamingResponse(stream_request(), media_type="text/event-stream")