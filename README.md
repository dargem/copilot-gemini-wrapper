# Copilot Gemini Wrapper

A key-rotating wrapper around Gemini's API for GitHub Copilot. It is designed to manage multiple Gemini API keys, rotate them to handle rate limits, and provide a seamless custom endpoint for VS Code's GitHub Copilot. Using Gemini AI Studio you can have 12 google workspaces, each with their own API key that have independent rate limits. This allows you as of today's rate limits (18th June) to get 240 gemini-3.5-flash, 240 gemini-3-flash-preview and 6000 gemini-3.1-flash-lite calls respectively. This program will create the files log.txt, key_data.json which stores usage limits corresponding to your keys and thought_signatures.json which stores gemini's encrypted thought signatures used for internal reasoning. This has instructions for setting up the server, as well as a way to simply add it as a custom endpoint for github copilot using vscode.

## Features

- **Key Rotation**: Automatically rotates through multiple Gemini API keys to maximize available rate limit
- **Rate Limit Management**: Tracks requests per day (RPD), requests per minute (RPM), and tokens per minute (TPM) locally
- **Graceful Fallbacks**: If rate-limited, the manager temporarily stops using that key's models and falls back to another one
- **Persistence**: Saves model usage statistics to key_data.json so that restarting the server doesn't lose track of daily limits
- **Automatic Reset**: Daily request counts are reset automatically at midnight (Pacific Time).
- **Out-of-Sync Recovery**: Built-in fallbacks exist if a key hits rate limits, updating local tracking accordingly.
- **Simple Logging**: Logs requests and errors to both the console and log.txt.
- **Thought Signatures**: Transparent Gemini thought signature relay which copilot drops for multi-turn tool call continuity
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

### 1. Configure API Keys

Create a `.env` file in the root directory and add your Gemini API keys. Each key must start with `KEY_` followed by a unique identifier (e.g., the name of the Google AI Studio project):

```env
KEY_FOO=Adsfjsakfdklafds 
KEY_BAR=sdafjadasfklafsd
KEY_PROJECT_7=dsafajdkfaklfajd
```

### 2. Install Dependencies

There are two options, I suggest using the bash script run.sh. It should work for unix based systems. It will detect if you have created a venv. If you haven't it will ask to create one and install requirements.txt. Once its done it will start up a server. You can easily create a symlink in /.local/bin to this `run.sh` and you can launch it from anywhere.

To do this manually (or if on windows source venv/bin/activate won't work so you need to modify it), create a venv and install the required Python packages:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then start the server using Uvicorn:

```bash
uvicorn server:app --port 8787
```

Use the --reload flag if doing development. If that port is already in use you may want to use this to see who is using the port:

```bash
sudo ss -tulpn | grep 8787
```

You can kill them using the PID, or just change the used port of this server.

## VS Code Integration

To configure VS Code's GitHub Copilot to use this wrapper, add a custom endpoint in your model settings. You can adjust `maxInputTokens` and `maxOutputTokens` as needed. Gemini rate limits don't really care about length of output. id corresponds to what is being sent to the server about what model you have selected. Name is just the client side name. To do this:

1. ctrl + shift + p -> Chat: Manage Language Models
2. Add models (custom endpoint)
3. Add in this to your custom endpoint json

```json
[
    // ETC... if you already have some, then add this as an entry
	{
		"name": "GeminiWrapper", // This is the group each model is under
		"vendor": "customendpoint",
		"apiType": "chat-completions",
		"models": [
			{
				"id": "gemini_pooled",
				"name": "best pooled", // This is the name you will see in model selection
				"url": "http://localhost:8787/v1/chat/completions",
				"toolCalling": true,
				"vision": true,
				"maxInputTokens": 512000,
				"maxOutputTokens": 16000
			},
			{
				"id": "gemini-3.5-flash",
				"name": "3.5 flash",
				"url": "http://localhost:8787/v1/chat/completions",
				"toolCalling": true,
				"vision": true,
				"maxInputTokens": 512000,
				"maxOutputTokens": 16000
			},
			{
				"id": "gemini-3-flash-preview",
				"name": "3 flash",
				"url": "http://localhost:8787/v1/chat/completions",
				"toolCalling": true,
				"vision": true,
				"maxInputTokens": 512000,
				"maxOutputTokens": 16000
			},
			{
				"id": "gemini-3.1-flash-lite",
				"name": "3.1 flash lite",
				"url": "http://localhost:8787/v1/chat/completions",
				"toolCalling": true,
				"vision": true,
				"maxInputTokens": 512000,
				"maxOutputTokens": 16000
			},
		]
	}
]
```

And you're done, simply select the chosen name under GeminiWrapper and you're good to go.