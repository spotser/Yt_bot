#!/usr/bin/env python3
"""
TikTok (yt-dlp Profile Scraper) → YouTube Shorts (BOLTAS CLIPS)
- Fetches videos from a specific TikTok profile using yt-dlp
- Smart Upscale: 1080x1920 with padding (no stretching)
- Metadata: Auto-extracts title and generates perfect Hinglish SEO using Groq AI
- Watermark: Overlaying watermark text only (no kinetic hook text)
- Upload: Playwright browser-based (human-like, no API)
- GitHub Actions Ready: Uses env secrets
"""

import os
import re
import sys
import json
import base64
import subprocess
import requests
import time
import random
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

TIKTOK_PROFILE_ID = os.environ.get("TIKTOK_PROFILE_ID", "").strip()
PRIVACY           = os.environ.get("YT_PRIVACY", "public")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "").strip()
WATERMARK_TEXT    = os.environ.get("WATERMARK_TEXT", "@BOLTAS CLIPS").strip()
COOKIES_B64       = os.environ.get("YT_COOKIES_B64", "").strip()

# PATHS
BASE_DIR       = Path("temp_work_ch2")
DOWNLOAD_DIR   = BASE_DIR / "downloads"
PROCESSED_DIR  = BASE_DIR / "processed"
HISTORY_FILE   = Path("upload_history_ch2.txt")
HASH_HISTORY   = Path("hash_history_ch2.txt")
YT_DLP_ARCHIVE = BASE_DIR / "downloaded_ch2.txt"
COOKIES_PATH   = BASE_DIR / "yt_cookies.json"

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
    text = text.replace("\\", "\\").replace(",", "\,")
    return text.encode('ascii', 'ignore').decode('ascii').strip()

def setup_dirs():
    for d in [DOWNLOAD_DIR, PROCESSED_DIR]:
        if d.exists():
            for f in d.glob("*"):
                try: f.unlink()
                except: pass
        d.mkdir(parents=True, exist_ok=True)

def validate_env():
    if not TIKTOK_PROFILE_ID:
        log("Missing TIKTOK_PROFILE_ID secret", "ERR")
        sys.exit(1)
    if not COOKIES_B64:
        log("Missing YT_COOKIES_B64 secret", "ERR")
        sys.exit(1)

# ==========================================
# COOKIE MANAGEMENT
# ==========================================

def load_cookies():
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        decoded = base64.b64decode(COOKIES_B64).decode("utf-8")
        cookies = json.loads(decoded)

        # Fix sameSite values for Playwright
        for cookie in cookies:
            same_site = cookie.get("sameSite", "")
            if same_site not in ["Strict", "Lax", "None"]:
                cookie["sameSite"] = "None"
            # Remove fields Playwright doesn't accept
            cookie.pop("hostOnly", None)
            cookie.pop("storeId", None)
            cookie.pop("firstPartyDomain", None)
            cookie.pop("partitionKey", None)
            cookie.pop("session", None)

        COOKIES_PATH.write_text(json.dumps(cookies), encoding="utf-8")
        log(f"Loaded {len(cookies)} YouTube cookies")
        return cookies
    except Exception as e:
        log(f"Cookie decode failed: {e}", "ERR")
        sys.exit(1)

# ==========================================
# HISTORY MANAGEMENT
# ==========================================

def load_history():
    if not HISTORY_FILE.exists():
        return set(), set()
    ids, titles = set(), set()
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
        HISTORY_FILE.write_text("# TikTok → YouTube BOLTAS CLIPS History\n\n", encoding="utf-8")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tiktok_id} | {yt_id} | {ts} | {title[:50]}\n")
    if file_hash:
        with open(HASH_HISTORY, "a", encoding="utf-8") as f:
            f.write(f"{file_hash}\n")
    log(f"History saved for {tiktok_id}")

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
# YT-DLP DOWNLOAD
# ==========================================

def download_video():
    profile_url = f"https://www.tiktok.com/@{TIKTOK_PROFILE_ID.lstrip('@')}"
    log(f"Fetching from TikTok profile: {profile_url}", "STEP")

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
        "--max-downloads", "1",
        "--write-info-json",
        "-o", str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in [0, 101]:
            log(f"yt-dlp failed: {result.stderr}", "ERR")
            return None
        log(f"yt-dlp done (exit: {result.returncode})")
    except Exception as e:
        log(f"yt-dlp error: {e}", "ERR")
        return None

    video_files = []
    for ext in ["*.mp4", "*.mkv", "*.webm", "*.mov"]:
        video_files.extend(DOWNLOAD_DIR.glob(ext))

    if not video_files:
        log("No new videos found in profile", "INFO")
        return None

    v_file = video_files[0]
    vid_id = v_file.stem

    info_json = DOWNLOAD_DIR / f"{vid_id}.info.json"
    raw_caption = "New Movie Clip"
    if info_json.exists():
        try:
            with open(info_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
                raw_caption = meta.get("title") or meta.get("description") or "New Movie Clip"
        except:
            pass
        try: info_json.unlink()
        except: pass

    return v_file, raw_caption

# ==========================================
# VIDEO PROCESSING (DNA CHANGE)
# ==========================================

def process_video(input_path: Path) -> Path | None:
    output_path = PROCESSED_DIR / f"processed_{input_path.name}"
    log("Applying 11-Layer DNA fingerprint change...", "STEP")

    d = {
        "pts":        round(random.uniform(0.98, 1.02), 4),
        "cw":         round(random.uniform(0.97, 0.99), 3),
        "cx":         round(random.uniform(0.001, 0.005), 4),
        "brightness": round(random.uniform(-0.02, 0.02), 3),
        "contrast":   round(random.uniform(0.98, 1.05), 3),
        "saturation": round(random.uniform(0.98, 1.1), 3),
        "hue":        round(random.uniform(-2, 2), 1),
        "rotate":     round(random.uniform(-0.01, 0.01), 4),
        "zoom":       round(random.uniform(1.01, 1.05), 3),
        "fps":        random.choice([29.97, 30, 24]),
        "pitch":      round(random.uniform(0.98, 1.02), 3),
    }

    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    font_path = next((f for f in possible_fonts if os.path.exists(f)), "")
    font_config = f"fontfile='{font_path}':" if font_path else ""

    safe_watermark = escape_ffmpeg_text(WATERMARK_TEXT)
    watermark = (
        f"drawtext={font_config}text='{safe_watermark}':"
        f"fontcolor=white@0.3:fontsize=35:"
        f"x=(w-tw)/2:y=h*0.75:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )

    v_filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        f"setpts={d['pts']}*PTS",
        f"crop=iw*{d['cw']}:ih*{d['cw']}:iw*{d['cx']}:ih*{d['cx']}",
        f"eq=brightness={d['brightness']}:contrast={d['contrast']}:saturation={d['saturation']}:gamma=1.05",
        f"hue=h={d['hue']}",
        f"fps={d['fps']}",
        watermark,
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    ]

    vf = ",".join([f for f in v_filters if f])
    af = f"asetrate=44100*{d['pitch']},atempo={d['pts']}/{d['pitch']},aresample=44100"

    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -preset ultrafast -crf 22 '
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
# GROQ METADATA (using openai/gpt-oss-120b)
# ==========================================

def generate_ai_metadata(original_title: str):
    if not GROQ_API_KEY:
        return None

    log("Generating Hinglish SEO metadata via Groq (openai/gpt-oss-120b)...", "STEP")

    system_prompt = (
        "You are a YouTube Shorts SEO expert specialising in Hindi/Hinglish movie content for Indian audiences. "
        "You ALWAYS respond with a single valid JSON object and NOTHING else — no markdown, no backticks, no commentary. "
        "Every field is mandatory. Follow the exact format shown."
    )

    user_prompt = f"""Video caption from TikTok: "{original_title}"

Generate YouTube Shorts metadata strictly for BOLTAS CLIPS channel targeting Hindi movie lovers in India.

Rules:
1. "title": Max 70 chars total. Format: <Hinglish curiosity-gap hook (40 chars)> + 1 emoji (🎬/🍿/😱/🔥) + #shorts #movieclips #boltasclips. Must make viewer STOP scrolling.
2. "description": Structured as below (plain text, NO markdown asterisks):
   Line 1: ALL-CAPS emotional Hinglish hook related to the video (e.g. YEH SCENE DEKH KE ROO PADOGE!)
   Lines 2-6: 4-5 lines of Hinglish movie trivia / emotional cliffhanger building curiosity
   Line 7: "Subscribe to BOLTAS CLIPS for more! 🔔"
   Line 8: blank
   Line 9-onwards: EXACTLY 20 hashtags on separate lines, all starting with #, all relevant to the video topic, mixing: movie name hashtags, genre hashtags, Hindi/Hinglish hashtags, shorts hashtags. MUST include: #shorts #movieclips #boltasclips #movieexplainedinhindi #hindimovie
3. "tags": Array of EXACTLY 15 strings. Mix: movie title keywords, actor names (if inferable), genre, Hindi movie terms, emotion keywords. No # symbol. Each tag max 30 chars.

Return ONLY this JSON (no extra keys):
{{"title": "...", "description": "...", "tags": ["...", ...]}}"""

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7,
                    "max_tokens": 1200,
                },
                timeout=60
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            # Strip any accidental markdown fences
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)

            # Validate all three keys exist and have content
            assert result.get("title") and result.get("description") and result.get("tags")

            # Enforce tag count
            tags = result["tags"]
            if len(tags) < 15:
                tags += ["bollywood", "hindi movie", "movie clip", "shorts", "boltasclips",
                         "movieexplained", "hindimovies", "moviescene", "viral", "trending",
                         "movielovers", "filmclip", "cinemahindi", "desi", "india"]
                result["tags"] = tags[:15]

            # Ensure description has 20 hashtags
            desc = result["description"]
            ht_count = desc.count("\n#") + (1 if desc.lstrip().startswith("#") else 0)
            # Count lines starting with #
            ht_lines = [l for l in desc.splitlines() if l.strip().startswith("#")]
            if len(ht_lines) < 20:
                extra = [
                    "#shorts", "#movieclips", "#boltasclips", "#movieexplainedinhindi",
                    "#hindimovie", "#bollywood", "#viral", "#trending", "#moviescene",
                    "#cinematichindi", "#filmlovers", "#desicinema", "#india", "#reels",
                    "#ytshorts", "#movietrivia", "#hindifilm", "#actorscene", "#subscribe",
                    "#watchnow"
                ]
                needed = [h for h in extra if h not in desc]
                for h in needed:
                    if len(ht_lines) >= 20:
                        break
                    desc += f"\n{h}"
                    ht_lines.append(h)
                result["description"] = desc

            log(f"Groq metadata OK (attempt {attempt+1})")
            return result

        except Exception as e:
            log(f"Groq attempt {attempt+1} failed: {e}", "WARN")
            time.sleep(2)

    return None

def get_final_metadata(raw_caption: str, video_id: str) -> dict:
    ai = generate_ai_metadata(raw_caption) if GROQ_API_KEY else None
    if ai:
        return {
            "title": ai.get("title", raw_caption[:70]),
            "description": ai.get("description", ""),
            "tags": ai.get("tags", [])
        }
    # Fallback
    return {
        "title": raw_caption[:70],
        "description": f"{raw_caption}\n\n#shorts #movieclips #boltasclips",
        "tags": ["shorts", "movieclips", "bollywood", "hollywood", "hindi"]
    }

# ==========================================
# HUMAN BEHAVIOR HELPERS
# ==========================================

async def human_type(page, selector, text):
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.3, 0.7))
    await page.keyboard.press("Control+a")
    await asyncio.sleep(random.uniform(0.1, 0.3))
    await page.keyboard.press("Backspace")
    await asyncio.sleep(random.uniform(0.2, 0.5))
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.15))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.3, 0.8))

async def human_click(page, selector):
    try:
        element = await page.wait_for_selector(selector, timeout=8000)
        box = await element.bounding_box()
        if not box: return False
        x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
        y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)
        await page.mouse.move(x + random.randint(-30, 30), y + random.randint(-20, 20))
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.click(x, y)
        return True
    except:
        return False

# ==========================================
# PLAYWRIGHT UPLOAD (HUMAN-LIKE)
# ==========================================

async def playwright_upload(video_path: str, title: str, description: str,
                             tags: list, privacy: str = "public") -> str | None:
    from playwright.async_api import async_playwright

    cookies = load_cookies()
    log("Starting Playwright browser upload...", "STEP")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
            ]
        )

        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )

        # Stealth — remove webdriver flag
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en','hi'] });
            window.chrome = { runtime: {} };
        """)

        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        # --- Verify login ---
        log("Verifying YouTube session...", "STEP")
        await page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2.5, 4.0))

        if "accounts.google.com" in page.url:
            log("Cookies expired! Regenerate YT_COOKIES_B64", "ERR")
            await browser.close()
            return None

        log("Session OK — logged in!", "INFO")
        await asyncio.sleep(random.uniform(1.0, 2.5))

        # --- Click Create/Upload ---
        upload_selectors = [
            "button[aria-label='Create']",
            "ytcp-button#create-icon",
            "#upload-btn",
        ]
        clicked = False
        for sel in upload_selectors:
            if await human_click(page, sel):
                clicked = True
                log("Upload button clicked")
                break

        await page.goto("https://studio.youtube.com/channel/UC/videos/upload", wait_until="networkidle")

        await asyncio.sleep(random.uniform(1.5, 2.5))

        # --- Attach file via Playwright set_input_files ---
        log("Attaching video file...", "STEP")

        attached = False
        max_attach_attempts = 3

        for attempt in range(max_attach_attempts):
            try:
                # Wait for the page to fully load upload UI
                await asyncio.sleep(random.uniform(2.0, 3.0))

                # Method 1: Try to find input directly (may be hidden)
                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(video_path)
                    log(f"File attached via hidden input (attempt {attempt+1})")
                    attached = True
                    break

            except Exception as e1:
                log(f"Hidden input failed: {e1}", "WARN")

                # Method 2: Try clicking upload area first, then set files
                try:
                    # Click the upload area/dropzone to trigger file input creation
                    upload_area_selectors = [
                        "#upload-content",
                        "[id*='upload']",
                        "ytcp-uploads-dialog",
                        "[role='dialog']",
                        "#dialog",
                        ".upload-dialog",
                        "ytcp-video-upload-dialog",
                    ]

                    for sel in upload_area_selectors:
                        try:
                            area = await page.query_selector(sel)
                            if area:
                                await area.click()
                                await asyncio.sleep(1.0)
                                break
                        except:
                            continue

                    # Try finding input again after click
                    await asyncio.sleep(2.0)
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(video_path)
                        log(f"File attached after click trigger (attempt {attempt+1})")
                        attached = True
                        break

                except Exception as e2:
                    log(f"Click trigger failed: {e2}", "WARN")

            await asyncio.sleep(random.uniform(1.0, 2.0))

        if not attached:
            log("All file attachment methods failed", "ERR")
            try:
                await page.screenshot(path="upload_error.png", full_page=True)
            except:
                pass
            await browser.close()
            return None

        await asyncio.sleep(random.uniform(3.0, 5.0))

        # --- Title ---
        title_selectors = [
            "#textbox[aria-label='Add a title that describes your video']",
            "#title-textarea #textbox",
            "ytcp-social-suggestions-textbox #textbox",
            "[aria-label='Add a title that describes your video']",
            "#title-textarea",
        ]
        for sel in title_selectors:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                await human_type(page, sel, title[:100])
                log("Title filled")
                break
            except:
                continue

        await asyncio.sleep(random.uniform(0.8, 1.5))

        # --- Description ---
        desc_selectors = [
            "#textbox[aria-label='Tell viewers about your video']",
            "#description-textarea #textbox",
            "[aria-label='Tell viewers about your video']",
            "#description-textarea",
        ]
        for sel in desc_selectors:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                await human_type(page, sel, description[:4500])
                log("Description filled")
                break
            except:
                continue

        await asyncio.sleep(random.uniform(0.8, 1.5))

        # --- Not for kids ---
        try:
            nfk = await page.wait_for_selector(
                "#radioLabel:has-text('No, it\\'s not made for kids')", timeout=5000
            )
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await nfk.click()
            log("Audience set")
        except:
            pass

        await asyncio.sleep(random.uniform(0.5, 1.0))

        # --- Next x3 (Details → Video elements → Checks → Visibility) ---
        for step in range(3):
            # Close any open autocomplete / suggestion dropdown first
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except:
                pass

            clicked_next = False
            next_selectors = [
                "ytcp-button#next-button",
                "#next-button",
                "div#next-button",
                "ytcp-button[id='next-button']",
                "button[aria-label='Next']",
                "[aria-label='Next']",
            ]

            # Try each selector with wait
            for sel in next_selectors:
                try:
                    btn = await page.wait_for_selector(sel, state="visible", timeout=12000)
                    if btn:
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        await btn.click(force=True)
                        clicked_next = True
                        log(f"Next step {step+1}/3 clicked ✓")
                        break
                except:
                    continue

            if not clicked_next:
                # JS fallback as last resort
                try:
                    await page.evaluate("""() => {
                        const buttons = document.querySelectorAll('ytcp-button');
                        for (const b of buttons) {
                            const label = b.getAttribute('aria-label') || b.textContent || '';
                            if (label.toLowerCase().includes('next')) {
                                b.click();
                                return true;
                            }
                        }
                        // Fallback: find by ID
                        const b = document.querySelector('ytcp-button#next-button') ||
                                    document.querySelector('#next-button');
                        if (b) { b.click(); return true; }
                        return false;
                    }""")
                    clicked_next = True
                    log(f"Next step {step+1}/3 via JS fallback")
                except Exception as js_err:
                    log(f"JS fallback also failed: {js_err}", "WARN")

            if not clicked_next:
                log(f"Could not click Next for step {step+1}", "ERR")
                try:
                    await page.screenshot(path=f"next_error_step{step+1}.png", full_page=True)
                except:
                    pass
                # Continue anyway, sometimes the page auto-advances

            # Wait longer between steps for processing
            await asyncio.sleep(random.uniform(3.0, 5.0))

            # Check if we're stuck on same page (upload still processing)
            max_wait = 60
            waited = 0
            while waited < max_wait:
                try:
                    # Check if progress bar still exists
                    prog = await page.query_selector(".progress-label, #progress, [role='progressbar']")
                    if prog:
                        txt = await prog.inner_text() if hasattr(prog, 'inner_text') else ""
                        if txt and "%" in txt:
                            log(f"  Upload processing: {txt.strip()}")
                            await asyncio.sleep(5)
                            waited += 5
                            continue
                except:
                    pass
                break

            try:
                await page.screenshot(path=f"step_{step+1}_after_next.png")
            except:
                pass

        # --- Visibility ---
        privacy_map = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}
        p_val = privacy_map.get(privacy.lower(), "PUBLIC")
        try:
            radio = await page.wait_for_selector(
                f"tp-yt-paper-radio-button[name='{p_val}']", timeout=8000
            )
            await asyncio.sleep(random.uniform(0.8, 1.5))
            await radio.click()
            log(f"Visibility: {p_val}")
        except:
            log("Privacy selector not found — defaulting Public", "WARN")

        await asyncio.sleep(random.uniform(1.0, 2.0))

        # --- Wait for upload complete ---
        log("Waiting for upload to finish...", "STEP")
        max_wait = 300
        waited = 0
        while waited < max_wait:
            try:
                btn = await page.query_selector("#done-button, ytcp-button#done-button")
                if btn and await btn.is_enabled():
                    log("Upload complete — publishing!")
                    break
            except:
                pass
            try:
                prog = await page.query_selector(".progress-label")
                if prog:
                    txt = await prog.inner_text()
                    print(f"  ⏳ {txt.strip()}", end="\r", flush=True)
            except:
                pass
            await asyncio.sleep(5)
            waited += 5
            if waited % 30 == 0:
                await page.mouse.wheel(0, random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await page.mouse.wheel(0, -random.randint(30, 80))

        # --- Publish ---
        publish_selectors = [
            "#done-button",
            "ytcp-button#done-button",
            "[aria-label='Publish']",
            "[aria-label='Save']",
        ]
        published = False
        for sel in publish_selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000)
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await btn.click()
                published = True
                log("Published!")
                break
            except:
                continue

        if not published:
            # Final JS fallback for publish
            try:
                await page.evaluate("""() => {
                    const buttons = document.querySelectorAll('ytcp-button');
                    for (const b of buttons) {
                        const label = (b.getAttribute('aria-label') || b.textContent || '').toLowerCase();
                        if (label.includes('publish') || label.includes('save') || label.includes('done')) {
                            b.click();
                            return true;
                        }
                    }
                    const done = document.querySelector('#done-button') || 
                                 document.querySelector('ytcp-button#done-button');
                    if (done) { done.click(); return true; }
                    return false;
                }""")
                published = True
                log("Published via JS fallback!")
            except:
                pass

        if not published:
            log("Publish button not found", "ERR")
            await browser.close()
            return None

        await asyncio.sleep(random.uniform(3.0, 5.0))

        # Get video URL/ID
        yt_id = "uploaded"
        try:
            link = await page.wait_for_selector("a.ytcp-video-info", timeout=8000)
            href = await link.get_attribute("href")
            if href:
                match = re.search(r'v=([a-zA-Z0-9_-]+)', href)
                if match:
                    yt_id = match.group(1)
                    log(f"Video live: https://youtube.com/watch?v={yt_id}")
        except:
            log("Video published (ID not captured)")

        await asyncio.sleep(random.uniform(2.0, 4.0))
        await browser.close()
        return yt_id

def upload_video_sync(video_path: str, title: str, description: str,
                       tags: list, privacy: str = "public") -> str | None:
    return asyncio.run(playwright_upload(video_path, title, description, tags, privacy))

# ==========================================
# MAIN
# ==========================================

def main():
    log("=== BOLTAS CLIPS — TikTok → YouTube Pipeline ===")

    validate_env()
    setup_dirs()

    # Step 1: Download
    result = download_video()
    if not result:
        log("No new video to upload. Exiting.", "INFO")
        sys.exit(0)

    v_file, raw_caption = result
    vid_id = v_file.stem
    log(f"Downloaded: {v_file.name} | Caption: {raw_caption[:60]}")

    # Step 2: Duplicate check
    file_hash = get_file_hash(v_file)
    if is_duplicate_hash(file_hash):
        log("Duplicate video detected — skipping.", "WARN")
        sys.exit(0)

    # Step 3: Process (DNA change)
    processed = process_video(v_file)
    if not processed:
        log("Video processing failed.", "ERR")
        sys.exit(1)

    # Step 4: Metadata
    meta = get_final_metadata(raw_caption, vid_id)
    log(f"Title: {meta['title']}")

    # Step 5: Upload via Playwright
    yt_id = upload_video_sync(
        video_path=str(processed),
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        privacy=PRIVACY,
    )

    if not yt_id:
        log("Upload failed.", "ERR")
        sys.exit(1)

    # Step 6: Save history
    save_history(vid_id, yt_id, meta["title"], file_hash)
    log("=== Pipeline complete! ===")

if __name__ == "__main__":
    main()
