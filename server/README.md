# Transcriber meeting reporter

1. Copy `.env.example` to `.env` and fill in an OpenRouter API key and SMTP credentials. Do not put the OpenRouter key in the Chrome extension.
2. Install dependencies: `pip install -r requirements.txt`
3. Start the API: `uvicorn main:app --reload --port 8080`
4. Reload the unpacked Chrome extension. At every completed meeting it downloads a `.txt` backup and posts that file to `http://127.0.0.1:8080/api/meetings/analyze-file`.

The server asks Mistral Small 3.1 24B for a strict JSON report, saves each response under `server/responses/`, prints it to the console, renders a responsive HTML email, attaches the transcript as `meeting-transcript.txt`, and delivers both to the configured recipients. Test the server first at `http://127.0.0.1:8080/health`.

The extension uses the local server by default and no server URL setting is required. Reload the extension after changing its manifest permissions.
