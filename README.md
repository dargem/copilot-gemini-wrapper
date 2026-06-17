Key rotator wrapper around gemini's api for github pilot. Kindof lazily written assumes only one request is going at a time.

To setup the server locally run:

uvicorn server:app --reload --port 8787