# Copilot Gemini Wrapper

A key-rotating wrapper around Gemini's API for GitHub Copilot. It is designed to manage multiple Gemini API keys, rotate them to handle rate limits, and provide a seamless custom endpoint for VS Code's GitHub Copilot. Using Gemini AI Studio you can have 12 google workspaces, each with their own API key that have independent rate limits. This allows you as of today's rate limits (18th June) to get 240 gemini-3.5-flash, 240 gemini-3-flash-preview and 6000 gemini-3.1-flash-lite calls respectively.

## Features

- **Key Rotation**: Automatically rotates through multiple Gemini API keys to maximize available rate limit
- **Rate Limit Management**: Tracks requests per day (RPD), requests per minute (RPM), and tokens per minute (TPM) locally
- **Graceful Fallbacks**: If rate-limited, the manager temporarily stops using that key's models and falls back to another one
- **Persistence**: Saves model usage statistics to key_data.json so that restarting the server doesn't lose track of daily limits
- **Automatic Reset**: Daily request counts are reset automatically at midnight (Pacific Time).
- **Out-of-Sync Recovery**: Built-in fallbacks exist if a key hits rate limits, updating local tracking accordingly.
- **Simple Logging**: Logs requests and errors to both the console and log.txt.
- **Full Compatibility**: There are no limitations compared to a normal endpoint, tool use and etc all works correctly.

## Supported Models

The wrapper currently manages and rotates the following models (configured in [model_manager.py](model_manager.py)):
- `gemini-3.5-flash`
- `gemini-3-flash-preview`
- `gemini-3.1-flash-lite`

Just adding another model into this will include it in the rotation. The model_manager assumes the models in `model_limits` are ordered in descending preference (so it would use all of `gemini-3.5-flash` before other models first here). If Gemini changes free rate limits or adds new models addition is simple, just pop in another model /or edit the corresponding limits.


```python
model_limits = {
    "gemini-3.5-flash": Limits(5, 250000, 20), # RPM, TPM, #RPD
    "gemini-3-flash-preview": Limits(5, 250000, 20),
    "gemini-3.1-flash-lite": Limits(15, 250000, 500)
}
```

## Setup

### 1. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file in the root directory and add your Gemini API keys. Each key must start with `KEY_` followed by a unique identifier (e.g., the name of the Google AI Studio project):

```env
KEY_FOO=Adsfjsakfdklafds 
KEY_BAR=sdafjadasfklafsd
KEY_PROJECT_7=dsafajdkfaklfajd
```

### 3. Start the Server

Run the FastAPI server locally using Uvicorn:

```bash
uvicorn server:app --reload --port 8787
```

## VS Code Integration

To configure VS Code's GitHub Copilot to use this wrapper, add a custom endpoint in your model settings. You can adjust `maxInputTokens` and `maxOutputTokens` as needed. Gemini rate limits don't really care about length of output.

```json
{
    "name": "GeminiWrapper",
    "vendor": "customendpoint",
    "apiType": "chat-completions",
    "models": [
        {
            "id": "gemini",
            "name": "Gemini (best pooled)",
            "url": "http://localhost:8787/v1/chat/completions",
            "toolCalling": true,
            "vision": true,
            "maxInputTokens": 512000,
            "maxOutputTokens": 16000
        }
    ]
}
```