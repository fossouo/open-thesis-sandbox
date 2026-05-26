import os
import json
import logging
import httpx
import wave
import hashlib
import re
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from core.dag_store import (
    init_db, get_latest_canonical, get_latest_node, get_node,
    get_node_tree, get_children, get_available_sectors, get_frontier,
    count_nodes
)
from core.auto_research import (
    run_full_research_cycle, SECTOR_GROUPS
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("financial_thesis_sandbox")

app = FastAPI(
    title="Financial Thesis Sandbox - Top 10 Semiconductors & US AI",
    description="Local POC for real-time financial backtesting and LLM-driven analysis.",
    version="1.0.0"
)

# OpenAI-compatible Chat Completions endpoint. Bring your own — Ollama, vLLM,
# llama.cpp, LiteLLM, OpenAI, etc.
LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:8000/v1/chat/completions")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gpt-4o-mini")

def _llm_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if LITELLM_API_KEY:
        h["Authorization"] = f"Bearer {LITELLM_API_KEY}"
    return h


# OpenAI-compatible TTS endpoint (e.g. Kokoro-FastAPI, OpenAI audio.speech).
TTS_API_URL = os.getenv("TTS_API_URL", "http://localhost:8880/v1/audio/speech")
TTS_MODEL = os.getenv("TTS_MODEL", "kokoro")

# Audio cache directory (override via AUDIO_CACHE_DIR).
AUDIO_CACHE_DIR = os.getenv("AUDIO_CACHE_DIR", os.path.join(os.path.dirname(__file__), "data", "audio-cache"))
if not os.path.exists(AUDIO_CACHE_DIR):
    try:
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    except Exception:
        AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "audio-cache")
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

logger.info(f"Using audio cache directory: {AUDIO_CACHE_DIR}")

# Global registry of active/running audio pre-generation tasks
active_audio_tasks: dict[str, asyncio.Task] = {}

# Initialize DAG store on startup
DAG_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "research.db")
dag_conn = init_db(DAG_DB_PATH)
logger.info(f"DAG store initialized at {DAG_DB_PATH} ({count_nodes(dag_conn)} existing nodes)")

# Track active research cycles to avoid duplicates
active_research_tasks: dict[str, asyncio.Task] = {}


class AnalyzeRequest(BaseModel):
    weights: dict[str, float]
    lang: str

    @field_validator('lang')
    @classmethod
    def validate_lang(cls, v):
        val = v.lower()
        if val not in ['fr', 'en']:
            raise ValueError("Language must be 'fr' or 'en'")
        return val

class AudioOverviewRequest(BaseModel):
    weights: dict[str, float]
    lang: str

    @field_validator('lang')
    @classmethod
    def validate_lang(cls, v):
        val = v.lower()
        if val not in ['fr', 'en']:
            raise ValueError("Language must be 'fr' or 'en'")
        return val

# API Endpoint for portfolio analysis
@app.post("/api/analyze")
async def analyze_portfolio(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    weights = request.weights
    lang = request.lang
    
    # Filter only the supported 10 tickers
    supported_tickers = {"NVDA", "AMD", "AVGO", "MU", "QCOM", "INTC", "MSFT", "GOOGL", "META", "AMZN"}
    filtered_weights = {ticker: val for ticker, val in weights.items() if ticker in supported_tickers}
    
    total_weight = sum(filtered_weights.values())
    if total_weight <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "fr": "Le poids total du portefeuille doit être supérieur à 0%.",
                "en": "Total portfolio weight must be greater than 0%."
            }
        )
    
    # Normalize weights to sum to 100%
    normalized = {ticker: round((val / total_weight) * 100, 2) for ticker, val in filtered_weights.items()}
    
    # Build readable list of allocations
    weights_str = "\n".join([f"- {ticker}: {val}%" for ticker, val in sorted(normalized.items(), key=lambda x: -x[1]) if val > 0])
    
    # Build System Prompt and Content depending on language
    if lang == "fr":
        system_prompt = (
            "Tu es un analyste financier de haut niveau spécialisé dans la technologie américaine et l'intelligence artificielle.\n"
            "Analyse le portefeuille d'actions américain qui te sera présenté (les allocations sont exprimées en pourcentage du portefeuille total).\n"
            "Rédige une analyse synthétique des risques et opportunités de cette allocation.\n"
            "Tu DOIS respecter strictement les consignes suivantes :\n"
            "1. Donne ton analyse en EXACTEMENT 3 phrases maximum.\n"
            "2. Rédige en français uniquement.\n"
            "3. Reste professionnel, analytique et constructif.\n"
            "Ne commence pas ton analyse par des phrases introductives ou de salutation. Donne directement les points clés de l'analyse."
        )
        user_content = f"Voici l'allocation du portefeuille :\n{weights_str}\n\nDonne-moi ton analyse de risques et d'opportunités en 3 phrases maximum."
    else:
        system_prompt = (
            "You are a elite financial analyst specializing in US technology and artificial intelligence equities.\n"
            "Analyze the US stock portfolio presented to you (allocations are expressed as percentages of the total portfolio).\n"
            "Write a synthetic analysis of the risks and opportunities of this allocation.\n"
            "You MUST strictly adhere to the following constraints:\n"
            "1. Provide your analysis in EXACTLY 3 sentences maximum.\n"
            "2. Write in English only.\n"
            "3. Remain professional, analytical, and constructive.\n"
            "Do not start your analysis with introductory phrases or greetings. Go straight to the key points of the analysis."
        )
        user_content = f"Here is the portfolio allocation:\n{weights_str}\n\nProvide your analysis of risks and opportunities in 3 sentences maximum."

    logger.info(f"Calling LiteLLM endpoint at {LITELLM_URL} using language: {lang}")
    
    # Set timeouts: 5 seconds for connection, 15 seconds total response timeout
    timeout = httpx.Timeout(15.0, connect=5.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                LITELLM_URL,
                headers=_llm_headers(),
                json={
                    "model": LITELLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024
                }
            )
            
            # Check for non-200 status codes from LiteLLM
            if response.status_code != 200:
                logger.error(f"LiteLLM returned status code {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail={
                        "fr": f"Erreur du serveur d'analyse local (LiteLLM) : Code {response.status_code}.",
                        "en": f"Local analysis server error (LiteLLM): Code {response.status_code}."
                    }
                )
                
            resp_json = response.json()
            choice = resp_json.get("choices", [{}])[0]
            message = choice.get("message", {})
            
            content = message.get("content", "").strip()
            reasoning = message.get("reasoning_content", "").strip()
            
            # Parse embedded think tags if reasoning_content is not returned separately
            if not reasoning and "<think>" in content:
                parts = content.split("</think>")
                if len(parts) >= 2:
                    reasoning = parts[0].replace("<think>", "").strip()
                    content = " ".join(parts[1:]).strip()
                elif len(parts) == 1:
                    reasoning = content.replace("<think>", "").strip()
                    content = ""
            
            logger.info("LiteLLM response successfully received and parsed.")
            
            # Proactively pre-generate audio overview in the background
            weights_hash_str = json.dumps(sorted(normalized.items()), sort_keys=True) + f"_{lang}"
            file_hash = hashlib.md5(weights_hash_str.encode("utf-8")).hexdigest()
            cached_filename = f"audio_{file_hash}.wav"
            cached_filepath = os.path.join(AUDIO_CACHE_DIR, cached_filename)
            
            if not os.path.exists(cached_filepath) and file_hash not in active_audio_tasks:
                logger.info(f"Triggering proactive audio overview generation in background for hash {file_hash}...")
                
                async def run_pregeneration():
                    try:
                        await perform_audio_generation(normalized, lang, file_hash, cached_filepath)
                    except Exception as bg_err:
                        logger.error(f"Proactive background audio generation failed: {bg_err}")
                    finally:
                        active_audio_tasks.pop(file_hash, None)
                
                task = asyncio.create_task(run_pregeneration())
                active_audio_tasks[file_hash] = task
                background_tasks.add_task(lambda: task)

            return {
                "analysis": content,
                "reasoning": reasoning,
                "normalized_weights": normalized
            }
            
        except httpx.ConnectError as ce:
            logger.error(f"Connection to LiteLLM failed: {ce}")
            raise HTTPException(
                status_code=503,
                detail={
                    "fr": "Le serveur d'analyse IA est injoignable. Vérifiez la variable LITELLM_URL et que le serveur OpenAI-compatible tourne.",
                    "en": "The AI analysis server is unreachable. Check LITELLM_URL and that an OpenAI-compatible server is running."
                }
            )
        except httpx.TimeoutException as te:
            logger.error(f"LiteLLM request timed out: {te}")
            raise HTTPException(
                status_code=504,
                detail={
                    "fr": "Le serveur d'analyse IA a mis trop de temps à répondre (timeout de 15s dépassé).",
                    "en": "The AI analysis server took too long to respond (15s timeout exceeded)."
                }
            )
        except HTTPException:
            # Re-raise HTTPExceptions we threw ourselves
            raise
        except Exception as e:
            logger.error(f"Unexpected error during LiteLLM invocation: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "fr": f"Erreur interne lors de l'appel à l'IA : {str(e)}",
                    "en": f"Internal error during AI call: {str(e)}"
                }
            )

def concatenate_wavs(paths: list[str], output_path: str, silence_duration: float = 0.4) -> bool:
    if not paths:
        return False
    try:
        with wave.open(paths[0], 'rb') as w_first:
            params = w_first.getparams()
            
        with wave.open(output_path, 'wb') as w_out:
            w_out.setnchannels(params.nchannels)
            w_out.setsampwidth(params.sampwidth)
            w_out.setframerate(params.framerate)
            w_out.setnframes(0)
            
            frame_size = params.nchannels * params.sampwidth
            silence_frames = int(params.framerate * silence_duration)
            silence_bytes = b'\x00' * (silence_frames * frame_size)
            
            for idx, path in enumerate(paths):
                with wave.open(path, 'rb') as w_in:
                    while True:
                        chunk = w_in.readframes(32768)
                        if not chunk:
                            break
                        w_out.writeframes(chunk)
                if idx < len(paths) - 1:
                    w_out.writeframes(silence_bytes)
        return True
    except Exception as e:
        logger.error(f"Error concatenating WAV files: {e}")
        return False

async def perform_audio_generation(normalized: dict[str, float], lang: str, file_hash: str, cached_filepath: str):
    # Build list of allocations
    weights_str = "\n".join([f"- {ticker}: {val}%" for ticker, val in sorted(normalized.items(), key=lambda x: -x[1]) if val > 0])
    
    # Prompts for the configured chat-completions model
    if lang == "fr":
        system_prompt = (
            "Tu es un producteur de podcasts financiers de haut niveau spécialisé dans la technologie et l'IA américaine.\n"
            "Génère un script de dialogue structuré ultra-court (EXACTEMENT 4 répliques au total : A, puis B, puis A, puis B) entre deux analystes.\n"
            "A est l'hôte (voix féminine) et B est l'invité (voix masculine).\n"
            "Chaque réplique doit être constituée d'UNE SEULE phrase très courte et percutante (maximum 15 mots par réplique) analysant la composition du portefeuille.\n"
            "Le script doit être rédigé EN FRANÇAIS.\n"
            "Tu DOIS répondre UNIQUEMENT sous la forme d'un tableau JSON valide, sans bloc de code markdown, et sans aucune explication avant ou après le JSON. Format exact :\n"
            "[\n"
            "  {\"speaker\": \"A\", \"text\": \"Bonjour. Aujourd'hui nous analysons un portefeuille concentré sur...\"},\n"
            "  {\"speaker\": \"B\", \"text\": \"En effet, l'allocation est fortement exposée aux puces de...\"},\n"
            "  {\"speaker\": \"A\", \"text\": \"Quels sont les principaux risques de cette stratégie ?\"},\n"
            "  {\"speaker\": \"B\", \"text\": \"Le risque de concentration sectorielle reste le point critique.\"}\n"
            "]"
        )
        user_content = f"Voici l'allocation du portefeuille :\n{weights_str}\n\nGénère le dialogue ultra-court au format JSON."
    else:
        system_prompt = (
            "You are an elite financial podcast producer specializing in US tech and AI equities.\n"
            "Generate an ultra-short structured dialogue script (EXACTLY 4 turns total: A, then B, then A, then B) between two analysts.\n"
            "A is the host (female voice) and B is the guest (male voice).\n"
            "Each turn must consist of EXACTLY ONE short and punchy sentence (maximum 15 words per turn) analyzing the portfolio allocation.\n"
            "The script must be written IN ENGLISH.\n"
            "You MUST respond ONLY with a valid JSON array, without markdown code blocks, and without any text before or after the JSON. Exact format:\n"
            "[\n"
            "  {\"speaker\": \"A\", \"text\": \"Hello. Today we are looking at a portfolio focused on...\"},\n"
            "  {\"speaker\": \"B\", \"text\": \"Yes, this allocation has high exposure to...\"},\n"
            "  {\"speaker\": \"A\", \"text\": \"What are the main risks here?\"},\n"
            "  {\"speaker\": \"B\", \"text\": \"The major concern is the high sector concentration.\"}\n"
            "]"
        )
        user_content = f"Here is the portfolio allocation:\n{weights_str}\n\nGenerate the ultra-short dialogue in the required JSON format."

    logger.info(f"Generating dialogue script using model {LITELLM_MODEL} on {LITELLM_URL}...")
    timeout = httpx.Timeout(20.0, connect=5.0)
    
    dialogue_turns = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                LITELLM_URL,
                headers=_llm_headers(),
                json={
                    "model": LITELLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500
                }
            )
            
            if response.status_code != 200:
                logger.error(f"LiteLLM returned status code {response.status_code}: {response.text}")
                raise Exception("AI script generation failed.")
                
            resp_json = response.json()
            content = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if "<think>" in content:
                parts = content.split("</think>")
                if len(parts) >= 2:
                    content = " ".join(parts[1:]).strip()
            
            content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE)
            content = re.sub(r"```$", "", content, flags=re.IGNORECASE).strip()
            
            try:
                dialogue_turns = json.loads(content)
            except Exception as parse_err:
                logger.error(f"Failed to parse JSON script from Content: '{content}'. Error: {parse_err}")
                if lang == "fr":
                    dialogue_turns = [
                        {"speaker": "A", "text": f"Voici l'analyse de votre portefeuille. L'allocation principale est sur {max(normalized, key=normalized.get)}."},
                        {"speaker": "B", "text": "En effet, c'est un choix fort qui présente à la fois des opportunités de croissance et des risques sectoriels."}
                    ]
                else:
                    dialogue_turns = [
                        {"speaker": "A", "text": f"Here is your portfolio analysis. The main allocation is in {max(normalized, key=normalized.get)}."},
                        {"speaker": "B", "text": "Indeed, this is a strong conviction play that offers high growth potential but introduces sector risk."}
                    ]
        except Exception as e:
            logger.error(f"Error during LiteLLM call for script: {e}")
            raise Exception("Analysis server unreachable.")

    if not isinstance(dialogue_turns, list):
        dialogue_turns = []

    # Call TTS server for each line
    temp_files = []
    try:
        tts_timeout = httpx.Timeout(240.0, connect=5.0)
        async with httpx.AsyncClient(timeout=tts_timeout) as client:
            for idx, turn in enumerate(dialogue_turns):
                speaker = str(turn.get("speaker", "A")).upper()
                text = str(turn.get("text", "")).strip()
                if not text:
                    continue
                
                if lang == "fr":
                    if speaker == "A":
                        voice = "ff_siwis(0.85)+af_bella(0.15)"
                        speed = 1.0
                    else:
                        voice = "ff_siwis(0.80)+am_adam(0.20)"
                        speed = 1.05
                else:
                    if speaker == "A":
                        voice = "af_bella"
                        speed = 1.0
                    else:
                        voice = "am_adam"
                        speed = 1.0
                
                logger.info(f"Calling TTS for turn {idx+1}/{len(dialogue_turns)} (Speaker {speaker})")
                tts_resp = await client.post(
                    TTS_API_URL,
                    json={
                        "model": TTS_MODEL,
                        "input": text,
                        "voice": voice,
                        "response_format": "wav",
                        "speed": speed
                    }
                )
                
                if tts_resp.status_code != 200:
                    logger.error(f"TTS server returned status code {tts_resp.status_code}: {tts_resp.text}")
                    raise Exception("Speech synthesis service failed.")
                
                temp_filename = f"temp_chunk_{file_hash}_{idx}.wav"
                temp_filepath = os.path.join(AUDIO_CACHE_DIR, temp_filename)
                with open(temp_filepath, "wb") as f_temp:
                    f_temp.write(tts_resp.content)
                temp_files.append(temp_filepath)

        # Concatenate WAV files
        success = concatenate_wavs(temp_files, cached_filepath)
        if not success:
            raise Exception("Failed to assemble audio file.")
            
        logger.info(f"Successfully generated and cached audio overview: {cached_filepath}")

    except Exception as tts_err:
        if os.path.exists(cached_filepath):
            try:
                os.remove(cached_filepath)
            except Exception:
                pass
        raise tts_err
    finally:
        for temp_f in temp_files:
            if os.path.exists(temp_f):
                try:
                    os.remove(temp_f)
                except Exception:
                    pass

@app.post("/api/audio-overview")
async def generate_audio_overview(request: AudioOverviewRequest):
    weights = request.weights
    lang = request.lang
    
    supported_tickers = {"NVDA", "AMD", "AVGO", "MU", "QCOM", "INTC", "MSFT", "GOOGL", "META", "AMZN"}
    filtered_weights = {ticker: val for ticker, val in weights.items() if ticker in supported_tickers}
    
    total_weight = sum(filtered_weights.values())
    if total_weight <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "fr": "Le poids total du portefeuille doit être supérieur à 0%.",
                "en": "Total portfolio weight must be greater than 0%."
            }
        )
        
    normalized = {ticker: round((val / total_weight) * 100, 2) for ticker, val in filtered_weights.items()}
    
    # Check cache first
    weights_hash_str = json.dumps(sorted(normalized.items()), sort_keys=True) + f"_{lang}"
    file_hash = hashlib.md5(weights_hash_str.encode("utf-8")).hexdigest()
    cached_filename = f"audio_{file_hash}.wav"
    cached_filepath = os.path.join(AUDIO_CACHE_DIR, cached_filename)
    
    if os.path.exists(cached_filepath):
        logger.info(f"Returning cached audio file: {cached_filepath}")
        return {
            "audio_url": f"/api/audio-cache/{cached_filename}",
            "cached": True
        }
        
    # Check if there is an active background task running for this hash
    if file_hash in active_audio_tasks:
        logger.info(f"Audio briefing generation in progress for hash {file_hash}, awaiting running task...")
        try:
            await active_audio_tasks[file_hash]
        except Exception as e:
            logger.error(f"Awaited audio briefing task failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "fr": f"Erreur de synthèse vocale en arrière-plan : {str(e)}",
                    "en": f"Background speech synthesis error: {str(e)}"
                }
            )
            
        if os.path.exists(cached_filepath):
            return {
                "audio_url": f"/api/audio-cache/{cached_filename}",
                "cached": False
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "fr": "La génération en arrière-plan s'est terminée sans produire de fichier.",
                    "en": "Background generation finished without producing an audio file."
                }
            )

    # If no task is running and not cached, we run it now
    logger.info(f"No active task or cache for {file_hash}. Generating synchronously...")
    
    async def run_generation():
        try:
            await perform_audio_generation(normalized, lang, file_hash, cached_filepath)
        finally:
            active_audio_tasks.pop(file_hash, None)
            
    task = asyncio.create_task(run_generation())
    active_audio_tasks[file_hash] = task
    
    try:
        await task
    except Exception as e:
        logger.error(f"Synchronous audio briefing generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "fr": f"Erreur de synthèse vocale : {str(e)}",
                "en": f"Speech synthesis error: {str(e)}"
            }
        )
        
    if os.path.exists(cached_filepath):
        return {
            "audio_url": f"/api/audio-cache/{cached_filename}",
            "cached": False
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "fr": "Échec de la création du fichier audio.",
                "en": "Failed to create audio file."
            }
        )

# ============================
# Research Discovery API (Phase 5)
# ============================

@app.get("/api/research/sectors")
async def get_research_sectors(
    lang: str = Query("fr", pattern="^(fr|en)$")
):
    """Return available sector categories with latest node metadata.

    During an in-flight research cycle, total_nodes for a sector reflects
    only the sectors whose nodes have already been committed by the writer
    connection. A response with node_count=0 while a cycle is starting is
    expected behaviour until the first sector commits — it is not a stale
    reader snapshot (see test_reader_observes_writer_commits_across_connections).
    """
    sectors = get_available_sectors(dag_conn, lang)
    
    # Enrich with sector display info
    result = []
    for s in sectors:
        node_type = s["node_type"]
        display = {
            "sector_key": node_type,
            "label": SECTOR_GROUPS.get(node_type, {}).get("label", {}).get(lang, node_type.replace("_", " ").title()),
            "emoji": SECTOR_GROUPS.get(node_type, {}).get("emoji", "🌐"),
            "latest_update": s.get("latest_created_at"),
            "total_nodes": s.get("total_nodes", 0),
            "ticker_count": s.get("ticker_count", 0),
        }
        
        # Compute freshness
        if s.get("latest_created_at"):
            try:
                created = datetime.fromisoformat(s["latest_created_at"])
                age = datetime.now(timezone.utc) - created
                display["age_hours"] = round(age.total_seconds() / 3600, 1)
                if age < timedelta(hours=24):
                    display["freshness"] = "live"
                elif age < timedelta(days=7):
                    display["freshness"] = "recent"
                else:
                    display["freshness"] = "archived"
            except Exception:
                display["freshness"] = "unknown"
                display["age_hours"] = None
        
        result.append(display)
    
    # Add sectors with no data yet (show as "unavailable")
    existing_keys = {s["sector_key"] for s in result}
    for sector_key, config in SECTOR_GROUPS.items():
        if sector_key not in existing_keys:
            result.append({
                "sector_key": sector_key,
                "label": config["label"].get(lang, sector_key),
                "emoji": config["emoji"],
                "latest_update": None,
                "total_nodes": 0,
                "ticker_count": 0,
                "freshness": "unavailable",
                "age_hours": None
            })
    
    # Always include "global" category
    if "global" not in existing_keys:
        result.insert(0, {
            "sector_key": "global",
            "label": "Global Top 10" if lang == "en" else "Top 10 Global",
            "emoji": "🌐",
            "latest_update": None,
            "total_nodes": 0,
            "ticker_count": 0,
            "freshness": "unavailable",
            "age_hours": None
        })
    
    return {"sectors": result}


@app.get("/api/research/top10")
async def get_research_top10(
    sector: str = Query("global"),
    lang: str = Query("fr", pattern="^(fr|en)$"),
    tier: str = Query("free", pattern="^(free|premium)$")
):
    """
    Core distribution endpoint.
    
    Free tier: Returns canonical node >= 7 days old (zero inference cost).
    Premium tier: Returns canonical node < 24h old (triggers live research if needed).
    """
    canonical = get_latest_canonical(dag_conn, sector, lang)
    
    if tier == "free":
        # Free: serve only if node is at least 7 days old
        if not canonical:
            raise HTTPException(
                status_code=404,
                detail={
                    "fr": f"Aucune analyse gratuite disponible pour le secteur '{sector}'. Lancez un cycle de recherche d'abord.",
                    "en": f"No free analysis available for sector '{sector}'. Run a research cycle first."
                }
            )
        
        try:
            created = datetime.fromisoformat(canonical["created_at"])
            age = datetime.now(timezone.utc) - created
        except Exception:
            age = timedelta(days=0)
        
        if age < timedelta(days=7):
            # Node exists but is too fresh for free tier
            raise HTTPException(
                status_code=403,
                detail={
                    "fr": f"L'analyse pour '{sector}' est disponible en mode Premium uniquement (mise à jour il y a {age.days}j {age.seconds//3600}h). Mode gratuit : 7 jours minimum.",
                    "en": f"Analysis for '{sector}' is available in Premium mode only (updated {age.days}d {age.seconds//3600}h ago). Free mode: 7 days minimum."
                }
            )
        
        return _format_node_response(canonical, "free")
    
    else:  # premium
        if canonical:
            try:
                created = datetime.fromisoformat(canonical["created_at"])
                age = datetime.now(timezone.utc) - created
            except Exception:
                age = timedelta(hours=999)
            
            if age < timedelta(hours=24):
                # Fresh enough — serve immediately
                return _format_node_response(canonical, "premium")
        
        # Stale or missing — trigger live research
        task_key = f"{sector}_{lang}"
        if task_key in active_research_tasks:
            # Already running — await it
            try:
                logger.info(f"Awaiting running research task for {task_key}...")
                await active_research_tasks[task_key]
            except Exception as e:
                logger.error(f"Research task failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "fr": f"La recherche en direct a échoué : {str(e)}",
                        "en": f"Live research failed: {str(e)}"
                    }
                )
        else:
            # Launch live research
            logger.info(f"Triggering live research cycle for {task_key}...")
            
            async def _run_research():
                try:
                    await run_full_research_cycle(lang=lang, db_path=DAG_DB_PATH)
                except Exception as e:
                    logger.error(f"Research cycle error: {e}")
                    raise
                finally:
                    active_research_tasks.pop(task_key, None)
            
            task = asyncio.create_task(_run_research())
            active_research_tasks[task_key] = task
            
            try:
                await task
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "fr": f"Échec du cycle de recherche : {str(e)}",
                        "en": f"Research cycle failed: {str(e)}"
                    }
                )
        
        # Re-fetch the now-fresh canonical node
        canonical = get_latest_canonical(dag_conn, sector, lang)
        if canonical:
            return _format_node_response(canonical, "premium")
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "fr": f"La recherche n'a pas produit de résultats pour '{sector}'.",
                    "en": f"Research did not produce results for '{sector}'."
                }
            )


@app.get("/api/research/graph")
async def get_research_graph(
    node_id: str = Query(...)
):
    """Return the full DAG lineage for a given node."""
    node = get_node(dag_conn, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    tree = get_node_tree(dag_conn, node_id)
    children = get_children(dag_conn, node_id)
    
    return {
        "node": _format_node_data(node),
        "ancestors": [_format_node_data(n) for n in tree[:-1]],
        "children": [_format_node_data(n) for n in children]
    }


@app.post("/api/research/trigger")
async def trigger_research(
    lang: str = Query("fr", pattern="^(fr|en)$")
):
    """Admin endpoint: manually trigger a full research cycle."""
    task_key = f"manual_{lang}"
    
    if task_key in active_research_tasks:
        return {
            "status": "already_running",
            "message": {
                "fr": "Un cycle de recherche est déjà en cours.",
                "en": "A research cycle is already running."
            }
        }
    
    async def _run_research():
        try:
            await run_full_research_cycle(lang=lang, db_path=DAG_DB_PATH)
        except Exception as e:
            logger.error(f"Manual research cycle error: {e}")
            raise
        finally:
            active_research_tasks.pop(task_key, None)
    
    task = asyncio.create_task(_run_research())
    active_research_tasks[task_key] = task
    
    return {
        "status": "started",
        "message": {
            "fr": "Cycle de recherche lancé en arrière-plan.",
            "en": "Research cycle started in background."
        }
    }


def _format_node_data(node: dict) -> dict:
    """Format a DAG node for API response."""
    created = None
    age_hours = None
    freshness = "unknown"
    
    if node.get("created_at"):
        try:
            created = datetime.fromisoformat(node["created_at"])
            age = datetime.now(timezone.utc) - created
            age_hours = round(age.total_seconds() / 3600, 1)
            if age < timedelta(hours=24):
                freshness = "live"
            elif age < timedelta(days=7):
                freshness = "recent"
            else:
                freshness = "archived"
        except Exception:
            pass
    
    return {
        "id": node["id"],
        "parent_id": node.get("parent_id"),
        "created_at": node.get("created_at"),
        "node_type": node["node_type"],
        "lang": node["lang"],
        "hypothesis": node["hypothesis"],
        "tickers": node["tickers"],
        "weights": node["weights"],
        "quant_report": node["quant_report"],
        "audio_url": f"/api/audio-cache/{os.path.basename(node['audio_file'])}" if node.get("audio_file") else None,
        "is_canonical": bool(node.get("is_canonical", 0)),
        "freshness": freshness,
        "age_hours": age_hours
    }


def _format_node_response(node: dict, tier: str) -> dict:
    """Format a full node response for the top10 endpoint."""
    data = _format_node_data(node)
    
    # Add sector display info
    sector_key = node["node_type"]
    lang = node["lang"]
    
    data["sector_label"] = SECTOR_GROUPS.get(sector_key, {}).get("label", {}).get(lang, sector_key.replace("_", " ").title())
    if sector_key == "global":
        data["sector_label"] = "Global Top 10" if lang == "en" else "Top 10 Global"
    data["sector_emoji"] = SECTOR_GROUPS.get(sector_key, {}).get("emoji", "🌐")
    data["tier"] = tier
    
    # Add freshness description
    if data.get("age_hours") is not None:
        hours = data["age_hours"]
        if hours < 1:
            data["freshness_label"] = {
                "fr": f"Généré il y a {int(hours * 60)} minutes",
                "en": f"Generated {int(hours * 60)} minutes ago"
            }
        elif hours < 24:
            data["freshness_label"] = {
                "fr": f"Généré il y a {int(hours)} heures",
                "en": f"Generated {int(hours)} hours ago"
            }
        else:
            days = int(hours / 24)
            data["freshness_label"] = {
                "fr": f"Indexé il y a {days} jour{'s' if days > 1 else ''}",
                "en": f"Indexed {days} day{'s' if days > 1 else ''} ago"
            }
    
    return data


# Serves data file for front-end loading
@app.get("/api/prices")
async def get_prices():
    prices_path = os.path.join(os.path.dirname(__file__), "data", "prices_top10.json")
    if not os.path.exists(prices_path):
        raise HTTPException(
            status_code=404,
            detail={
                "fr": "Fichier de cours financiers manquant. Lancez download_data.py pour le générer.",
                "en": "Financial price data file missing. Run download_data.py to generate it."
            }
        )
    return FileResponse(prices_path, media_type="application/json")

# Serves the landing page UI
@app.get("/")
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "public", "index.html")
    if not os.path.exists(index_path):
        # Create a basic directory structure so it doesn't fail mounting static files
        os.makedirs(os.path.join(os.path.dirname(__file__), "public"), exist_ok=True)
        return {"message": "Server is running. Please add index.html in the public folder."}
    return FileResponse(index_path)

# Serve all other static assets (app.js, index.css, etc.)
os.makedirs(os.path.join(os.path.dirname(__file__), "public"), exist_ok=True)
app.mount("/api/audio-cache", StaticFiles(directory=AUDIO_CACHE_DIR), name="audio-cache")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "public")), name="static")
