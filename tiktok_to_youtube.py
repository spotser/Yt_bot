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

SEARCH_KEYWORDS  = os.environ.get("SEARCH_KEYWORDS", "").strip()
if not SEARCH_KEYWORDS:
    SEARCH_KEYWORDS = "funny viral, comedy clips, desi comedy, hilarious fails, trending comedy"
CLIENT_SECRETS   = os.environ.get("CLIENT_SECRETS_JSON", "")
TOKEN_PICKLE_B64 = os.environ.get("TOKEN_PICKLE_B64", "")
UPLOAD_OLDEST    = os.environ.get("UPLOAD_OLDEST", "false").lower() == "true"
PRIVACY          = os.environ.get("YT_PRIVACY", "public")
CATEGORY         = os.environ.get("YT_CATEGORY", "24") # 24 = Entertainment, 23 = Comedy
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "").strip()

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
    import hashlib
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
        "follow for more", "link in bio", "subscribe", "buy now", "sale", "discount", "promo"
    ]

    # --- SMART KEYWORD EXPANSION ---
    import random
    final_keywords = [k for k in keywords]
    if GROQ_API_KEY and random.random() < 0.3: # 30% chance to expand niche
        try:
            log("Expanding comedy keywords with AI...", "STEP")
            prompt = f"Given these comedy keywords: {SEARCH_KEYWORDS}, suggest 3 more trending sub-niches for viral comedy shorts (e.g. 'desi comedy', 'office fails'). Return ONLY a comma-separated list of 3 keywords."
            
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
                    time.sleep(5)
                    continue
                break
            except Exception as e:
                if retry == 2: raise e
                time.sleep(5)
        
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
                    
                    if duration < 5 or duration > 60: # Slightly relaxed range
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
                
            time.sleep(2)
        except Exception as e:
            log(f"Search error for '{kw}': {e}", "ERR")
            
    log(f"Total {len(all_videos)} videos pooled from all keywords.")
    
    # Sort by Virality 2.0 (Engagement Score)
    # This prioritizes videos that people are actually interacting with
    all_videos.sort(key=lambda x: x.get("engagement_score", 0), reverse=True)
    
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

def process_video(input_path: Path, hook_text: str) -> Path | None:
    """Smart Scaling: Keeps aspect ratio, adds black bars if needed to make it 1080x1920"""
    output_path = PROCESSED_DIR / input_path.name
    log("Processing video (Scaling, Mirroring, Thumbnail Hook, Watermark)...", "STEP")
    
    # FFmpeg filters setup
    # Using a common Linux font path for GitHub Actions compatibility
    # Also checking common Windows font paths
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
            
    font_path_fixed = font_path.replace('\\', '/')
    font_opt = f"fontfile='{font_path_fixed}'" if font_path else ""
    
    # Safe text for FFmpeg (remove emojis/special chars that cause boxes)
    safe_text = hook_text.encode('ascii', 'ignore').decode('ascii').strip().replace("'", "").replace(":", "")
    
    # 1. Thumbnail Hook: Big yellow text in the middle, visible only for first 0.8 seconds
    font_config = f"{font_opt}:" if font_opt else ""
    thumb_hook = f"drawtext={font_config}text='{safe_text}':fontcolor=yellow:fontsize=90:x=(w-text_w)/2:y=(h-text_h)/2-150:box=1:boxcolor=black@0.7:boxborderw=25:enable='between(t,0,0.8)'"
    
    # 2. Watermark: Bottom right corner
    watermark = f"drawtext={font_config}text='@VIRALITY':fontcolor=white@0.6:fontsize=45:x=w-tw-50:y=h-th-100:shadowcolor=black:shadowx=2:shadowy=2"

    # Digital Footprint Modification (Subtle enough to be invisible, strong enough for Content ID)
    # - unsharp: Sharpens edges slightly
    # - eq: Tiny boost to contrast and saturation
    # - atempo: 1% speed increase (shifts audio fingerprint)
    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        f"unsharp=5:5:0.8:5:5:0.8,"
        f"eq=brightness=0.01:contrast=1.03:saturation=1.05,"
        f"{thumb_hook},"
        f"{watermark}"
    )
    
    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf}" '
        f'-af "atempo=1.01" '
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

def upload_to_youtube(video_path: Path, title: str, description: str, tags: list):
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
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  ⏳ Upload Progress: {int(status.progress() * 100)}%", end="\r")
            
    log(f"Upload Complete! ID: {response['id']}")
    return response["id"]

# ==========================================
# AI ENHANCEMENTS (GROQ)
# ==========================================

def generate_ai_metadata(original_title: str) -> str:
    if not GROQ_API_KEY:
        return None
        
    log("Generating AI Metadata using Groq...", "STEP")
    prompt = (
        f"You are a viral YouTube Shorts SEO expert.\n"
        f"Video Topic: {original_title}\n\n"
        f"Generate a viral package for this video.\n"
        f"1. TITLE: Max 50 chars, high-CTR, use emojis. (Shorts Title)\n"
        f"2. HOOK: Max 3 words, ALL CAPS (for video overlay).\n"
        f"3. DESCRIPTION: 2-3 lines of engaging text + hashtags.\n"
        f"4. TAGS: Exactly 5-7 highly relevant tags.\n\n"
        f"Format as JSON: {{\"title\": \"...\", \"hook\": \"...\", \"description\": \"...\", \"tags\": [...]}}"
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
            timeout=20
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"AI Generation failed: {e}", "WARN")
        return None

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    # Human-like randomness: Wait between 10 seconds to 5 minutes before starting
    # This ensures GitHub Actions don't hit the API at the exact same minute every day
    import random
    delay = random.randint(10, 300)
    log(f"Human-like delay initiated: Waiting for {int(delay/60)} minutes and {delay%60} seconds...", "STEP")
    time.sleep(delay)

    validate_env()
    setup_dirs()
    write_secrets()
    
    history = load_history()
    videos = fetch_videos()
    
    if not videos:
        log("No videos found for search keywords.", "WARN")
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

    vid_id = str(target.get("video_id", target.get("id")))
    raw_caption = target.get("title", "") or "New Short"
    
    # --- Smart Caption Rewrite & SEO ---
    ai_meta = None
    if GROQ_API_KEY:
        try:
            raw_ai = generate_ai_metadata(raw_caption)
            if raw_ai:
                import json
                ai_meta = json.loads(raw_ai)
                log("AI Metadata generated successfully.")
        except Exception as e:
            log(f"Failed to parse AI JSON: {e}", "WARN")

    if ai_meta:
        clean_title = ai_meta.get("title", raw_caption[:50])
        hook = ai_meta.get("hook", "Wait for it! 😂")
        final_description = ai_meta.get("description", "")
        chosen_tags = ai_meta.get("tags", ["Shorts", "Viral"])
    else:
        # Fallback to legacy logic
        hooks = [
            "Wait for it! 😂", "Must Watch! 🤣", "Ending will kill you! 💀",
            "Try not to laugh! 😆", "This is hilarious! 🚀", "Tag a friend who would do this 👇",
            "Best comedy video today! 🌟", "Omg! I can't stop laughing 🤣"
        ]
        
        # 1. Clean original caption
        clean_orig = re.sub(r'#(tiktok|fyp|foryou|foryoupage|tik_tok)\S*', '', raw_caption, flags=re.IGNORECASE)
        clean_orig = re.sub(r'\s+', ' ', clean_orig).strip()
        
        # 2. Rewrite Title
        hook = random.choice(hooks)
        clean_title = f"{hook} {clean_orig}"
        clean_title = re.sub(r'[<>]', '', clean_title).strip()[:100]
        
        if not clean_orig: clean_title = f"{hook} Shorts - {vid_id}"
        
        # 3. Dynamic Description & Tags Variations (Comedy Focused)
        desc_templates = [
            (
                f"{clean_title}\n\nAapko ye video kaisi lagi? Comment mein bataein! 👇\n\n"
                f"✅ Subscribe for more daily comedy & viral shorts!\n🔥 Keep smiling and sharing.\n\n",
                ["Shorts", "Comedy", "Funny", "Viral", "Hilarious", "Trending", "Laugh"]
            ),
            (
                f"🔥 {clean_title}\n\nDon't forget to like and share if this made you laugh! 😂\n"
                f"🔔 Hit the subscribe button for daily funny videos!\n\n",
                ["Shorts", "FunnyVideo", "ComedyShorts", "ViralComedy", "Meme", "Lol", "Daily"]
            ),
            (
                f"✨ {clean_title}\n\nTag a friend who needs to see this! 🗣️👇\n"
                f"👉 Subscribe to our channel for the best comedy content!\n\n",
                ["Shorts", "Trending", "MustWatch", "FunnyClips", "DesiComedy", "Prank", "Haha"]
            )
        ]
        
        chosen_desc_template, chosen_tags = random.choice(desc_templates)
        final_description = f"{chosen_desc_template}#Shorts #Viral #Trending"
    
    # Download
    v_file = download_video(target)
    if not v_file: return
    
    # --- CRITICAL DUPLICATE CHECK (HASH) ---
    file_hash = get_file_hash(v_file)
    if is_duplicate_hash(file_hash):
        log("ABORT: Content already exists in history (Same video, different ID). Skipping.", "WARN")
        if v_file.exists(): v_file.unlink()
        return
    
    # Process
    p_file = process_video(v_file, hook)
    if not p_file: return
    
    # Upload
    try:
        # Pass the dynamically chosen tags to the upload function
        yt_id = upload_to_youtube(p_file, clean_title, final_description, chosen_tags)
        save_history(vid_id, yt_id, clean_title, file_hash)
        log(f"SUCCESS: https://youtube.com/shorts/{yt_id}")
    except Exception as e:
        log(f"YouTube Upload Failed: {e}", "ERR")
    finally:
        # Cleanup
        if v_file.exists(): v_file.unlink()
        if p_file.exists(): p_file.unlink()

if __name__ == "__main__":
    main()
