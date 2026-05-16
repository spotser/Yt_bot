#!/usr/bin/env python3
"""
TikTok (TikWM) → YouTube Shorts (Optimized)
- Fetches videos from TikWM API
- Smart Upscale: 1080x1920 with padding (no stretching)
- Metadata: Auto-extracts title and hashtags
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
import gdown
from pathlib import Path
from datetime import datetime
import textwrap

# ==========================================
# CONFIGURATION
# ==========================================

SEARCH_KEYWORDS  = os.environ.get("SEARCH_KEYWORDS", "").strip()
if not SEARCH_KEYWORDS:
    SEARCH_KEYWORDS = "stoic wisdom, psychology facts, ancient stoicism, human behavior secrets, dark psychology hacks, marcus aurelius quotes, mental toughness"
CLIENT_SECRETS   = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64 = os.environ.get("TOKEN_PICKLE_B64", "")
UPLOAD_OLDEST    = os.environ.get("UPLOAD_OLDEST", "false").lower() == "true"
PRIVACY          = os.environ.get("YT_PRIVACY", "public")
CATEGORY         = os.environ.get("YT_CATEGORY", "24") # 24 = Entertainment, 23 = Comedy
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "").strip()
DRIVE_FOLDER_URL = os.environ.get("DRIVE_FOLDER_URL", "").strip()
WATERMARK_TEXT   = os.environ.get("WATERMARK_TEXT", "@VIRALITY").strip()

TIKWM_API        = "https://www.tikwm.com/api"

# PATHS
BASE_DIR      = Path("temp_work")
DOWNLOAD_DIR  = BASE_DIR / "downloads"
PROCESSED_DIR = BASE_DIR / "processed"
HISTORY_FILE  = Path("upload_history.txt")
HASH_HISTORY  = Path("hash_history.txt")
TOKEN_PATH    = BASE_DIR / "token.pickle"
SECRETS_PATH  = BASE_DIR / "client_secrets.json"

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
        d.mkdir(parents=True, exist_ok=True)

def validate_env():
    if not SEARCH_KEYWORDS or not CLIENT_SECRETS or not TOKEN_PICKLE_B64:
        log("Missing required Environment Secrets (SEARCH_KEYWORDS, CLIENT_SECRETS_JSON, TOKEN_PICKLE_B64)", "ERR")
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
        log(f"Failed to decode TOKEN_PICKLE_B64 secret: {e}", "ERR")
        sys.exit(1)

def get_authenticated_service():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    
    if not TOKEN_PATH.exists():
        log("Token file missing. Ensure TOKEN_PICKLE_B64 is set correctly.", "ERR")
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
        HISTORY_FILE.write_text("# TikTok → YouTube History\n\n", encoding="utf-8")
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
# CORE LOGIC
# ==========================================

def fetch_videos() -> list[dict]:
    keywords = [k.strip() for k in SEARCH_KEYWORDS.split(",") if k.strip()]
    all_videos = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.tikwm.com/",
        "Accept-Language": "en-US,en;q=0.9"
    }

    # Comprehensive Filter List to ensure maximum copyright safety and faceless content
    SKIP_WORDS = [
        # News Channels & Brands
        "news", "aajtak", "abp", "zeenews", "ndtv", "republic", "dainik", "bhaskar", "indiatv", "bbc", "cnn", "fox", "timesnow", "tv9", "news18", "thehindu", "breaking", "press conference", "exclusive report", "journalist", "reporter",
        # Personal/Vlog/Talking Head (Face/Voice)
        "vlog", "storytime", "podcast", "interview", "grwm", "my voice", "day in my life", "get ready with me", "daily vlog", "my morning", "my night", "my story", "qna", "q&a",
        # Movies/TV Shows/Web Series (High Copyright Risk)
        "movie", "cinema", "netflix", "prime", "episode", "season", "trailer", "teaser", "actor", "actress", "bollywood", "hollywood", "tollywood", "scene", "series", "webseries", "director",
        # Music/Songs/Labels (High Copyright Risk)
        "official video", "music video", "song", "tseries", "vevo", "singer", "album", "lyrics", "cover", "remix", "lofi", "dj ", "mtv",
        # Sports/Events (High Copyright Risk)
        "ipl", "bcci", "icc", "wwe", "football", "cricket", "nba", "fifa", "ufc", "wrestling", "match", "highlights", "sports", "premier league", "champions",
        # Generic/Spam
        "follow for more", "link in bio", "subscribe", "buy now", "sale", "discount", "promo",
        "part 1", "part 2", "part 3", "continuation", "to be continued" # Avoid split parts
    ]

    # --- 2026 VIRAL KEYWORD INJECTION ---
    VIRAL_MODIFIERS = ["viral", "trending", "4k", "pov", "mindset", "motivation", "success", "aesthetic"]
    
    # --- SMART KEYWORD EXPANSION ---
    final_keywords = [k for k in keywords]
    if GROQ_API_KEY:
        try:
            log("Expanding niche keywords with AI (2026 Mode)...", "STEP")
            prompt = f"Given these niches: {SEARCH_KEYWORDS}, suggest 5 more hyper-specific trending sub-niches for viral shorts. Avoid generic terms. Return ONLY a comma-separated list."
            
            # Simple direct call to Groq for keyword expansion
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                },
                timeout=15
            )
            expansion = resp.json()["choices"][0]["message"]["content"].strip()
            if expansion and "," in expansion:
                new_kws = [k.strip() for k in expansion.split(",") if k.strip()]
                log(f"AI suggested new niches: {new_kws}")
                final_keywords.extend(new_kws)
        except Exception as e:
            log(f"Expansion failed: {e}", "WARN")

    for kw in final_keywords:
        log(f"Searching for viral videos: '{kw}'...", "STEP")
        for retry in range(3):
            try:
                params = {"keywords": kw, "count": 20, "cursor": 0, "hd": 1}
                resp = requests.get(f"{TIKWM_API}/feed/search", params=params, headers=headers, timeout=30)
                
                if "Just a moment" in resp.text or resp.status_code == 403:
                    log(f"Cloudflare block detected (Attempt {retry+1}/3).", "WARN")
                    time.sleep(2)
                    continue
                break
            except Exception as e:
                if retry == 2: raise e
                time.sleep(2)
        
        # Rate limiting for Free API (1 request/second)
        time.sleep(1.5)
        
        try:
            data = resp.json()
            if data.get("code") == 0:
                posts = data.get("data", {}).get("videos", [])
                filtered = []
                for p in posts:
                    # 1. Author/Niche Filtering
                    author_name = p.get("author", {}).get("nickname", "").lower()
                    author_id = p.get("author", {}).get("unique_id", "").lower()
                    if any(word in author_name or word in author_id for word in SKIP_WORDS):
                        continue
                        
                    # 2. Premium Content Filter (Resolution & Length)
                    duration = p.get("duration", 0)
                    width = p.get("width", 0)
                    height = p.get("height", 0)
                    
                    if duration < 10 or duration > 59: # 10s to 59s only for Shorts perfection
                        # log(f"Skipping {p.get('id')}: Duration {duration}s", "DEBUG")
                        continue
                        
                    # If width/height is missing, we check if it's likely vertical
                    if width > 0 and height > 0:
                        if height < width: # Horizontal video
                            continue
                    
                    # 3. Recency Filter
                    create_time = p.get("create_time", 0)
                    if create_time:
                        days_old = (time.time() - create_time) / (24 * 3600)
                        if days_old > 10: # Increased to 10 days to find better quality
                            continue
                            
                    # 4. Virality 2.0 (Calculate Engagement Score)
                    views = p.get("play_count", 0)
                    likes = p.get("digg_count", 0)
                    comments = p.get("comment_count", 0)
                    shares = p.get("share_count", 0)
                    
                    # Engagement Ratio (Avoid division by zero)
                    if views > 1000:
                        p["engagement_score"] = (likes + comments + shares) / views
                    else:
                        p["engagement_score"] = 0
                        
                    filtered.append(p)
                
                log(f"Found {len(posts)} videos for '{kw}' (Kept {len(filtered)} after Premium filtering).")
                all_videos.extend(filtered)
            else:
                log(f"Search API Error for '{kw}': {data.get('msg')}", "WARN")
                
            # Removed delay for faster execution as requested
        except Exception as e:
            log(f"Search error for '{kw}': {e}", "ERR")
            
    log(f"Total {len(all_videos)} videos pooled from all keywords.")
    
    # Sort by Virality 2.0 (Engagement Score)
    # This prioritizes videos that people are actually interacting with
    all_videos.sort(key=lambda x: x.get("engagement_score", 0), reverse=True)
    
    return all_videos

# ==========================================
# DRIVE SOURCING (AURA UPGRADE)
# ==========================================

def extract_id(link_or_id: str) -> str | None:
    if not link_or_id: return None
    # Support for folders, file links, and direct IDs
    match = re.search(r'(?:folders/|id=|/d/|/file/d/)([a-zA-Z0-9_-]{25,})', link_or_id)
    return match.group(1) if match else link_or_id

def download_from_drive(drive_url: str) -> Path | None:
    target_id = extract_id(drive_url)
    if not target_id: return None
    
    log(f"Sourcing from Google Drive: {target_id}", "STEP")
    try:
        # Step 1: Try to treat it as a FOLDER first (Scrape file IDs)
        is_folder = "folders" in drive_url or "embeddedfolderview" in drive_url
        
        if is_folder:
            url = f"https://drive.google.com/embeddedfolderview?id={target_id}"
            resp = requests.get(url, timeout=15)
            file_ids = list(set(re.findall(r'\"([a-zA-Z0-9_-]{28,35})\"', resp.text)))
            
            if file_ids:
                random.shuffle(file_ids)
                history = load_history()
                
                final_id = None
                for fid in file_ids:
                    if fid not in history:
                        final_id = fid
                        break
                
                if not final_id:
                    log("All videos in Drive folder have already been uploaded.", "INFO")
                    return None
                target_id = final_id
            else:
                log("No files found in folder view. Attempting direct file download...", "INFO")
        
        # Step 2: Download the file (Directly or from Folder selection)
        out = DOWNLOAD_DIR / f"drive_{target_id}.mp4"
        log(f"Downloading from Drive: {target_id}...", "STEP")
        
        # Use gdown for robust download
        result = gdown.download(id=target_id, output=str(out), quiet=False)
        
        if out.exists():
            # Check if it's a ZIP
            if out.suffix.lower() == ".zip" or "zip" in str(result).lower():
                log("WARNING: Downloaded file is a ZIP. YouTube automation only supports .mp4/.mov.", "WARN")
                # Attempting to rename if gdown changed suffix
                if not out.exists() and Path(str(result)).exists():
                    out = Path(str(result))
            return out
            
    except Exception as e:
        log(f"Drive fetch failed: {e}", "ERR")
    return None

def download_video(v: dict) -> Path | None:
    vid_id = str(v.get("video_id", v.get("id")))
    url = v.get("hdplay") or v.get("play")
    
    if not url:
        log("No download URL found!", "ERR")
        return None
        
    out = DOWNLOAD_DIR / f"{vid_id}.mp4"
    log(f"Downloading {vid_id}...", "STEP")
    
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return out
    except Exception as e:
        log(f"Download failed: {e}", "ERR")
        return None

def process_video(input_path: Path, hook_text: str) -> Path | None:
    """
    11-Layer Anti-Copyright Filter System (Digital DNA)
    - Randomized Visual & Audio fingerprinting
    - Resolution-independent scaling
    - Centered watermark at 30% from bottom
    """
    output_path = PROCESSED_DIR / input_path.name
    log("Processing video with 11-Layer Anti-Copyright Filter...", "STEP")
    
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
    safe_text = escape_ffmpeg_text(hook_text)
    safe_watermark = escape_ffmpeg_text(WATERMARK_TEXT)
    
    # --- DYNAMIC FONT SIZING & WRAPPING FOR HOOK ---
    # Standard is 90. If text is long, we wrap it and shrink it.
    wrapped_text = safe_text
    base_font_size = 90
    
    if len(safe_text) > 15:
        # Wrap at approx 15-20 characters per line for vertical video (1080px)
        wrapped_text = "\n".join(textwrap.wrap(safe_text, width=15))
        base_font_size = 80
    if len(safe_text) > 30:
        wrapped_text = "\n".join(textwrap.wrap(safe_text, width=18))
        base_font_size = 65
    if len(safe_text) > 50:
        wrapped_text = "\n".join(textwrap.wrap(safe_text, width=22))
        base_font_size = 50

    # 1. Kinetic Thumbnail Hook: Big pulsing yellow text
    # 2026 Hack: The hook stays for 3s, fades out, and reappears for the last 2s.
    hook_file = PROCESSED_DIR / f"{input_path.stem}_hook.txt"
    hook_file.write_text(wrapped_text, encoding="utf-8")
    hook_file_path = str(hook_file).replace('\\', '/')
    
    thumb_hook = (
        f"drawtext={font_config}textfile='{hook_file_path}':fontcolor=yellow:fontsize={base_font_size}:"
        f"x=(w-tw)/2:y=(h-th)/2-200:box=1:boxcolor=black@0.8:boxborderw=30:fix_bounds=1:line_spacing=10:"
        f"enable='between(t,0,0.5)'"
    )
    
    # 2. Watermark: Centered horizontally, 30% from bottom
    watermark = f"drawtext={font_config}text='{safe_watermark}':fontcolor=white@0.3:fontsize=35:x=(w-tw)/2:y=h*0.75:shadowcolor=black@0.5:shadowx=2:shadowy=2"

    # --- 11 LAYER 2026 FILTER CHAIN (DNA HACK) ---
    v_filters = [
        f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", # Layer 1: Standardize
        f"setpts={d['pts']}*PTS",                                               # Layer 2: Speed shift
        f"crop=iw*{d['cw']}:ih*{d['cw']}:iw*{d['cx']}:ih*{d['cx']}",            # Layer 3: Jitter Crop
        f"eq=brightness={d['brightness']}:contrast={d['contrast']}:saturation={d['saturation']}:gamma=1.05", # Layer 4: Color DNA
        f"hue=h={d['hue']}",                                                    # Layer 5: Subtle Tint
        f"rotate={d['rotate']}:fillcolor=black:ow=iw:oh=ih",                    # Layer 6: Micro-tilt
        f"vignette='PI/4+0.1*sin(T)'",                                          # Layer 7: Dynamic Vignette (Anti-Bot)
        f"noise=c0s=3:c0f=t+u",                                                 # Layer 8: Grain Jitter
        f"unsharp=3:3:1.2:3:3:0.0",                                             # Layer 9: Sharpness Boost
        f"fps={d['fps']}",                                                      # Layer 10: Frame rate shift
        thumb_hook,                                                             # Layer 11a: Kinetic Hook
        watermark,                                                              # Layer 11b: Subtle Watermark
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"   # Final: Lock Resolution
    ]
    
    vf = ",".join(v_filters)
    
    # Audio filters: Pitch and Speed
    af = f"asetrate=44100*{d['pitch']},atempo={d['pts']}/{d['pitch']},aresample=44100"

    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -preset slow -crf 18 '
        f'-c:a aac -b:a 192k '
        f'"{output_path}"'
    )
    
    try:
        run_cmd(cmd)
        return output_path
    except Exception as e:
        log(f"FFmpeg failed: {e}", "ERR")
        return None

def upload_to_youtube(youtube, video_path: Path, title: str, description: str, tags: list):
    from googleapiclient.http import MediaFileUpload
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": CATEGORY,
            "tags": tags
        },
        "status": {
            "privacyStatus": PRIVACY,
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
        
    log("Generating AI Metadata using Groq...", "STEP")
    prompt = (
        f"You are a YouTube Shorts Growth Expert. Target Audience: Stoicism/Psychology.\n"
        f"Current Date: {datetime.now().strftime('%B %d, %Y')}\n"
        f"Video Topic: {original_title}\n\n"
        f"Generate an ULTRA-PERFECT SEO metadata package for 2026 Algorithm:\n"
        f"1. TITLE: Exactly 70 characters. Use Curiosity Gap + 1 High-Energy Emoji. First 40 chars = HOOK. Last 30 chars = 3 hashtags.\n"
        f"2. HOOK: 2-3 words in ALL CAPS (e.g., 'STAY COLD', 'ALPHA TRUTH').\n"
        f"3. DESCRIPTION: High-retention semantic formatting:\n"
        f"   - Line 1: Emotional hook using Unicode bold (if possible) or caps.\n"
        f"   - Line 2-5: Deep value proposition.\n"
        f"   - Line 6: Strong CTA (Subscribe).\n"
        f"   - Block: 25 trending hashtags in the niche.\n"
        f"4. TAGS: 15 specific semantic tags.\n\n"
        f"IMPORTANT: No placeholders. Valid JSON ONLY.\n"
        f"Format: {{\"title\": \"...\", \"hook\": \"...\", \"description\": \"...\", \"tags\": [...]}}"
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
            "hook": ai_meta.get("hook", "Wait for it! 😂"),
            "description": ai_meta.get("description", ""),
            "tags": ai_meta.get("tags", ["Shorts", "Viral"])
        }
    
    # --- FALLBACK LOGIC (STOICISM & PSYCHOLOGY) ---
    log("Using Stoicism/Psychology fallback metadata logic.", "INFO")
    hooks = [
        "CONTROL YOUR MIND", "ANCIENT WISDOM", "STAY CALM",
        "BE UNSTOPPABLE", "PSYCHOLOGY TRICK", "STOP COMPLAINING",
        "MASTER EMOTIONS", "STOIC MINDSET", "THE HARD TRUTH"
    ]
    
    # 1. Clean original caption
    clean_orig = re.sub(r'#(tiktok|fyp|foryou|foryoupage|tik_tok)\S*', '', raw_caption, flags=re.IGNORECASE)
    clean_orig = re.sub(r'\s+', ' ', clean_orig).strip()
    
    # 2. Rewrite Title with 3 hashtags
    hook = random.choice(hooks)
    title_hashtags = "#stoic #mindset #wisdom"
    if clean_orig and len(clean_orig) > 5:
        clean_title = f"{hook}: {clean_orig[:40]} {title_hashtags}"
    else:
        clean_title = f"{hook} - Ancient Wisdom {title_hashtags}"
    
    clean_title = re.sub(r'[<>]', '', clean_title).strip()[:100]
    
    # 3. Dynamic Description (8-10 Lines) & 25-30 Hashtags
    trending_30 = (
        "#stoicism #psychology #mindset #wisdom #mentalstrength #stoicquotes "
        "#humanbehavior #darkpsychology #growth #selfimprovement #discipline "
        "#motivation #shorts #viral #trending #dailywisdom #stoic #lifehacks "
        "#success #mentalhealth #sigma #stoicmindset #psychologyfacts #mindsetmatters "
        "#ancientwisdom #discipline #focus #power #control #mindsetshift"
    )
    
    desc_templates = [
        (
            f"Control your mind, control your life. {clean_title}\n\n"
            f"Master the art of Stoicism and understand the human mind to become unstoppable. 👇\n\n"
            f"✅ Subscribe for daily wisdom & psychology secrets.\n🏛️ Stay Stoic.\n\n"
            f"{trending_30}",
            ["Stoicism", "Psychology", "Mindset", "Wisdom", "MentalStrength", "StoicQuotes", "Viral", "Shorts"]
        ),
        (
            f"The secret to a peaceful life lies in your perspective. {clean_title}\n\n"
            f"Deep dive into human behavior and ancient philosophy for a better you.\n"
            f"🔔 Subscribe for your daily dose of mental toughness!\n\n"
            f"{trending_30}",
            ["PsychologyFacts", "StoicMindset", "Motivation", "SelfImprovement", "AncientWisdom", "Viral", "Shorts"]
        )
    ]
    
    chosen_desc, chosen_tags = random.choice(desc_templates)
    
    # Ensure description is "Badhiya" (8-10 Lines + 30 Hashtags)
    premium_desc = (
        f"🏛️ {chosen_desc.split('.')[0]}.\n"
        f"Master your mind before it masters you.\n"
        f"Ancient wisdom meets modern psychology to build an unbreakable spirit.\n"
        f"Stop letting external factors control your inner peace.\n"
        f"Become the master of your emotions and your destiny.\n"
        f"Focus on what you can control, and ignore the rest.\n"
        f"🚀 Join the tribe of the mentally strong.\n"
        f"✅ Subscribe for Daily Wisdom & Psychology Secrets.\n\n"
        f"{trending_30}"
    )
    
    return {
        "title": clean_title,
        "hook": hook,
        "description": premium_desc,
        "tags": chosen_tags
    }

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    # Removed human-like delay as requested for instant execution
    # delay = random.randint(5, 60)
    # log(f"Human-like delay initiated: Waiting for {delay} seconds...", "STEP")
    # time.sleep(delay)

    validate_env()
    setup_dirs()
    write_secrets()
    
    # 0. Verify Auth Early
    youtube = get_authenticated_service()
    if not youtube:
        log("Authentication failed. Aborting process to save quota/time.", "ERR")
        return
    
    history_ids, history_titles = load_history()
    
    # 1. Try Sourcing from Drive (Priority)
    target = None
    v_file = None
    vid_id = None
    raw_caption = ""

    if DRIVE_FOLDER_URL:
        drive_links = [l.strip() for l in DRIVE_FOLDER_URL.split(",") if l.strip()]
        random.shuffle(drive_links)
        
        for link in drive_links:
            v_file = download_from_drive(link)
            if v_file:
                vid_id = v_file.stem.replace("drive_", "")
                if vid_id in history_ids:
                    log(f"Video {vid_id} already in history. Skipping...", "INFO")
                    v_file.unlink()
                    v_file = None
                    continue
                    
                raw_caption = f"Drive Content {vid_id}"
                log(f"Successfully sourced from Drive: {vid_id}")
                break
            else:
                log(f"No usable video found in Drive link: {link[:40]}...", "INFO")

    # 2. Fallback to TikTok Scraper (with Retry Logic for Schedule Reliability)
    if not v_file:
        videos = fetch_videos()
        if not videos:
            log("Primary keywords failed. Trying fallback niche to save schedule...", "WARN")
            # Dynamic fallback to ensure NO SCHEDULE IS MISSED
            os.environ["SEARCH_KEYWORDS"] = "stoic wisdom, success motivation"
            videos = fetch_videos()
            
        if not videos:
            log("No videos found even after fallback. Aborting.", "ERR")
            return

        if UPLOAD_OLDEST:
            videos.reverse()
            
        # Try top 10 videos in order of engagement to find a valid download
        for v in videos[:10]:
            temp_vid_id = str(v.get("video_id", v.get("id")))
            if temp_vid_id not in history_ids:
                log(f"Attempting to download video candidate: {temp_vid_id}")
                v_file = download_video(v)
                if v_file:
                    vid_id = temp_vid_id
                    raw_caption = v.get("title", "") or "New Short"
                    break
                else:
                    log(f"Download failed for {temp_vid_id}, trying next...", "WARN")

    if not v_file:
        log("CRITICAL: Failed to source any video after multiple attempts. Schedule might be missed!", "ERR")
        return
    
    # Metadata
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
        p_file = process_video(v_file, meta["hook"])
        if not p_file:
            log("Video processing failed.", "ERR")
            return
        
        # Upload
        yt_id = upload_to_youtube(youtube, p_file, meta["title"], meta["description"], meta["tags"])
        save_history(vid_id, yt_id, meta["title"], file_hash)
        log(f"SUCCESS: https://youtube.com/shorts/{yt_id}")
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
        
        # Cleanup hook text file
        try:
            hook_file = PROCESSED_DIR / f"{v_file.stem}_hook.txt"
            if hook_file.exists(): hook_file.unlink()
        except:
            pass

if __name__ == "__main__":
    main()
