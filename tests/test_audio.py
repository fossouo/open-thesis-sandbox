import os
import json
import pytest
import wave
import httpx
import hashlib
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import app, concatenate_wavs

client = TestClient(app)

def create_dummy_wav(path: str, framerate: int = 24000, duration: float = 0.1):
    """Creates a small dummy WAV file with 16-bit mono PCM zero frames."""
    nchannels = 1
    sampwidth = 2
    nframes = int(framerate * duration)
    data = b'\x00' * (nframes * nchannels * sampwidth)
    
    with wave.open(path, 'wb') as w:
        w.setnchannels(nchannels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(data)

def test_concatenate_wavs(tmp_path):
    # Create two dummy WAV files
    wav1 = str(tmp_path / "chunk1.wav")
    wav2 = str(tmp_path / "chunk2.wav")
    out_wav = str(tmp_path / "output.wav")
    
    create_dummy_wav(wav1, duration=0.2)
    create_dummy_wav(wav2, duration=0.3)
    
    success = concatenate_wavs([wav1, wav2], out_wav, silence_duration=0.1)
    assert success is True
    assert os.path.exists(out_wav)
    
    # Check that output file is valid and check its parameters and length
    with wave.open(out_wav, 'rb') as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 24000
        # Total duration = 0.2 + 0.1 (silence) + 0.3 = 0.6 seconds
        assert w.getnframes() == int(0.6 * 24000)

def test_audio_overview_invalid_language():
    response = client.post(
        "/api/audio-overview",
        json={
            "weights": {"NVDA": 100},
            "lang": "de" # Invalid language
        }
    )
    assert response.status_code == 422

def test_audio_overview_zero_weights():
    response = client.post(
        "/api/audio-overview",
        json={
            "weights": {"NVDA": 0, "AMD": 0},
            "lang": "en"
        }
    )
    assert response.status_code == 400

@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
def test_audio_overview_mock_success(mock_post, tmp_path):
    # We mock:
    # 1. LiteLLM response with dialogue JSON
    # 2. TTS server response with dummy audio WAV content
    
    # Setup mock response 1: LiteLLM script
    mock_litellm_resp = MagicMock()
    mock_litellm_resp.status_code = 200
    mock_litellm_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps([
                        {"speaker": "A", "text": "Bonjour, quel beau portefeuille !"},
                        {"speaker": "B", "text": "Oui, beaucoup de NVIDIA."}
                    ])
                }
            }
        ]
    }
    
    # Setup mock response 2: TTS sound file response (dummy WAV bytes)
    dummy_wav_path = str(tmp_path / "dummy.wav")
    create_dummy_wav(dummy_wav_path, duration=0.1)
    with open(dummy_wav_path, "rb") as f:
        dummy_wav_bytes = f.read()
        
    mock_tts_resp = MagicMock()
    mock_tts_resp.status_code = 200
    mock_tts_resp.content = dummy_wav_bytes
    
    # Setup AsyncClient mock to yield these responses in order
    mock_post.side_effect = [mock_litellm_resp, mock_tts_resp, mock_tts_resp]
    
    # Override AUDIO_CACHE_DIR temporarily to tmp_path
    import main
    original_cache_dir = main.AUDIO_CACHE_DIR
    main.AUDIO_CACHE_DIR = str(tmp_path)
    
    try:
        response = client.post(
            "/api/audio-overview",
            json={
                "weights": {"NVDA": 80.0, "AMD": 20.0},
                "lang": "fr"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "audio_url" in data
        assert "cached" in data
        assert data["cached"] is False
        
        # Verify that output file exists
        audio_filename = os.path.basename(data["audio_url"])
        output_file_path = os.path.join(str(tmp_path), audio_filename)
        assert os.path.exists(output_file_path)
        
        # Read WAV to verify total duration (2 chunks of 0.1s + 1 silence of 0.4s = 0.6s)
        with wave.open(output_file_path, 'rb') as w:
            assert w.getnframes() == int(0.6 * 24000)
            
    finally:
        main.AUDIO_CACHE_DIR = original_cache_dir

def test_tts_service_connectivity():
    # Sanity check: verify if the TTS service is reachable 
    # If not reachable, skip the test instead of failing
    try:
        # Check standard health or root endpoint
        response = httpx.get("http://localhost:8880/", timeout=2.0)
        assert response.status_code in [200, 404, 405]
    except Exception as e:
        pytest.skip(f"TTS service at http://localhost:8880 is not reachable: {e}")

@patch("main.perform_audio_generation", new_callable=AsyncMock)
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
def test_analyze_proactive_audio_trigger(mock_post, mock_perf_gen, tmp_path):
    # Mock LiteLLM for /api/analyze
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Analysis text here.", "reasoning_content": "Reasoning here."}}]
    }
    mock_post.return_value = mock_resp
    
    import main
    original_cache_dir = main.AUDIO_CACHE_DIR
    main.AUDIO_CACHE_DIR = str(tmp_path)
    main.active_audio_tasks.clear()
    
    try:
        response = client.post(
            "/api/analyze",
            json={
                "weights": {"NVDA": 50, "AMD": 50},
                "lang": "fr"
            }
        )
        assert response.status_code == 200
        
        # Verify perform_audio_generation was triggered in background
        mock_perf_gen.assert_called_once()
        
    finally:
        main.AUDIO_CACHE_DIR = original_cache_dir
        main.active_audio_tasks.clear()

@patch("main.perform_audio_generation", new_callable=AsyncMock)
def test_audio_overview_duplicate_task_avoidance(mock_perf_gen, tmp_path):
    import main
    original_cache_dir = main.AUDIO_CACHE_DIR
    main.AUDIO_CACHE_DIR = str(tmp_path)
    main.active_audio_tasks.clear()
    
    try:
        weights = {"NVDA": 50.0, "AMD": 50.0}
        lang = "fr"
        weights_hash_str = json.dumps(sorted(weights.items()), sort_keys=True) + f"_{lang}"
        file_hash = hashlib.md5(weights_hash_str.encode("utf-8")).hexdigest()
        cached_filename = f"audio_{file_hash}.wav"
        cached_filepath = os.path.join(str(tmp_path), cached_filename)
        
        async def mock_running_task():
            # Create the dummy file to simulate perform_audio_generation completing
            create_dummy_wav(cached_filepath, duration=0.1)
            
        main.active_audio_tasks[file_hash] = mock_running_task()
        
        response = client.post(
            "/api/audio-overview",
            json={
                "weights": weights,
                "lang": lang
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "audio_url" in data
        assert data["cached"] is False
        
        # Verify perform_audio_generation was NOT called (we awaited the active task instead)
        mock_perf_gen.assert_not_called()
        
    finally:
        main.AUDIO_CACHE_DIR = original_cache_dir
        main.active_audio_tasks.clear()

