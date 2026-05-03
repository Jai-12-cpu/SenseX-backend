import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import azure.cognitiveservices.speech as speechsdk

app = FastAPI()

# Enable CORS for cross-platform communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Azure Configuration
AZURE_SPEECH_KEY = "YOUR_AZURE_KEY"
AZURE_REGION = "YOUR_REGION"

class ConnectionManager:
    """Manages active WebSocket connections for real-time broadcasting."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

def text_to_haptic_pattern(text: str):
    """Maps text characters to vibration durations (ms)."""
    # Simple mapping: Dot=100, Dash=300, Gap=100
    MORSE_MAP = {'A': [100, 300], 'B': [300, 100, 100, 100], 'H': [100, 100, 100, 100]}
    pattern = []
    for char in text.upper():
        if char in MORSE_MAP:
            pattern.extend(MORSE_MAP[char])
            pattern.append(200) # Inter-character gap
    return pattern

@app.websocket("/ws/haptics")
async def haptic_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Heartbeat logic to keep the connection alive[cite: 1]
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/translate-speech")
async def translate_speech(file: UploadFile = File(...)):
    """Receives audio, uses Azure to transcribe, and broadcasts haptics."""[cite: 4]
    with open("input.wav", "wb") as f:
        f.write(await file.read())

    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_REGION)
    audio_config = speechsdk.AudioConfig(filename="input.wav")
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    result = recognizer.recognize_once_async().get()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pattern = text_to_haptic_pattern(result.text)
        # Broadcast to all connected deafblind users instantly
        await manager.broadcast({"type": "VIBRATE", "pattern": pattern, "text": result.text})
        return {"status": "success", "text": result.text}
    
    return {"status": "error", "message": "Speech not recognized"}
