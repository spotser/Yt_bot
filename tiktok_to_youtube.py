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
from pathlib import Path
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

SEARCH_KEYWORDS   = os.environ.get("SEARCH_KEYWORDS", "India viral, Hindi funny")
CLIENT_SECRETS   = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64 = os.environ.get("TOKEN_PICKLE_B64", "")
UPLOAD_OLDEST    = os.environ.get("UPLOAD_OLDEST", "false").lower() == "true"
PRIVACY          = os.environ.get("YT_PRIVACY", "public")
CATEGORY         = os.environ.get("YT_CATEGORY", "22") # 22 = People & Blogs

TIKWM_API        = "https://www.tikwm.com/api"

# PATHS
BASE_DIR      = Path("temp_work")
DOWNLOAD_DIR  = BASE_DIR / "downloads"
PROCESSED_DIR = BASE_DIR / "processed"
HISTORY_FILE  = Path("upload_history.txt")
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

def setup_dirs():
    for d in [DOWNLOAD_DIR, PROCESSED_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def validate_env():
    if not SEARCH_KEYWORDS or not CLIENT_SECRETS or not TOKEN_PICKLE_B64:
        log("Missing required Environment Secrets (SEARCH_KEYWORDS, CLIENT_SECRETS_JSON, TOKEN_PICKLE_B64)", "ERR")
        sys.exit(1)

def write_secrets():
    SECRETS_PATH.write_text(CLIENT_SECRETS, encoding="utf-8")
    try:
        TOKEN_PATH.write_bytes(base64.b64decode(TOKEN_PICKLE_B64))
        log("Authentication secrets loaded.")
    except Exception as e:
        log(f"Failed to decode TOKEN_PICKLE_B64: {e}", "ERR")
        sys.exit(1)

# ==========================================
# HISTORY MANAGEMENT
# ==========================================

def load_history() -> set:
    if not HISTORY_FILE.exists():
        return set()
    ids = set()
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line.split("|")[0].strip())
    return ids

def save_history(tiktok_id: str, yt_id: str, title: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("# TikTok → YouTube History\n\n", encoding="utf-8")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tiktok_id} | {yt_id} | {ts} | {title[:50]}\n")
    log(f"History updated for video {tiktok_id}")

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

    # News channels to skip
    SKIP_WORDS = ["news", "aajtak", "abp", "zeenews", "ndtv", "republic", "dainik", "bhaskar", "indiatv", "bbc"]

    for kw in keywords:
        log(f"Searching for viral videos: '{kw}'...", "STEP")
        try:
            params = {"keywords": kw, "count": 20, "cursor": 0, "hd": 1}
            resp = requests.get(f"{TIKWM_API}/feed/search", params=params, headers=headers, timeout=30)
            
            if "Just a moment" in resp.text or resp.status_code == 403:
                log(f"Cloudflare block detected for keyword '{kw}'.", "WARN")
                continue

            data = resp.json()
            if data.get("code") == 0:
                posts = data.get("data", {}).get("videos", [])
                filtered = []
                for p in posts:
                    author_name = p.get("author", {}).get("nickname", "").lower()
                    author_id = p.get("author", {}).get("unique_id", "").lower()
                    
                    # Check if any skip word is in author name or id
                    if any(word in author_name or word in author_id for word in SKIP_WORDS):
                        continue
                    filtered.append(p)
                
                log(f"Found {len(posts)} videos for '{kw}' (Kept {len(filtered)} after News filtering).")
                all_videos.extend(filtered)
            else:
                log(f"Search API Error for '{kw}': {data.get('msg')}", "WARN")
                
            time.sleep(2)
        except Exception as e:
            log(f"Search error for '{kw}': {e}", "ERR")
            
    log(f"Total {len(all_videos)} videos pooled from all keywords.")
    return all_videos

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

def process_video(input_path: Path) -> Path | None:
    """Smart Scaling: Keeps aspect ratio, adds black bars if needed to make it 1080x1920"""
    output_path = PROCESSED_DIR / input_path.name
    log("Processing video (Scaling to 1080x1920)...", "STEP")
    
    # FFmpeg filter: Scale, Pad, and Add Watermark (@VIRALITY)
    # Using a common Linux font path for GitHub Actions compatibility
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    drawtext = f"drawtext=text='@VIRALITY':fontcolor=white@0.6:fontsize=45:x=w-tw-50:y=h-th-100:shadowcolor=black:shadowx=2:shadowy=2"
    
    # Add fontfile if it exists (mostly for local Windows testing, but good for safety)
    if os.path.exists(font_path):
        drawtext = f"drawtext=fontfile='{font_path}':text='@VIRALITY':fontcolor=white@0.6:fontsize=45:x=w-tw-50:y=h-th-100:shadowcolor=black:shadowx=2:shadowy=2"

    vf = (
        f"hflip," # Mirror effect to bypass copyright detection
        f"scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        f"{drawtext}"
    )
    
    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf}" '
        f'-c:v libx264 -preset fast -crf 22 '
        f'-c:a aac -b:a 128k '
        f'"{output_path}"'
    )
    
    try:
        run_cmd(cmd)
        return output_path
    except Exception as e:
        log(f"FFmpeg failed: {e}", "ERR")
        return None

def upload_to_youtube(video_path: Path, title: str, description: str):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
    
    # Load Credentials
    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)
        
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
            
    youtube = build("youtube", "v3", credentials=creds)
    
    # Dynamic Tags for better SEO
    viral_tags = ["Shorts", "Viral", "Trending", "Hindi", "India", "Fact", "Entertainment", "Comedy", "Gadgets", "Amazing"]
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": CATEGORY,
            "tags": viral_tags
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=1024*1024*5)
    
    log(f"Uploading to YouTube: {title[:50]}...", "STEP")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  ⏳ Upload Progress: {int(status.progress() * 100)}%", end="\r")
            
    log(f"Upload Complete! ID: {response['id']}")
    return response["id"]

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    validate_env()
    setup_dirs()
    write_secrets()
    
    history = load_history()
    videos = fetch_videos()
    
    if not videos:
        log("No videos found on profile.", "WARN")
        return

    if UPLOAD_OLDEST:
        videos.reverse()
        
    # Find next video to upload
    target = None
    for v in videos:
        vid_id = str(v.get("video_id", v.get("id")))
        if vid_id not in history:
            target = v
            break
            
    if not target:
        log("Everything is up to date. No new videos.", "INFO")
        return

    # --- Smart Caption Rewrite & SEO ---
    import random
    hooks = [
        "Wait for it! 😱", "Must Watch! 🔥", "Ending will shock you! 🤯",
        "Watch till end! ✨", "This is unbelievable! 🚀", "Did you know this? 🤔",
        "Best video today! 🌟", "Omg! Look at this 💎"
    ]
    
    # 1. Clean original caption
    clean_orig = re.sub(r'#(tiktok|fyp|foryou|foryoupage|tik_tok)\S*', '', raw_caption, flags=re.IGNORECASE)
    clean_orig = re.sub(r'\s+', ' ', clean_orig).strip()
    
    # 2. Rewrite Title
    hook = random.choice(hooks)
    # Combine Hook + Clean Caption
    clean_title = f"{hook} {clean_orig}"
    clean_title = re.sub(r'[<>]', '', clean_title).strip()[:100]
    
    if not clean_orig: clean_title = f"{hook} Shorts - {vid_id}"
    
    # 3. Dynamic Description
    final_description = (
        f"{clean_title}\n\n"
        f"Aapko ye video kaisi lagi? Comment mein bataein! 👇\n\n"
        f"✅ Subscribe for more viral shorts!\n"
        f"🔥 Daily amazing content from across the web.\n\n"
        f"#Shorts #Viral #India #Trending #Amazing #Fact #Hindi"
    )
    
    # Download
    v_file = download_video(target)
    if not v_file: return
    
    # Process
    p_file = process_video(v_file)
    if not p_file: return
    
    # Upload
    try:
        yt_id = upload_to_youtube(p_file, clean_title, final_description)
        save_history(vid_id, yt_id, clean_title)
        log(f"SUCCESS: https://youtube.com/shorts/{yt_id}")
    except Exception as e:
        log(f"YouTube Upload Failed: {e}", "ERR")
    finally:
        # Cleanup
        if v_file.exists(): v_file.unlink()
        if p_file.exists(): p_file.unlink()

if __name__ == "__main__":
    main()
