import os
import json
import azure.cognitiveservices.speech as speechsdk
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Azure Configuration
AZURE_SPEECH_KEY = "your_azure_key"
AZURE_REGION = "your_region"

def text_to_morse_haptics(text: str):
    """Converts text to vibration timings (ms). Short = 100ms, Long = 300ms."""
    MORSE_MAP = {'A': [100, 300], 'B': [300, 100, 100, 100], 'S': [100, 100, 100]} # Simplified
    pattern = []
    for char in text.upper():
        if char in MORSE_MAP:
            pattern.extend(MORSE_MAP[char])
            pattern.append(200)  # Gap between letters
    return pattern

@app.post("/speech-to-haptic")
async def speech_to_haptic(file: UploadFile = File(...)):
    # Save temp audio file
    with open("temp.wav", "wb") as buffer:
        buffer.write(await file.read())

    # Azure Speech-to-Text Logic[cite: 4]
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_REGION)
    audio_input = speechsdk.AudioConfig(filename="temp.wav")
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

    result = speech_recognizer.recognize_once_async().get()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        transcript = result.text
        haptic_pattern = text_to_morse_haptics(transcript)
        return {"transcript": transcript, "pattern": haptic_pattern}
    
    return {"error": "Speech not recognized"}
