from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import time
import uuid
import httpx
from dotenv import load_dotenv
from logger import Logger, LogLevel
from model_manager import ModelManager, APIRecord, model_limits
from contextlib import asynccontextmanager
from pathlib import Path

load_dotenv()

SIGNATURES_FILE = "thought_signatures.json"


def save_signatures():
    with open(SIGNATURES_FILE, "w") as f:
        json.dump(thought_signatures, f)


def load_signatures() -> dict[str, str]:
    if not Path(SIGNATURES_FILE).is_file():
        return {}
    with open(SIGNATURES_FILE, "r") as f:
        return json.load(f)


thought_signatures = load_signatures()
THOUGHT_SIGNATURE_SENTINEL = "skip_thought_signature_validator"

model_manager = ModelManager()
logger = Logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logger.log(LogLevel.INFO, "Shutting down and saving models")
    model_manager.save()
    save_signatures()


app = FastAPI(lifespan=lifespan)


def inject_signatures(body: dict) -> None:
    for message in body.get("messages", []):
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls", []) or []:
            signature = thought_signatures.get(tool_call.get("id"), THOUGHT_SIGNATURE_SENTINEL)
            if signature == THOUGHT_SIGNATURE_SENTINEL:
                logger.log(LogLevel.WARNING, "Falling back to sentinel for a function signature")
            tool_call.setdefault("extra_content", {}).setdefault("google", {})["thought_signature"] = signature


def enable_thought_summaries(body: dict) -> None:
    extra_body = body.setdefault("extra_body", {})
    google = extra_body.setdefault("google", {})
    thinking_config = google.setdefault("thinking_config", {})
    if "include_thoughts" not in thinking_config:
        thinking_config["include_thoughts"] = True


def extract_gemini_error(error_payload: str) -> tuple[int, str]:
    try:
        payload = json.loads(error_payload)
    except json.JSONDecodeError:
        return 500, error_payload.strip() or "Gemini returned an invalid response"

    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, list):
        return 500, ", ".join(str(item) for item in error)
    if isinstance(error, dict):
        violations = error.get("details")[1].get("violations")
        message = ""
        for violation in violations:
            message += violation.get("quotaId")
        code = error.get("code", 500)
        return int(code), message

    return 500, str(payload) if payload else "Gemini returned an invalid response"


def is_retryable_gemini_error(status_code: int, message: str) -> bool:
    if status_code in {429, 500, 503}:
        return True
    lowered = message.lower()
    return any(token in lowered for token in [
        "quota exceeded",
        "high demand",
        "resource_exhausted",
        "temporarily unavailable",
        "unavailable",
        "rate limit",
        "retry later",
    ])


def capture_signatures(parsed_chunk: dict, index_to_id: dict):
    choices = parsed_chunk.get("choices", [])
    if not choices:
        return

    for tc in choices[0].get("delta", {}).get("tool_calls", []) or []:
        idx = tc.get("index")
        if "id" in tc:
            index_to_id[idx] = tc["id"]
        sig = tc.get("extra_content", {}).get("google", {}).get("thought_signature")
        if sig:
            tc_id = tc.get("id") or index_to_id.get(idx)
            if tc_id:
                thought_signatures[tc_id] = sig


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    logger.log(LogLevel.INFO, "Starting chat completion request")
    body = await request.json()
    inject_signatures(body)
    enable_thought_summaries(body)

    GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"

    def record_errors(record: APIRecord, error: str, status_code):
        known_error_noted = False
        if "GenerateRequestsPerDay" in error:
            known_error_noted = True
            record.record.RPD_error = True
        if "GenerateRequestsPerMinute" in error:
            known_error_noted = True
            record.record.RPM_error = True
        if "GenerateContentInputTokens" in error:
            known_error_noted = True
            record.record.TPM_error = True
        if "This model is currently experiencing high demand" in error:
            known_error_noted = True
            record.record.DEMAND_error = True

        if not known_error_noted:
            logger.log(LogLevel.ERROR, f"Unknown error interrupted streaming, Gemini Error Code {status_code}: {error}")
        else:
            logger.log(LogLevel.INFO, f"Known error interrupted streaming, Gemini Error Code {status_code}: {error}")

    last_error_status = 500
    last_error_message = "Gemini did not return a valid response"

    for _ in range(20):
        selected_model = body.get("model", "gemini_pooled")
        if selected_model not in model_limits.keys():
            if selected_model != "gemini_pooled":
                logger.log(LogLevel.INFO, f"User has run query with unknown model {selected_model}, defaulting to best pooled")
            record = model_manager.reserve_best_model()
        else:
            try:
                record = model_manager.reserve_model(selected_model)
            except Exception:
                logger.log(LogLevel.INFO, f"Model {selected_model} not available, falling back to best pooled")
                record = model_manager.reserve_best_model()

        if record is None:
            logger.log(LogLevel.INFO, "Exhausted all keys")
            break

        logger.log(LogLevel.INFO, f"Streaming response with {record.model}")
        request_body = {**body, "model": record.model}
        headers = {
            "Authorization": f"Bearer {record.key}",
            "Content-Type": "application/json",
        }

        valid_chunks: list[bytes] = []
        non_data_lines: list[str] = []
        index_to_id: dict[int, str] = {}

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    GEMINI_OPENAI_URL,
                    json=request_body,
                    headers=headers,
                    timeout=300.0,
                ) as response:

                    if response.status_code != 200:
                        error_body = await response.aread()
                        decoded_error = error_body.decode("utf-8", errors="replace")
                        last_error_status, last_error_message = extract_gemini_error(decoded_error)
                        record_errors(record, decoded_error, response.status_code)
                        model_manager.finalize(record, 0)
                        if is_retryable_gemini_error(last_error_status, last_error_message):
                            logger.log(LogLevel.WARNING, f"Retryable Gemini upstream error for model {record.model}: {last_error_status} {last_error_message}")
                            continue
                        break

                    logger.log(LogLevel.INFO, "Successful response from Gemini")
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            if line.strip():
                                non_data_lines.append(line)
                            continue

                        payload = line[6:]
                        logger.log(LogLevel.INFO, f"Raw Gemini SSE payload: {payload[:2000]}")
                        if payload == "[DONE]":
                            logger.log(LogLevel.INFO, "Received Gemini [DONE] marker")
                            continue

                        try:
                            parsed_chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.log(LogLevel.WARNING, f"Failed to JSON-decode Gemini SSE payload: {payload[:2000]}")
                            continue

                        capture_signatures(parsed_chunk, index_to_id)
                        valid_chunks.append((line + "\n").encode())

                    raw_extra = "\n".join(non_data_lines)
                    if '"error"' in raw_extra:
                        last_error_status, last_error_message = extract_gemini_error(raw_extra)
                        record_errors(record, raw_extra, last_error_status)
                        model_manager.finalize(record, 0)
                        if is_retryable_gemini_error(last_error_status, last_error_message):
                            logger.log(LogLevel.WARNING, f"Mid-stream Gemini error on {record.model}: {last_error_status} {last_error_message}")
                            continue
                        break

                    model_manager.finalize(record, 0)
        except Exception as exc:
            logger.log(LogLevel.ERROR, f"Gemini streaming request failed: {exc}")
            continue

        if valid_chunks:
            async def stream_generator():
                for chunk in valid_chunks:
                    yield chunk
                yield b"data: [DONE]\n\n"

            return StreamingResponse(stream_generator(), media_type="text/event-stream")

    return StreamingResponse(iter(()), media_type="text/event-stream")
