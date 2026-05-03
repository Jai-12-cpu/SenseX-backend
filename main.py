import os
import uuid
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import whisper

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Whisper model once at startup — not on every request
# Options: "tiny", "base", "small", "medium", "large"
model = whisper.load_model("base")

# Full Morse code map
MORSE_MAP = {
    'A': [100, 300],
    'B': [300, 100, 100, 100],
    'C': [300, 100, 300, 100],
    'D': [300, 100, 100],
    'E': [100],
    'F': [100, 100, 300, 100],
    'G': [300, 300, 100],
    'H': [100, 100, 100, 100],
    'I': [100, 100],
    'J': [100, 300, 300, 300],
    'K': [300, 100, 300],
    'L': [100, 300, 100, 100],
    'M': [300, 300],
    'N': [300, 100],
    'O': [300, 300, 300],
    'P': [100, 300, 300, 100],
    'Q': [300, 300, 100, 300],
    'R': [100, 300, 100],
    'S': [100, 100, 100],
    'T': [300],
    'U': [100, 100, 300],
    'V': [100, 100, 100, 300],
    'W': [100, 300, 300],
    'X': [300, 100, 100, 300],
    'Y': [300, 100, 300, 300],
    'Z': [300, 300, 100, 100],
}

DOT = 100        # ms — vibration for a dot
DASH = 300       # ms — vibration for a dash
SYMBOL_GAP = 100  # ms — silence between dot/dash within a letter
LETTER_GAP = 300  # ms — silence between letters


class ConnectionManager:
    """Manages active WebSocket connections for real-time broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast to all connected clients, dropping stale ones."""
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.active_connections.remove(conn)


manager = ConnectionManager()


def text_to_haptic_pattern(text: str) -> list[int]:
    """
    Converts text to a Vibration.vibrate()-compatible pattern.

    Android's Vibration.vibrate(pattern) alternates between:
      vibrate, pause, vibrate, pause, ...
    starting with vibrate if the first value is > 0.

    We encode Morse as: dot/dash, symbol_gap, dot/dash, symbol_gap...
    with a longer letter_gap between letters.
    """
    pattern = []
    letters = [c for c in text.upper() if c in MORSE_MAP]

    for i, char in enumerate(letters):
        symbols = MORSE_MAP[char]
        for j, duration in enumerate(symbols):
            pattern.append(duration)           # vibrate
            if j < len(symbols) - 1:
                pattern.append(SYMBOL_GAP)     # pause between symbols
        if i < len(letters) - 1:
            pattern.append(LETTER_GAP)         # pause between letters

    return pattern if pattern else [200]  # fallback single buzz


@app.get("/health")
async def health():
    """Health check endpoint for Render uptime monitoring."""
    return {"status": "ok"}


@app.websocket("/ws/haptics")
async def haptic_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/translate-speech")
async def translate_speech(file: UploadFile = File(...)):
    """
    Receives a .m4a audio file, transcribes with local Whisper,
    converts to haptic Morse pattern, and broadcasts to all WS clients.
    """
    # Write to a unique temp file to avoid race conditions
    tmp_path = f"/tmp/{uuid.uuid4()}.m4a"
    try:
        contents = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(contents)

        # Run blocking Whisper call in a thread so we don't block the event loop
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: model.transcribe(tmp_path)
        )

        text = result["text"].strip()

        if text:
            pattern = text_to_haptic_pattern(text)
            await manager.broadcast({
                "type": "VIBRATE",
                "pattern": pattern,
                "text": text,
            })
            return {"status": "success", "text": text, "pattern": pattern}

        return {"status": "error", "message": "Speech not recognized"}

    finally:
        # Always clean up the temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
