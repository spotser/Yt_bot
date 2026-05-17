#!/usr/bin/env python3
"""
TikTok (yt-dlp Profile Scraper) → YouTube Shorts (Channel 2: BOLTAS CLIPS)
- Fetches videos from a specific TikTok profile using yt-dlp
- Smart Upscale: 1080x1920 with padding (no stretching)
- Metadata: Auto-extracts title and generates perfect Hollywood SEO using Groq AI
- Watermark: Overlaying watermark text only (no kinetic hook text)
- GitHub Actions Ready: Uses env secrets
"""

import os
import re
import sys
import json
import base64
import pickle
import subprocess
import requests
import time
import random
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ==========================================
# CONFIGURATION
# ==========================================

TIKTOK_PROFILE_ID = os.environ.get("TIKTOK_PROFILE_ID", "").strip()
CLIENT_SECRETS    = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64  = os.environ.get("TOKEN_PICKLE_B64_CH2", "")
PRIVACY           = os.environ.get("YT_PRIVACY", "public")
CATEGORY          = os.environ.get("YT_CATEGORY", "24") # 24 = Entertainment (Perfect for Movie Clips)
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "").strip()
WATERMARK_TEXT    = os.environ.get("WATERMARK_TEXT_CH2", "@BOLTAS CLIPS").strip()

# PATHS
BASE_DIR      = Path("temp_work_ch2")
DOWNLOAD_DIR  = BASE_DIR / "downloads"
PROCESSED_DIR = BASE_DIR / "processed"
HISTORY_FILE  = Path("upload_history_ch2.txt")
HASH_HISTORY  = Path("hash_history_ch2.txt")
TOKEN_PATH    = BASE_DIR / "token_ch2.pickle"
SECRETS_PATH  = BASE_DIR / "client_secrets_ch2.json"
YT_DLP_ARCHIVE = BASE_DIR / "downloaded_ch2.txt"

# ==========================================
# HELPERS
# ==========================================

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "✅", "WARN": "⚠️ ", "ERR": "❌", "STEP": "🔄"}
    print(f"[{ts}] {icons.get(level, '•')}  {msg}", flush=True)

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def escape_ffmpeg_text(text: str) -> str:
    """Escapes special characters for FFmpeg drawtext filter."""
    if not text: return ""
    # Remove characters that are extremely problematic
    text = text.replace("'", "").replace(":", "")
    # Escape backslash and comma
    text = text.replace("\\", "\\\\").replace(",", "\\,")
    # Remove non-ascii characters to be safe with most fonts
    return text.encode('ascii', 'ignore').decode('ascii').strip()

def setup_dirs():
    for d in [DOWNLOAD_DIR, PROCESSED_DIR]:
        if d.exists():
            # Clean up old files to avoid conflicts between runs
            for f in d.glob("*"):
                try:
                    f.unlink()
                except Exception as e:
                    pass
        d.mkdir(parents=True, exist_ok=True)

def validate_env():
    if not TIKTOK_PROFILE_ID or not CLIENT_SECRETS or not TOKEN_PICKLE_B64:
        log("Missing required Environment Secrets (TIKTOK_PROFILE_ID, CLIENT_SECRETS_JSON, TOKEN_PICKLE_B64_CH2)", "ERR")
        sys.exit(1)

def write_secrets():
    if not SECRETS_PATH.parent.exists():
        SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        
    SECRETS_PATH.write_text(CLIENT_SECRETS, encoding="utf-8")
    try:
        token_data = base64.b64decode(TOKEN_PICKLE_B64)
        TOKEN_PATH.write_bytes(token_data)
        log("Authentication secrets loaded into temporary workspace.")
    except Exception as e:
        log(f"Failed to decode TOKEN_PICKLE_B64_CH2 secret: {e}", "ERR")
        sys.exit(1)

def get_authenticated_service():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    
    if not TOKEN_PATH.exists():
        log("Token file missing. Ensure TOKEN_PICKLE_B64_CH2 is set correctly.", "ERR")
        return None

    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        log("Token expired. Attempting to refresh...", "STEP")
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as f:
                pickle.dump(creds, f)
            log("Token refreshed successfully.")
        except Exception as e:
            log(f"Failed to refresh token: {e}", "ERR")
            return None
    elif creds and creds.expired and not creds.refresh_token:
        log("CRITICAL: Token is expired and NO refresh token found. You must regenerate the token using generate_token.py locally.", "ERR")
        return None

    return build("youtube", "v3", credentials=creds)

# ==========================================
# HISTORY MANAGEMENT
# ==========================================

def load_history() -> tuple[set, set]:
    if not HISTORY_FILE.exists():
        return set(), set()
    ids = set()
    titles = set()
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 1: ids.add(parts[0])
            if len(parts) >= 4: titles.add(parts[3].lower())
    return ids, titles

def save_history(tiktok_id: str, yt_id: str, title: str, file_hash: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("# TikTok → YouTube Channel 2 History\n\n", encoding="utf-8")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tiktok_id} | {yt_id} | {ts} | {title[:50]}\n")
    
    if file_hash:
        with open(HASH_HISTORY, "a", encoding="utf-8") as f:
            f.write(f"{file_hash}\n")
            
    log(f"History and hash updated for video {tiktok_id}")

def get_file_hash(path: Path) -> str:
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def is_duplicate_hash(file_hash: str) -> bool:
    if not HASH_HISTORY.exists():
        return False
    hashes = HASH_HISTORY.read_text(encoding="utf-8").splitlines()
    return file_hash in [h.strip() for h in hashes if h.strip()]

# ==========================================
# YT-DLP DOWNLOAD LOGIC
# ==========================================

def download_video_ch2() -> tuple[Path, str] | None:
    profile_url = f"https://www.tiktok.com/@{TIKTOK_PROFILE_ID.lstrip('@')}"
    log(f"Downloading from TikTok profile: {profile_url}", "STEP")
    
    # We want to run yt-dlp to download exactly one new video
    cmd = [
        "yt-dlp",
        profile_url,
        "--download-archive", str(YT_DLP_ARCHIVE),
        "--socket-timeout", "300",
        "--retries", "100",
        "--fragment-retries", "100",
        "--concurrent-fragments", "1",
        "-f", "wv*[vcodec*=avc1]+wa/b[ext=mp4]/b",
        "-S", "res:720",
        "--force-ipv4",
        "--playlist-items", "1-10",  # Check top 10 recent videos
        "--max-downloads", "1",      # Download exactly 1 new video
        "--write-info-json",        # Save metadata to parse caption
        "-o", str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    ]
    
    try:
        log("Running yt-dlp to fetch the latest video...", "STEP")
        # Run yt-dlp command (no check=True so we can inspect return code)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 101 is the official yt-dlp success code when max-downloads is hit.
        # 0 is returned when it successfully completes (e.g., checks and finds no new videos to download).
        if result.returncode not in [0, 101]:
            log(f"yt-dlp failed with exit code {result.returncode}.", "ERR")
            log(f"yt-dlp stdout:\n{result.stdout}", "ERR")
            log(f"yt-dlp stderr:\n{result.stderr}", "ERR")
            return None
            
        log(f"yt-dlp completed successfully (exit code: {result.returncode}).")
    except Exception as e:
        log(f"yt-dlp execution failed: {e}", "ERR")
        return None
        
    # Search for downloaded files (any compatible video format)
    video_files = []
    for ext in ["*.mp4", "*.mkv", "*.webm", "*.mov"]:
        video_files.extend(DOWNLOAD_DIR.glob(ext))
        
    if not video_files:
        log("No new videos downloaded by yt-dlp (profile might be empty or all recent videos already in archive).", "INFO")
        return None
        
    v_file = video_files[0]
    vid_id = v_file.stem
    
    # Read the .info.json file to get the raw description/caption
    info_json_path = DOWNLOAD_DIR / f"{vid_id}.info.json"
    raw_caption = ""
    if info_json_path.exists():
        try:
            with open(info_json_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                raw_caption = meta_data.get("title", "") or meta_data.get("description", "") or "New Movie Clip"
        except Exception as e:
            log(f"Failed to read info.json: {e}", "WARN")
            raw_caption = "New Movie Clip"
    else:
        raw_caption = "New Movie Clip"
        
    # Clean up the JSON file early to avoid issues
    if info_json_path.exists():
        try:
            info_json_path.unlink()
        except:
            pass
            
    return v_file, raw_caption

# ==========================================
# VIDEO PROCESSING (ANTI-COPYRIGHT + WATERMARK)
# ==========================================

def process_video(input_path: Path) -> Path | None:
    """
    11-Layer Anti-Copyright Filter System (Digital DNA)
    - Customized for Hollywood Clips with Watermark only (no hook text)
    - Randomized Visual & Audio fingerprinting
    - Resolution-independent scaling
    - Subtle watermark centered at 30% from bottom
    """
    output_path = PROCESSED_DIR / f"processed_{input_path.name}"
    log("Processing movie clip with 11-Layer Anti-Copyright DNA Hack...", "STEP")
    
    # --- RANDOMIZED DNA PARAMETERS ---
    d = {
        "pts": round(random.uniform(0.98, 1.02), 4),       # Speed shift
        "cw": round(random.uniform(0.97, 0.99), 3),        # Crop width (97-99%)
        "cx": round(random.uniform(0.001, 0.005), 4),      # Crop offset
        "brightness": round(random.uniform(-0.02, 0.02), 3),
        "contrast": round(random.uniform(0.98, 1.05), 3),
        "saturation": round(random.uniform(0.98, 1.1), 3),
        "hue": round(random.uniform(-2, 2), 1),            # Subtle hue shift
        "rotate": round(random.uniform(-0.01, 0.01), 4),   # Invisible tilt
        "zoom": round(random.uniform(1.01, 1.05), 3),      # Ken Burns static zoom
        "fps": random.choice([29.97, 30, 24]),             # Variable frame rate
        "pitch": round(random.uniform(0.98, 1.02), 3),     # Audio pitch shift
    }

    # Font Setup
    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux (GitHub Actions)
        "C:\\Windows\\Fonts\\arialbd.ttf",                      # Windows Bold
        "C:\\Windows\\Fonts\\arial.ttf"                         # Windows Regular
    ]
    font_path = ""
    for f in possible_fonts:
        if os.path.exists(f):
            font_path = f
            break
    
    if not font_path:
        log("No system fonts found. Falling back to default FFmpeg font.", "WARN")
        font_config = ""
    else:
        font_path_fixed = font_path.replace('\\', '/')
        font_config = f"fontfile='{font_path_fixed}':"

    # Safe text for FFmpeg
    safe_watermark = escape_ffmpeg_text(WATERMARK_TEXT)
    
    # Watermark: Centered horizontally, 30% from bottom
    watermark = f"drawtext={font_config}text='{safe_watermark}':fontcolor=white@0.3:fontsize=35:x=(w-tw)/2:y=h*0.75:shadowcolor=black@0.5:shadowx=2:shadowy=2"

    # --- 11 LAYER 2026 FILTER CHAIN (DNA HACK) ---
    v_filters = [
        f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", # Layer 1: Standardize
        f"setpts={d['pts']}*PTS",                                               # Layer 2: Speed shift
        f"crop=iw*{d['cw']}:ih*{d['cw']}:iw*{d['cx']}:ih*{d['cx']}",            # Layer 3: Jitter Crop
        f"eq=brightness={d['brightness']}:contrast={d['contrast']}:saturation={d['saturation']}:gamma=1.05", # Layer 4: Color DNA
        f"hue=h={d['hue']}",                                                    # Layer 5: Subtle Tint
        f"rotate={d['rotate']}:fillcolor=black:ow=iw:oh=ih",                    # Layer 6: Micro-tilt
        f"vignette=PI/4+0.1*sin(t)",                                          # Layer 7: Dynamic Vignette (Anti-Bot)
        f"noise=c0s=3:c0f=t+u",                                                 # Layer 8: Grain Jitter
        f"unsharp=3:3:1.2:3:3:0.0",                                             # Layer 9: Sharpness Boost
        f"fps={d['fps']}",                                                      # Layer 10: Frame rate shift
        watermark,                                                              # Layer 11: Subtle Watermark
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"   # Final: Lock Resolution
    ]
    
    # Filter out empty strings from v_filters
    v_filters = [f for f in v_filters if f]
    vf = ",".join(v_filters)
    
    # Audio filters: Pitch and Speed
    af = f"asetrate=44100*{d['pitch']},atempo={d['pts']}/{d['pitch']},aresample=44100"

    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -preset veryfast -crf 22 '
        f'-c:a aac -b:a 192k '
        f'"{output_path}"'
    )
    
    try:
        run_cmd(cmd)
        return output_path
    except Exception as e:
        log(f"FFmpeg failed: {e}", "ERR")
        return None

# ==========================================
# YOUTUBE UPLOADER WITH SCHEDULING
# ==========================================

def upload_to_youtube(youtube, video_path: Path, title: str, description: str, tags: list):
    from googleapiclient.http import MediaFileUpload
    
    # CALCULATE PERFECT TIMING (Indian Peak Time Fix)
    # Target Indian times: 2:00 PM (14:00) IST and 9:00 PM (21:00) IST
    # Which corresponds to UTC: 08:30 and 15:30
    now = datetime.now(timezone.utc)
    target_utc_hours = [8, 15]
    
    cron_schedule = os.environ.get("CRON_SCHEDULE", "").strip()
    
    if "30 8" in cron_schedule:
        target_hour = 8
    elif "30 15" in cron_schedule:
        target_hour = 15
    else:
        # Fallback to nearest slot if manual run or missing cron
        target_hour = target_utc_hours[0]
        for h in target_utc_hours:
            if now.hour <= h + 2:
                target_hour = h
                break
            
    target_time = now.replace(hour=target_hour, minute=30, second=0, microsecond=0)
    if target_hour < now.hour - 2:  # Handle next day wrap-around
        target_time = target_time + timedelta(days=1)
    
    # If the script ran so late that the target time is less than 15 mins away (or past),
    # YouTube API will reject publishAt. In that case, publish exactly 15 mins from NOW.
    if target_time < now + timedelta(minutes=15):
        target_time = now + timedelta(minutes=15)
        
    publish_at_iso = target_time.isoformat().replace('+00:00', 'Z')
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": CATEGORY,
            "tags": tags
        },
        "status": {
            "privacyStatus": "private",  # Must be private to use publishAt
            "publishAt": publish_at_iso,
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=1024*1024*5)
    
    log(f"Uploading to YouTube: {title[:50]}...", "STEP")
    
    # Retry logic for upload
    for attempt in range(3):
        try:
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"  ⏳ Upload Progress: {int(status.progress() * 100)}%", end="\r")
            
            log(f"Upload Complete! ID: {response['id']}")
            return response["id"]
        except Exception as e:
            if "quotaExceeded" in str(e):
                log("CRITICAL: YouTube API Quota Exceeded for today.", "ERR")
                return None
            log(f"Upload attempt {attempt+1} failed: {e}", "WARN")
            if attempt < 2: time.sleep(5)
            else: raise e
    return None

# ==========================================
# AI ENHANCEMENTS (GROQ)
# ==========================================

def generate_ai_metadata(original_title: str) -> str:
    if not GROQ_API_KEY:
        return None
        
    log("Generating AI Metadata using Groq for BOLTAS CLIPS...", "STEP")
    prompt = (
        f"You are a YouTube Shorts Growth Expert. Target Audience: Hindi movie explanation, summaries, and Hollywood clips lovers in India.\n"
        f"Current Date: {datetime.now().strftime('%B %d, %Y')}\n"
        f"Video Caption: {original_title}\n\n"
        f"Generate an ULTRA-PERFECT SEO metadata package in Hinglish/Hindi for the 2026 Algorithm:\n"
        f"1. TITLE: Exactly 70 characters. Use Curiosity Gap in Hinglish/Hindi + 1 High-Energy Movie Emoji (like 🎬, 🍿, 😱, 🔥). First 40 chars = HINDI/HINGLISH HOOK. Last 30 chars = 3 trending hashtags including #movieexplainedinhindi.\n"
        f"2. DESCRIPTION: High-retention semantic formatting in Hinglish/Hindi:\n"
        f"   - Line 1: Emotional movie hook/quote in Hinglish/Hindi in ALL CAPS. DO NOT use any markdown asterisks (**).\n"
        f"   - Line 2-5: Engaging movie trivia, hindi explanation summary, or emotional cliffhanger that keeps Hindi viewers hooked.\n"
        f"   - Line 6: Strong CTA (Subscribe to BOLTAS CLIPS for more Hollywood Movie Clips in Hindi / Hindi Movie Summaries).\n"
        f"   - Block: EXACTLY 20 trending movie-related hashtags (e.g., #movies, #cinema, #movieclips, #explainedinhindi, #movieexplainedinhindi). No more, no less.\n"
        f"3. TAGS: 15 specific semantic tags related to movies and Hindi narrated movie explanations.\n\n"
        f"IMPORTANT: No placeholders. Valid JSON ONLY. NEVER USE '**' OR ANY MARKDOWN BOLDING.\n"
        f"Format: {{\"title\": \"...\", \"description\": \"...\", \"tags\": [...]}}"
    )
    
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}
            },
            timeout=25
        )
        if resp.status_code != 200:
            log(f"Groq API Error Body: {resp.text}", "ERR")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"AI Generation failed: {e}", "WARN")
        return None

def get_final_metadata(raw_caption: str, video_id: str) -> dict:
    """Consolidated metadata logic: AI first, then fallback."""
    ai_meta = None
    if GROQ_API_KEY:
        try:
            raw_ai = generate_ai_metadata(raw_caption)
            if raw_ai:
                ai_meta = json.loads(raw_ai)
                log("AI Metadata generated successfully.")
        except Exception as e:
            log(f"AI Metadata parsing failed: {e}", "WARN")

    if ai_meta:
        return {
            "title": ai_meta.get("title", raw_caption[:50]),
            "description": ai_meta.get("description", ""),
            "tags": ai_meta.get("tags", ["Shorts", "Viral"])
        }
    
    # --- FALLBACK LOGIC (HOLLYWOOD MOVIE CLIPS HINDI NARRATED) ---
    log("Using Hollywood Movie Clips Hindi Narrated fallback metadata logic.", "INFO")
    hooks = [
        "क्या इसने सही किया?", "इसने सबको हैरान कर दिया!", "ये कोई सोच भी नहीं सकता था!",
        "आखिरकार सच सामने आ गया!", "इसने अपनी जान दांव पर लगा दी!", "यह सीन देखकर रोंगटे खड़े हो जाएंगे!",
        "इसने तो इतिहास ही रच दिया!", "आखिर इसने ऐसा क्यों किया?", "ये सीन कभी मत भूलना!"
    ]
    
    # Clean original caption
    clean_orig = re.sub(r'#(tiktok|fyp|foryou|foryoupage|tik_tok)\S*', '', raw_caption, flags=re.IGNORECASE)
    clean_orig = re.sub(r'\s+', ' ', clean_orig).strip()
    
    hook = random.choice(hooks)
    title_hashtags = "#movies #explainedinhindi #movieclips"
    if clean_orig and len(clean_orig) > 5:
        clean_title = f"{hook} {clean_orig[:30]} {title_hashtags}"
    else:
        clean_title = f"{hook} - Hollywood Movie Scene {title_hashtags}"
    
    clean_title = re.sub(r'[<>]', '', clean_title).strip()[:100]
    
    # 3. Dynamic Description & Exactly 20 Hashtags
    trending_20 = (
        "#movies #cinema #movieclips #explainedinhindi #movieexplainedinhindi "
        "#storyexplainedinhindi #hindiexplanation #filmidubbed #hollywoodmoviesinhindi "
        "#cinemahindi #summaryinhindi #epicscenes #bestmovies #cinematic #trending "
        "#shorts #viral #fyp #mustwatch #boltasclips"
    )
    
    desc_templates = [
        (
            f"क्या आपने कभी इस शानदार फिल्म को देखा है? {clean_title}\n\n"
            f"हॉलीवुड की सबसे बेहतरीन कहानियों का हिंदी एक्सप्लेनेशन और रोंगटे खड़े कर देने वाले सीन्स। 👇\n\n"
            f"✅ ऐसे ही और भी हॉलीवुड मूवीज के हिंदी एक्सप्लेनेशन के लिए BOLTAS CLIPS को सब्सक्राइब करें!\n🍿 देखते रहिये।\n\n"
            f"{trending_20}",
            ["movies", "cinema", "movieclips", "explainedinhindi", "movieexplainedinhindi", "shorts", "viral"]
        ),
        (
            f"यह सीन सच में आपकी सोच बदल देगा। {clean_title}\n\n"
            f"सिनेमा के इतिहास का एक बेहद ही खूबसूरत और दिलचस्प हिस्सा हिंदी नरेशन के साथ। 👇\n\n"
            f"🔔 रोज़ाना बेहतरीन मूवी क्लिप्स और एक्सप्लेनेशन्स के लिए BOLTAS CLIPS को सब्सक्राइब करना न भूलें!\n\n"
            f"{trending_20}",
            ["epicscene", "cinematic", "storyexplainedinhindi", "hindiexplanation", "popcorn", "shorts", "viral"]
        )
    ]
    
    chosen_desc, chosen_tags = random.choice(desc_templates)
    
    premium_desc = (
        f"🎬 {chosen_desc.split('.')[0]}.\n"
        f"बेहतरीन हॉलीवुड मूवीज़ के सीन्स, यादगार डायलॉग्स और शानदार कहानी का हिंदी एक्सप्लेनेशन।\n"
        f"Welcome to BOLTAS CLIPS, your ultimate home for the greatest movie summaries.\n"
        f"अगर आपको एक्सप्लेनेशन पसंद आया हो तो कमेंट्स में ज़रूर बताएं कि आपका पसंदीदा पार्ट कौन सा था!\n"
        f"🚀 सिनेमा लवर्स की इस फैमिली का हिस्सा बनें।\n"
        f"✅ Subscribe to BOLTAS CLIPS for more epic movie moments.\n\n"
        f"{chosen_desc.split('👇')[-1].strip() if '👇' in chosen_desc else chosen_desc}"
    )
    
    return {
        "title": clean_title,
        "description": premium_desc,
        "tags": chosen_tags
    }

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    validate_env()
    setup_dirs()
    write_secrets()
    
    # 0. Verify Auth Early
    youtube = get_authenticated_service()
    if not youtube:
        log("Authentication failed. Aborting process to save quota/time.", "ERR")
        return
    
    history_ids, history_titles = load_history()
    
    # 1. Download TikTok Video via yt-dlp
    download_res = download_video_ch2()
    if not download_res:
        log("CRITICAL: Failed to download any new movie clip. Exiting...", "ERR")
        return
        
    v_file, raw_caption = download_res
    vid_id = v_file.stem
    
    # Verify by ID deduplication layer
    if vid_id in history_ids:
        log(f"Video {vid_id} already exists in history. Aborting.", "WARN")
        if v_file.exists(): v_file.unlink()
        return
        
    # Metadata Generation
    meta = get_final_metadata(raw_caption, vid_id)
    
    # --- TITLE DUPLICATION CHECK ---
    if meta["title"].lower() in history_titles:
        log(f"Title '{meta['title']}' already exists in history. Adding randomness...", "WARN")
        meta["title"] = f"{meta['title']} | {random.randint(10,99)}"
    
    # --- CRITICAL DUPLICATE CHECK (HASH) ---
    file_hash = get_file_hash(v_file)
    if is_duplicate_hash(file_hash):
        log("ABORT: Content already exists in history (Same video, different ID). Skipping.", "WARN")
        if v_file.exists(): v_file.unlink()
        return
    
    # Process
    p_file = None
    try:
        p_file = process_video(v_file)
        if not p_file:
            log("Video processing failed.", "ERR")
            return
        
        # Upload
        yt_id = upload_to_youtube(youtube, p_file, meta["title"], meta["description"], meta["tags"])
        if yt_id:
            save_history(vid_id, yt_id, meta["title"], file_hash)
            log(f"SUCCESS: https://youtube.com/shorts/{yt_id}")
        else:
            log("YouTube Upload failed.", "ERR")
    except Exception as e:
        log(f"Process/Upload Failed: {e}", "ERR")
    finally:
        # Cleanup files
        for f in [v_file, p_file]:
            if f and f.exists():
                try:
                    f.unlink()
                except:
                    pass

if __name__ == "__main__":
    main()
