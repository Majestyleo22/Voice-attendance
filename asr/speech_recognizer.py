"""
ASR Speech Recognizer Module for Voice Attendance System
Integrates Faster-Whisper with fallback decoding and noise filtering.
"""

import io
import os
import wave
import threading
import logging
import numpy as np

# Safe PyAV compatibility patch for newer av versions (av >= 14)
try:
    import av
    _orig_av_open = av.open

    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)

    av.open = _safe_av_open
except Exception as e:
    pass

logger = logging.getLogger(__name__)

# Global singleton model and lock
_MODEL = None
_MODEL_LOCK = threading.Lock()
_MODEL_NAME = "tiny.en"


def get_whisper_model():
    """Lazily loads and returns the singleton Faster-Whisper model."""
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                try:
                    from faster_whisper import WhisperModel
                    logger.info(f"Loading faster-whisper model '{_MODEL_NAME}' on CPU...")
                    _MODEL = WhisperModel(_MODEL_NAME, device="cpu", compute_type="int8")
                    logger.info("Faster-whisper model loaded successfully.")
                except Exception as ex:
                    logger.error(f"Failed to load faster-whisper: {ex}")
                    _MODEL = False
    return _MODEL if _MODEL is not False else None


def decode_audio_to_numpy(audio_bytes: bytes, original_filename: str = "") -> np.ndarray:
    """
    Decodes audio bytes into a 16000Hz mono float32 numpy array.
    Tries multiple approaches for resilience:
    1. Standard wave module (for standard WAV PCM)
    2. soundfile (for WAV, FLAC, OGG)
    3. PyAV (for WebM, Opus, MP3, etc.)
    """
    if not audio_bytes or len(audio_bytes) < 44:
        return None

    # Approach 1: Try wave module (Standard PCM WAV)
    try:
        buf = io.BytesIO(audio_bytes)
        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            if n_frames > 0:
                raw_frames = wf.readframes(n_frames)
                if sampwidth == 2:
                    audio_data = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    audio_data = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
                elif sampwidth == 1:
                    audio_data = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                else:
                    audio_data = None

                if audio_data is not None:
                    # If stereo, average down to mono
                    if n_channels > 1:
                        audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

                    # Resample if not 16000
                    if framerate != 16000 and len(audio_data) > 0:
                        duration = len(audio_data) / framerate
                        target_len = int(duration * 16000)
                        if target_len > 0:
                            indices = np.linspace(0, len(audio_data) - 1, target_len)
                            audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)

                    return audio_data.astype(np.float32)
    except Exception:
        pass

    # Approach 2: Try soundfile
    try:
        import soundfile as sf
        buf = io.BytesIO(audio_bytes)
        audio_data, samplerate = sf.read(buf, dtype="float32")
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)
        if samplerate != 16000 and len(audio_data) > 0:
            duration = len(audio_data) / samplerate
            target_len = int(duration * 16000)
            if target_len > 0:
                indices = np.linspace(0, len(audio_data) - 1, target_len)
                audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)
        return audio_data.astype(np.float32)
    except Exception:
        pass

    # Approach 3: Try PyAV
    try:
        import av
        buf = io.BytesIO(audio_bytes)
        container = av.open(buf)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        frames = []
        for frame in container.decode(audio=0):
            resampled = resampler.resample(frame)
            if resampled:
                frames.append(resampled.to_ndarray().flatten())
        if frames:
            return np.concatenate(frames).astype(np.float32)
    except Exception as ex:
        logger.warning(f"PyAV decoding failed: {ex}")

    return None


def calculate_audio_energy(audio: np.ndarray) -> float:
    """Calculates RMS energy of audio signal to detect silence."""
    if audio is None or len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> tuple:
    """
    Transcribes spoken audio using Faster-Whisper.
    Returns:
    (recognized_text: str, status: str, details: dict)
    Status values:
    - 'SUCCESS'
    - 'EMPTY_SPEECH'
    - 'POOR_RECOGNITION'
    - 'ERROR'
    """
    if not audio_bytes or len(audio_bytes) < 100:
        return "", "EMPTY_SPEECH", {"error": "Audio file is empty or too short."}

    # Step 1: Decode audio
    audio_np = decode_audio_to_numpy(audio_bytes, filename)
    if audio_np is None or len(audio_np) == 0:
        return "", "ERROR", {"error": "Could not decode audio format."}

    # Step 2: Energy & Duration Check (Silence filtering)
    duration_sec = len(audio_np) / 16000.0
    energy = calculate_audio_energy(audio_np)

    # Threshold for silence detection (< 0.003 is background hum/dead silence)
    if duration_sec < 0.25 or energy < 0.0025:
        return "", "EMPTY_SPEECH", {
            "duration": round(duration_sec, 2),
            "energy": round(energy, 5),
            "message": "No speech detected (audio is silent)."
        }

    # Step 3: Run Faster-Whisper
    model = get_whisper_model()
    if model is not None:
        try:
            # Transcribe with English language prompt and light VAD filtering
            segments, info = model.transcribe(
                audio_np,
                language="en",
                beam_size=3,
                best_of=3,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400)
            )

            text_parts = []
            avg_logprobs = []
            for seg in segments:
                text_parts.append(seg.text.strip())
                if hasattr(seg, "avg_logprob"):
                    avg_logprobs.append(seg.avg_logprob)

            full_text = " ".join(text_parts).strip()

            if not full_text:
                return "", "EMPTY_SPEECH", {"duration": duration_sec, "energy": energy}

            # Check logprob confidence
            mean_logprob = float(np.mean(avg_logprobs)) if avg_logprobs else 0.0
            # Extremely negative logprob means severe hallucinations or noise
            if mean_logprob < -1.8 and len(full_text.split()) > 10:
                return full_text, "POOR_RECOGNITION", {"logprob": mean_logprob}

            return full_text, "SUCCESS", {
                "duration": round(duration_sec, 2),
                "energy": round(energy, 4),
                "logprob": round(mean_logprob, 3),
                "language": info.language if info else "en"
            }
        except Exception as ex:
            logger.error(f"Faster-whisper transcription error: {ex}")

    # Step 4: Fallback to SpeechRecognition if whisper failed
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        # Save temp wav
        buf = io.BytesIO(audio_bytes)
        with sr.AudioFile(buf) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text.strip(), "SUCCESS", {"engine": "speech_recognition_google_fallback"}
    except sr.UnknownValueError:
        return "", "EMPTY_SPEECH", {"error": "Speech was unintelligible"}
    except Exception as ex:
        return "", "ERROR", {"error": str(ex)}
