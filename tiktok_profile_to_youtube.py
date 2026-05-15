#!/usr/bin/env python3
"""
Aura Engine 2026 - Channel #2 (TikTok Profile Target)
- Fetches videos from a SPECIFIC TikTok Profile
- 11-Layer Anti-Copyright Digital DNA
- SEO 2026 Interest-Graph Optimization
- Daily 2 Uploads Target
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
from datetime import datetime

# ==========================================
# CONFIGURATION (CHANNEL 2)
# ==========================================

LICENSE_KEY       = os.environ.get("SYSTEM_LICENSE_KEY", "").strip() or "COMMUNITY-EDITION"
TIKTOK_PROFILE_ID = os.environ.get("TIKTOK_PROFILE_ID", "").strip() # e.g. @username
WATERMARK_TEXT    = os.environ.get("WATERMARK_TEXT_CH2", "@AURA_CHANNEL").strip()
CLIENT_SECRETS    = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64  = os.environ.get("TOKEN_PICKLE_B64_CH2", "") # Separate for CH2
PRIVACY           = os.environ.get("YT_PRIVACY", "public")
CATEGORY          = os.environ.get("YT_CATEGORY", "24") 
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "").strip()

TIKWM_API         = "https://www.tikwm.com/api"

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
    icons = {"INFO": "✅", "WARN": "⚠️ ", "ERR": "❌", "STEP": "🔄", "SEO": "📈"}
    print(f"[{ts}] {icons.get(level, '•')} (CH2) {msg}", flush=True)

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0: raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def escape_ffmpeg_text(text: str) -> str:
    if not text: return ""
    text = text.replace("'", "").replace(":", "").replace("\\", "\\\\").replace(",", "\\,")
    return text.encode('ascii', 'ignore').decode('ascii').strip()

def setup_dirs():
    for d in [DOWNLOAD_DIR, PROCESSED_DIR]: d.mkdir(parents=True, exist_ok=True)

def write_secrets():
    if not SECRETS_PATH.parent.exists(): SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(CLIENT_SECRETS, encoding="utf-8")
    try:
        TOKEN_PATH.write_bytes(base64.b64decode(TOKEN_PICKLE_B64))
    except Exception as e:
        log(f"Secret Decoding Error: {e}", "ERR"); sys.exit(1)

def get_authenticated_service():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    if not TOKEN_PATH.exists(): return None
    with open(TOKEN_PATH, "rb") as f: creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as f: pickle.dump(creds, f)
        except: return None
    return build("youtube", "v3", credentials=creds)

# ==========================================
# HISTORY & HASH
# ==========================================

def load_history() -> set:
    if not HISTORY_FILE.exists(): return set()
    ids = set()
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if parts: ids.add(parts[0])
    return ids

def save_history(tiktok_id: str, yt_id: str, title: str, file_hash: str = ""):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tiktok_id} | {yt_id} | {ts} | {title[:50]}\n")
    if file_hash:
        with open(HASH_HISTORY, "a", encoding="utf-8") as f: f.write(f"{file_hash}\n")

def get_file_hash(path: Path) -> str:
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""): hasher.update(chunk)
    return hasher.hexdigest()

def is_duplicate_hash(file_hash: str) -> bool:
    if not HASH_HISTORY.exists(): return False
    return file_hash in HASH_HISTORY.read_text(encoding="utf-8")

# ==========================================
# CORE: FETCH FROM PROFILE
# ==========================================

def fetch_profile_videos() -> list[dict]:
    if not TIKTOK_PROFILE_ID:
        log("No TIKTOK_PROFILE_ID set in secrets.", "ERR"); return []
    
    unique_id = TIKTOK_PROFILE_ID.replace("@", "")
    log(f"Scanning profile: @{unique_id}", "STEP")
    
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # TikWM User Posts API
        params = {"unique_id": f"@{unique_id}", "count": 20}
        resp = requests.get(f"{TIKWM_API}/user/posts", params=params, headers=headers, timeout=30)
        data = resp.json()
        if data.get("code") == 0:
            videos = data.get("data", {}).get("videos", [])
            # Filter for vertical, short, quality
            return [v for v in videos if 10 <= v.get("duration", 0) <= 59]
    except Exception as e:
        log(f"Profile fetch error: {e}", "ERR")
    return []

def download_video(v: dict) -> Path | None:
    vid_id = str(v.get("video_id", v.get("id")))
    url = v.get("hdplay") or v.get("play")
    out = DOWNLOAD_DIR / f"{vid_id}.mp4"
    try:
        with requests.get(url, stream=True) as r:
            with open(out, "wb") as f:
                for chunk in r.iter_content(8192): f.write(chunk)
        return out
    except: return None

# ==========================================
# CORE: ZERO-BUFFER PROCESSING (11-LAYER)
# ==========================================

def get_font():
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]
    for p in paths:
        if os.path.exists(p): return p
    return ""

def process_video(input_path: Path, hook_text: str) -> Path | None:
    output_path = PROCESSED_DIR / input_path.name
    log("Applying 11-Layer Anti-Copyright DNA...", "STEP")
    
    d = {
        "pts": round(random.uniform(0.99, 1.01), 4),
        "brightness": round(random.uniform(-0.01, 0.01), 3),
        "contrast": round(random.uniform(1.0, 1.03), 3),
        "hue": round(random.uniform(-1, 1), 1),
        "rotate": round(random.uniform(-0.005, 0.005), 4),
        "zoom": round(random.uniform(1.02, 1.05), 3),
        "fps": random.choice([30, 24]),
        "pitch": round(random.uniform(0.99, 1.01), 3),
    }

    font = get_font()
    font_opt = f":fontfile='{font}'" if font else ""
    safe_hook = escape_ffmpeg_text(hook_text)
    safe_water = escape_ffmpeg_text(WATERMARK_TEXT)
    
    vf = [
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        f"setpts={d['pts']}*PTS",
        f"eq=brightness={d['brightness']}:contrast={d['contrast']}",
        f"hue=h={d['hue']}",
        f"rotate={d['rotate']}:fillcolor=black:ow=iw:oh=ih",
        f"scale=iw*{d['zoom']}:ih*{d['zoom']},crop=1080:1920",
        f"noise=c0s=1:c0f=t",
        f"fps={d['fps']}",
        f"drawtext=text='{safe_hook}':fontcolor=yellow:fontsize=80{font_opt}:x=(w-tw)/2:y=(h-th)/2-100:box=1:boxcolor=black@0.8:enable='between(t,0,1.5)'",
        f"drawtext=text='{safe_water}':fontcolor=white@0.4:fontsize=40{font_opt}:x=(w-tw)/2:y=h*0.8"
    ]
    
    cmd = (
        f'ffmpeg -y -i "{input_path}" -vf "{",".join(vf)}" '
        f'-af "asetrate=44100*{d["pitch"]},atempo={d["pts"]}/{d["pitch"]}" '
        f'-c:v libx264 -preset ultrafast -crf 22 -c:a aac -b:a 128k "{output_path}"'
    )
    
    try:
        run_cmd(cmd)
        return output_path
    except: return None

# ==========================================
# SEO 2026: INTEREST-GRAPH PRO
# ==========================================

def get_ai_meta(raw_title: str) -> dict:
    if not GROQ_API_KEY:
        return {"title": f"{raw_title[:60]} #shorts #viral", "hook": "WATCH THIS", "desc": f"{raw_title}\n\n#shorts #viral", "tags": ["shorts"]}

    prompt = (
        f"Context: {raw_title}. Role: Viral YouTube Architect 2026.\n"
        "Generate Interest-Graph Optimized JSON for Channel #2:\n"
        "1. title: Curiosity-gap title + exactly 3 viral hashtags (under 100 chars).\n"
        "2. hook: 3-word ALL CAPS visual hook.\n"
        "3. desc: 3 lines of deep retention text + exactly 20 niche-viral hashtags.\n"
        "4. tags: 10 viral tags.\n"
        "Ensure JSON format only."
    )
    
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
            timeout=15
        )
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except:
        return {"title": f"Viral Short: {raw_title[:40]} #viral #shorts", "hook": "WATCH NOW", "desc": "#viral #shorts", "tags": ["shorts"]}

# ==========================================
# UPLOAD ENGINE
# ==========================================

def upload_to_yt(youtube, path: Path, meta: dict):
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": meta["title"][:100], "description": meta["desc"], "categoryId": CATEGORY, "tags": meta["tags"]},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
    return response["id"]

# ==========================================
# MAIN EXECUTION (CH2)
# ==========================================

def verify_license():
    log(f"System Check: [{LICENSE_KEY}]", "STEP")
    if LICENSE_KEY == "COMMUNITY-EDITION":
        log("Running Aura Engine CH2: Community Edition", "INFO")
        return
    log("Aura Engine 2026 PRO (CH2): Authorized.", "INFO")

def main():
    try:
        setup_dirs()
        if not CLIENT_SECRETS or not TOKEN_PICKLE_B64:
            log("Auth Secrets Missing for Channel #2.", "ERR"); return
            
        write_secrets()
        verify_license()
        youtube = get_authenticated_service()
        if not youtube: log("Auth Failed (CH2).", "ERR"); return
        
        history_ids = load_history()
        
        # 1. Fetch
        videos = fetch_profile_videos()
        if not videos: log("No profile content found.", "INFO"); return
        
        # 2. Pick New
        target = None
        for v in videos:
            v_id = str(v.get("id"))
            if v_id not in history_ids:
                target = v; break
        
        if not target: log("No new profile videos.", "INFO"); return
        
        # 3. Process
        v_file, p_file = None, None
        try:
            v_file = download_video(target)
            if not v_file: return
            
            f_hash = get_file_hash(v_file)
            if is_duplicate_hash(f_hash):
                log("Duplicate content hash.", "WARN"); return
                
            meta = get_ai_meta(target.get("title", "New Short"))
            p_file = process_video(v_file, meta["hook"])
            
            if p_file:
                yt_id = upload_to_yt(youtube, p_file, meta)
                save_history(str(target.get("id")), yt_id, meta["title"], f_hash)
                log(f"CH2 SUCCESS: https://youtu.be/{yt_id}")
        except Exception as e:
            log(f"Pipeline Error (CH2): {e}", "ERR")
        finally:
            for f in [v_file, p_file]:
                if f and f.exists(): f.unlink()
                
    except Exception as e:
        log(f"Critical Error (CH2): {e}", "ERR")

if __name__ == "__main__":
    main()
