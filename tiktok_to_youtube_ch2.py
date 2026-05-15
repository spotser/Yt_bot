#!/usr/bin/env python3
"""
TikTok (TikWM) → YouTube Shorts (Channel 2: Movie Niche)
- STRICT Profile-only fetching
- Hindi/Hinglish AI Metadata
- Indian Peak Time Optimized
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

TIKTOK_PROFILE_ID = os.environ.get("TIKTOK_PROFILE_ID", "").strip()
CLIENT_SECRETS   = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64 = os.environ.get("TOKEN_PICKLE_B64", "")
PRIVACY          = os.environ.get("YT_PRIVACY", "public")
CATEGORY         = os.environ.get("YT_CATEGORY", "24") 
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "").strip()
WATERMARK_TEXT   = os.environ.get("WATERMARK_TEXT", "@VIRALITY").strip()
CHANNEL_NICHE     = "hindi_movie_narration"

TIKWM_API        = "https://www.tikwm.com/api"

# PATHS
BASE_DIR      = Path("temp_work_ch2")
DOWNLOAD_DIR  = BASE_DIR / "downloads"
PROCESSED_DIR = BASE_DIR / "processed"
HISTORY_FILE  = Path("upload_history_ch2.txt")
HASH_HISTORY  = Path("hash_history_ch2.txt")
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
    if not text: return ""
    text = text.replace("'", "").replace(":", "")
    text = text.replace("\\", "\\\\").replace(",", "\\,")
    return text.encode('ascii', 'ignore').decode('ascii').strip()

def setup_dirs():
    for d in [DOWNLOAD_DIR, PROCESSED_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def validate_env():
    if not TIKTOK_PROFILE_ID or not CLIENT_SECRETS or not TOKEN_PICKLE_B64:
        log("Missing required Environment Secrets (TIKTOK_PROFILE_ID, CLIENT_SECRETS_JSON, TOKEN_PICKLE_B64)", "ERR")
        sys.exit(1)

def write_secrets():
    if not SECRETS_PATH.parent.exists():
        SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(CLIENT_SECRETS, encoding="utf-8")
    try:
        token_data = base64.b64decode(TOKEN_PICKLE_B64)
        TOKEN_PATH.write_bytes(token_data)
        log("Authentication secrets loaded for Channel 2.")
    except Exception as e:
        log(f"Failed to decode TOKEN_PICKLE_B64: {e}", "ERR")
        sys.exit(1)

def get_authenticated_service():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    if not TOKEN_PATH.exists():
        return None
    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as f:
                pickle.dump(creds, f)
            log("Token refreshed.")
        except:
            return None
    return build("youtube", "v3", credentials=creds)

# ==========================================
# CORE LOGIC (STRICT PROFILE ONLY)
# ==========================================

def fetch_videos() -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.tikwm.com/"
    }
    
    profile_id = TIKTOK_PROFILE_ID if TIKTOK_PROFILE_ID.startswith("@") else f"@{TIKTOK_PROFILE_ID}"
    log(f"STRICT MODE: Fetching from Profile {profile_id}...", "STEP")
    
    try:
        # Added a small delay to prevent rate limits
        time.sleep(2)
        params = {"unique_id": profile_id, "count": 20, "cursor": 0}
        resp = requests.get(f"{TIKWM_API}/user/posts", params=params, headers=headers, timeout=30)
        
        if resp.status_code != 200 or not resp.text.strip():
            log(f"TikWM Error {resp.status_code}: Profile may be private or API is down.", "ERR")
            return []
            
        data = resp.json()
        if data.get("code") == 0:
            posts = data.get("data", {}).get("videos", [])
            log(f"Found {len(posts)} videos on profile.")
            return posts
        else:
            log(f"TikWM Msg: {data.get('msg')}", "ERR")
    except Exception as e:
        log(f"Fetch failed: {e}", "ERR")
    return []

def download_video(v: dict) -> Path | None:
    vid_id = str(v.get("video_id", v.get("id")))
    url = v.get("hdplay") or v.get("play")
    if not url: return None
    out = DOWNLOAD_DIR / f"{vid_id}.mp4"
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return out
    except:
        return None

def process_video(input_path: Path, hook_text: str) -> Path | None:
    output_path = PROCESSED_DIR / input_path.name
    d = {
        "pts": round(random.uniform(0.98, 1.02), 4),
        "cw": round(random.uniform(0.97, 0.99), 3),
        "cx": round(random.uniform(0.001, 0.005), 4),
        "brightness": round(random.uniform(-0.02, 0.02), 3),
        "contrast": round(random.uniform(0.98, 1.05), 3),
        "saturation": round(random.uniform(0.98, 1.1), 3),
        "hue": round(random.uniform(-2, 2), 1),
        "rotate": round(random.uniform(-0.01, 0.01), 4),
        "zoom": round(random.uniform(1.01, 1.05), 3),
        "fps": random.choice([29.97, 30, 24]),
        "pitch": round(random.uniform(0.98, 1.02), 3),
    }
    
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not os.path.exists(font_path): font_path = "C:/Windows/Fonts/arialbd.ttf"
    font_config = f"fontfile='{font_path}':" if os.path.exists(font_path) else ""

    safe_text = escape_ffmpeg_text(hook_text)
    safe_watermark = escape_ffmpeg_text(WATERMARK_TEXT)
    
    hook_file = PROCESSED_DIR / f"{input_path.stem}_hook.txt"
    hook_file.write_text("\n".join(textwrap.wrap(safe_text, width=15)), encoding="utf-8")
    hook_file_path = str(hook_file).replace('\\', '/')
    
    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setpts={d['pts']}*PTS,"
        f"crop=iw*{d['cw']}:ih*{d['cw']}:iw*{d['cx']}:ih*{d['cx']},eq=brightness={d['brightness']}:contrast={d['contrast']}:saturation={d['saturation']},"
        f"hue=h={d['hue']},rotate={d['rotate']}:fillcolor=black:ow=iw:oh=ih,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,scale=iw*{d['zoom']}:ih*{d['zoom']},crop=1080:1920,noise=c0s=2:c0f=t+u,unsharp=5:5:0.8:5:5:0.0,fps={d['fps']},"
        f"drawtext={font_config}textfile='{hook_file_path}':fontcolor=yellow:fontsize=80:x=(w-tw)/2:y=(h-th)/2-200:box=1:boxcolor=black@0.8:boxborderw=30:enable='between(t,0,1.0)',"
        f"drawtext={font_config}text='{safe_watermark}':fontcolor=white@0.5:fontsize=40:x=(w-tw)/2:y=h*0.7:shadowcolor=black:shadowx=2:shadowy=2"
    )
    
    cmd = f'ffmpeg -y -i "{input_path}" -vf "{vf}" -af "asetrate=44100*{d["pitch"]},atempo={d["pts"]}/{d["pitch"]},aresample=44100" -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k "{output_path}"'
    try:
        run_cmd(cmd)
        return output_path
    except:
        return None

# ==========================================
# METADATA & HISTORY
# ==========================================

def load_history():
    if not HISTORY_FILE.exists(): return set()
    return {line.split("|")[0].strip() for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if "|" in line}

def save_history(tid, yid, title, fhash):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tid} | {yid} | {datetime.now()} | {title[:50]}\n")
    with open(HASH_HISTORY, "a", encoding="utf-8") as f:
        f.write(f"{fhash}\n")

def generate_ai_metadata(original_title: str) -> str:
    if not GROQ_API_KEY: return None
    prompt = (
        f"You are a Movie Expert. Niche: Hollywood Movie Explanation in HINDI. Video: {original_title}\n"
        f"1. TITLE: 70 chars. Hinglish Curiosity Hook + 3 tags (e.g. #movies #facts).\n"
        f"2. HOOK: 2-3 words ALL CAPS Hindi.\n"
        f"3. DESCRIPTION: 8-10 lines Hindi explanation + 30 hashtags.\n"
        f"Return JSON: {{\"title\": \"...\", \"hook\": \"...\", \"description\": \"...\", \"tags\": []}}"
    )
    try:
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}, timeout=20)
        return resp.json()["choices"][0]["message"]["content"]
    except: return None

# ==========================================
# MAIN
# ==========================================

def main():
    validate_env()
    setup_dirs()
    write_secrets()
    yt = get_authenticated_service()
    if not yt: return
    
    history = load_history()
    videos = fetch_videos()
    
    target = None
    for v in videos:
        if str(v.get("id")) not in history:
            target = v
            break
            
    if not target:
        log("No new videos found on profile.")
        return

    vid_id = str(target.get("id"))
    raw_caption = target.get("title", "Movie Fact")
    v_file = download_video(target)
    if not v_file: return
    
    meta_raw = generate_ai_metadata(raw_caption)
    meta = json.loads(meta_raw) if meta_raw else {"title": raw_caption[:50], "hook": "Wait for it!", "description": "", "tags": []}
    
    p_file = process_video(v_file, meta.get("hook", "WOW!"))
    if not p_file: return
    
    from googleapiclient.http import MediaFileUpload
    body = {"snippet": {"title": meta["title"][:100], "description": meta["description"], "categoryId": CATEGORY, "tags": meta.get("tags", [])}, "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(str(p_file), mimetype="video/mp4", resumable=True)
    
    log(f"Uploading Channel 2: {meta['title'][:50]}")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    
    save_history(vid_id, response["id"], meta["title"], "hash_placeholder")
    log(f"SUCCESS CH2: https://youtube.com/shorts/{response['id']}")

if __name__ == "__main__":
    main()
