import os
import uuid
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load once at startup — tiny model fits in Render free 512MB with int8
model = WhisperModel("tiny", device="cpu", compute_type="int8")

MORSE_MAP = {
    'A': [100, 300], 'B': [300, 100, 100, 100], 'C': [300, 100, 300, 100],
    'D': [300, 100, 100], 'E': [100], 'F': [100, 100, 300, 100],
    'G': [300, 300, 100], 'H': [100, 100, 100, 100], 'I': [100, 100],
    'J': [100, 300, 300, 300], 'K': [300, 100, 300], 'L': [100, 300, 100, 100],
    'M': [300, 300], 'N': [300, 100], 'O': [300, 300, 300],
    'P': [100, 300, 300, 100], 'Q': [300, 300, 100, 300], 'R': [100, 300, 100],
    'S': [100, 100, 100], 'T': [300], 'U': [100, 100, 300],
    'V': [100, 100, 100, 300], 'W': [100, 300, 300], 'X': [300, 100, 100, 300],
    'Y': [300, 100, 300, 300], 'Z': [300, 300, 100, 100],
}

SYMBOL_GAP = 100
LETTER_GAP = 300


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
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
    pattern = []
    letters = [c for c in text.upper() if c in MORSE_MAP]
    for i, char in enumerate(letters):
        symbols = MORSE_MAP[char]
        for j, duration in enumerate(symbols):
            pattern.append(duration)
            if j < len(symbols) - 1:
                pattern.append(SYMBOL_GAP)
        if i < len(letters) - 1:
            pattern.append(LETTER_GAP)
    return pattern if pattern else [200]


@app.get("/health")
async def health():
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
    tmp_path = f"/tmp/{uuid.uuid4()}.m4a"
    try:
        contents = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(contents)

        segments, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: model.transcribe(tmp_path)
        )
        text = " ".join([seg.text for seg in segments]).strip()

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
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
