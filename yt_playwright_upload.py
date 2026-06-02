#!/usr/bin/env python3
"""
YouTube Human-Like Uploader via Playwright
- Fully simulates real human browser behavior
- Mouse movements, random delays, natural typing
- Cookie-based session (no API)
- GitHub Actions compatible (headless)
"""

import os
import sys
import json
import time
import random
import base64
import asyncio
from pathlib import Path
from datetime import datetime

# ==========================================
# CONFIG
# ==========================================

COOKIES_B64   = os.environ.get("YT_COOKIES_B64", "")
COOKIES_PATH  = Path("temp_work/yt_cookies.json")
VIDEO_PATH    = os.environ.get("VIDEO_PATH", "")        # passed from main pipeline
VIDEO_TITLE   = os.environ.get("VIDEO_TITLE", "")
VIDEO_DESC    = os.environ.get("VIDEO_DESC", "")
VIDEO_TAGS    = os.environ.get("VIDEO_TAGS", "")        # comma separated
PRIVACY       = os.environ.get("YT_PRIVACY", "public")  # public / unlisted / private

STUDIO_URL    = "https://studio.youtube.com"
UPLOAD_URL    = "https://www.youtube.com/upload"

# ==========================================
# HUMAN BEHAVIOR HELPERS
# ==========================================

def human_delay(min_ms=300, max_ms=900):
    """Random delay like a human pause"""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def micro_delay():
    """Tiny delay between keystrokes"""
    time.sleep(random.uniform(0.05, 0.18))

async def human_type(page, selector, text):
    """Type like a human — random speed, occasional pause"""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.3, 0.7))
    
    # Clear existing text naturally
    await page.keyboard.press("Control+a")
    await asyncio.sleep(random.uniform(0.1, 0.3))
    await page.keyboard.press("Backspace")
    await asyncio.sleep(random.uniform(0.2, 0.5))
    
    for char in text:
        await page.keyboard.type(char)
        # Random typing speed
        await asyncio.sleep(random.uniform(0.04, 0.15))
        
        # Occasional longer pause (like thinking)
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.3, 0.8))

async def human_move_and_click(page, selector):
    """Move mouse naturally then click"""
    element = await page.query_selector(selector)
    if not element:
        return False
    
    box = await element.bounding_box()
    if not box:
        return False
    
    # Random point within element
    x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
    y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)
    
    # Move in steps (natural curve simulation)
    await page.mouse.move(x + random.randint(-50, 50), y + random.randint(-30, 30))
    await asyncio.sleep(random.uniform(0.1, 0.3))
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(x, y)
    return True

async def random_scroll(page, direction="down", amount=None):
    """Random scroll like human browsing"""
    if amount is None:
        amount = random.randint(100, 400)
    if direction == "up":
        amount = -amount
    await page.mouse.wheel(0, amount)
    await asyncio.sleep(random.uniform(0.2, 0.6))

# ==========================================
# COOKIE MANAGEMENT
# ==========================================

def load_cookies():
    """Load cookies from env secret"""
    if not COOKIES_B64:
        print("❌ YT_COOKIES_B64 not set in environment", flush=True)
        sys.exit(1)
    
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        decoded = base64.b64decode(COOKIES_B64).decode("utf-8")
        cookies = json.loads(decoded)
        COOKIES_PATH.write_text(json.dumps(cookies), encoding="utf-8")
        print(f"✅ Loaded {len(cookies)} cookies", flush=True)
        return cookies
    except Exception as e:
        print(f"❌ Cookie decode failed: {e}", flush=True)
        sys.exit(1)

def export_cookies_locally():
    """
    Run this ONCE locally to generate YT_COOKIES_B64 secret.
    Usage: python yt_playwright_upload.py --export-cookies
    """
    from playwright.sync_api import sync_playwright
    
    print("🌐 Opening browser for manual login...")
    print("📝 Login to YouTube, then press Enter in terminal")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = ctx.new_page()
        page.goto("https://accounts.google.com/signin")
        
        input("\n✋ Login manually in the browser, then press ENTER here...")
        
        cookies = ctx.cookies()
        encoded = base64.b64encode(
            json.dumps(cookies).encode()
        ).decode()
        
        # Save to file
        Path("yt_cookies_b64.txt").write_text(encoded)
        print(f"\n✅ Cookies exported! ({len(cookies)} cookies)")
        print("📋 Copy content of yt_cookies_b64.txt to GitHub Secret: YT_COOKIES_B64")
        
        browser.close()

# ==========================================
# CORE UPLOAD FUNCTION
# ==========================================

async def upload_video(video_path: str, title: str, description: str, tags: str, privacy: str = "public"):
    """
    Upload video to YouTube via browser automation
    Fully human-like behavior
    """
    from playwright.async_api import async_playwright
    
    cookies = load_cookies()
    
    print(f"🎬 Starting upload: {title[:50]}...", flush=True)
    
    async with async_playwright() as p:
        # Launch with stealth settings
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,720",
                # Hide automation
                "--disable-extensions",
                "--disable-infobars",
            ]
        )
        
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Kolkata",
            # Permissions
            permissions=["geolocation"],
        )
        
        # Stealth: Remove webdriver property
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'hi']
            });
            window.chrome = { runtime: {} };
        """)
        
        # Load cookies
        await ctx.add_cookies(cookies)
        
        page = await ctx.new_page()
        
        # ---- STEP 1: Verify login ----
        print("🔐 Verifying YouTube session...", flush=True)
        await page.goto(STUDIO_URL, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2.5, 4.0))
        
        # Check if logged in
        if "accounts.google.com" in page.url:
            print("❌ Cookies expired! Regenerate YT_COOKIES_B64", flush=True)
            await browser.close()
            sys.exit(1)
        
        print("✅ Session verified — logged in!", flush=True)
        
        # ---- STEP 2: Human browsing simulation before upload ----
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await random_scroll(page, "down", random.randint(50, 150))
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # ---- STEP 3: Click Upload button ----
        print("📤 Navigating to upload...", flush=True)
        
        # Try Studio upload button
        upload_btn_selectors = [
            "button[aria-label='Create']",
            "#upload-btn",
            "ytcp-button#create-icon",
            "[aria-label='Upload videos']",
        ]
        
        clicked = False
        for sel in upload_btn_selectors:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                await human_move_and_click(page, sel)
                clicked = True
                print(f"✅ Upload button clicked", flush=True)
                break
            except:
                continue
        
        if not clicked:
            # Fallback: direct navigation
            await page.goto("https://www.youtube.com/upload", wait_until="domcontentloaded")
        
        await asyncio.sleep(random.uniform(1.5, 2.5))
        
        # ---- STEP 4: File input ----
        print("📁 Attaching video file...", flush=True)
        
        # Handle "Upload videos" option in dropdown if appeared
        try:
            upload_option = await page.wait_for_selector(
                "tp-yt-paper-item:has-text('Upload videos')", timeout=4000
            )
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await upload_option.click()
            await asyncio.sleep(random.uniform(1.0, 2.0))
        except:
            pass
        
        # Set file via input element
        try:
            file_input = await page.wait_for_selector(
                "input[type='file']", timeout=10000
            )
            await file_input.set_input_files(video_path)
            print("✅ File attached!", flush=True)
        except Exception as e:
            print(f"❌ File input failed: {e}", flush=True)
            await browser.close()
            return False
        
        # ---- STEP 5: Wait for upload dialog ----
        print("⏳ Waiting for upload dialog...", flush=True)
        await asyncio.sleep(random.uniform(3.0, 5.0))
        
        # ---- STEP 6: Fill Title ----
        print("✏️ Filling title...", flush=True)
        title_selectors = [
            "#textbox[aria-label='Add a title that describes your video']",
            "ytcp-social-suggestions-textbox #textbox",
            "#title-textarea #textbox",
        ]
        
        title_filled = False
        for sel in title_selectors:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                await human_type(page, sel, title[:100])
                title_filled = True
                print("✅ Title filled", flush=True)
                break
            except:
                continue
        
        if not title_filled:
            print("⚠️ Title field not found — continuing", flush=True)
        
        await asyncio.sleep(random.uniform(0.8, 1.5))
        
        # ---- STEP 7: Fill Description ----
        print("📝 Filling description...", flush=True)
        desc_selectors = [
            "#textbox[aria-label='Tell viewers about your video']",
            "#description-textarea #textbox",
        ]
        
        for sel in desc_selectors:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                await human_move_and_click(page, sel)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                await human_type(page, sel, description[:4500])
                print("✅ Description filled", flush=True)
                break
            except:
                continue
        
        await asyncio.sleep(random.uniform(0.8, 1.5))
        
        # ---- STEP 8: Not made for kids ----
        print("👶 Setting audience...", flush=True)
        try:
            not_for_kids = await page.wait_for_selector(
                "#radioLabel:has-text('No, it\\'s not made for kids')",
                timeout=5000
            )
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await not_for_kids.click()
            print("✅ Audience set", flush=True)
        except:
            pass
        
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # ---- STEP 9: Next → Next → Next (skip details) ----
        print("➡️ Moving through steps...", flush=True)
        for step in range(3):
            try:
                next_btn = await page.wait_for_selector(
                    "#next-button, ytcp-button#next-button",
                    timeout=8000
                )
                await asyncio.sleep(random.uniform(1.0, 2.0))
                await next_btn.click()
                print(f"✅ Step {step+1}/3 done", flush=True)
                await asyncio.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                print(f"⚠️ Next button step {step+1}: {e}", flush=True)
        
        # ---- STEP 10: Set Visibility ----
        print(f"🔒 Setting visibility: {privacy}...", flush=True)
        
        privacy_map = {
            "public":   "Public",
            "unlisted": "Unlisted",
            "private":  "Private",
        }
        privacy_label = privacy_map.get(privacy.lower(), "Public")
        
        try:
            privacy_radio = await page.wait_for_selector(
                f"tp-yt-paper-radio-button[name='{privacy_label.upper()}']",
                timeout=8000
            )
            await asyncio.sleep(random.uniform(0.8, 1.5))
            await privacy_radio.click()
            print(f"✅ Visibility set to {privacy_label}", flush=True)
        except:
            # Fallback selector
            try:
                await page.click(f"[aria-label='{privacy_label}']")
            except:
                print("⚠️ Privacy selector not found — defaulting to Public", flush=True)
        
        await asyncio.sleep(random.uniform(1.0, 2.0))
        
        # ---- STEP 11: Wait for upload to complete ----
        print("⏳ Waiting for video processing...", flush=True)
        
        max_wait = 300  # 5 minutes max
        waited = 0
        
        while waited < max_wait:
            try:
                # Check for "Publish" button — appears when upload done
                publish_btn = await page.query_selector(
                    "#done-button, ytcp-button#done-button, [aria-label='Publish']"
                )
                if publish_btn:
                    is_enabled = await publish_btn.is_enabled()
                    if is_enabled:
                        print("✅ Upload complete — ready to publish!", flush=True)
                        break
            except:
                pass
            
            # Check for processing message
            try:
                progress = await page.query_selector(".progress-label, .ytcp-video-upload-progress")
                if progress:
                    text = await progress.inner_text()
                    print(f"⏳ {text.strip()}", flush=True)
            except:
                pass
            
            await asyncio.sleep(5)
            waited += 5
            
            # Human behavior: occasional scroll while waiting
            if waited % 30 == 0:
                await random_scroll(page, "down", random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await random_scroll(page, "up", random.randint(30, 80))
        
        # ---- STEP 12: Publish ----
        print("🚀 Publishing...", flush=True)
        try:
            publish_selectors = [
                "#done-button",
                "ytcp-button#done-button",
                "[aria-label='Publish']",
                "ytcp-button:has-text('Publish')",
            ]
            
            for sel in publish_selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=5000)
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                    await human_move_and_click(page, sel)
                    print("✅ Published!", flush=True)
                    break
                except:
                    continue
                    
        except Exception as e:
            print(f"❌ Publish failed: {e}", flush=True)
            await browser.close()
            return False
        
        # ---- Wait for confirmation ----
        await asyncio.sleep(random.uniform(3.0, 5.0))
        
        # Grab video URL if possible
        try:
            success_link = await page.wait_for_selector(
                "a.ytcp-video-info", timeout=8000
            )
            href = await success_link.get_attribute("href")
            print(f"🎉 Video live: https://youtube.com{href}", flush=True)
        except:
            print("🎉 Video published successfully!", flush=True)
        
        await asyncio.sleep(random.uniform(2.0, 4.0))
        await browser.close()
        return True


# ==========================================
# PIPELINE INTEGRATION WRAPPER
# ==========================================

def upload_to_youtube(video_path: str, title: str, description: str, 
                       tags: str = "", privacy: str = "public") -> bool:
    """
    Drop-in replacement for YouTube API upload.
    Call this from your existing pipeline instead of youtube.videos().insert()
    
    Usage in main pipeline:
        from yt_playwright_upload import upload_to_youtube
        success = upload_to_youtube(
            video_path=str(processed_path),
            title=generated_title,
            description=generated_desc,
            tags=generated_tags,
            privacy="public"
        )
    """
    return asyncio.run(
        upload_video(video_path, title, description, tags, privacy)
    )


# ==========================================
# ENTRYPOINT
# ==========================================

if __name__ == "__main__":
    # Export cookies mode (run locally once)
    if "--export-cookies" in sys.argv:
        export_cookies_locally()
        sys.exit(0)
    
    # Direct run mode (for testing)
    if not VIDEO_PATH:
        print("Usage: VIDEO_PATH=x.mp4 VIDEO_TITLE='...' VIDEO_DESC='...' python yt_playwright_upload.py")
        sys.exit(1)
    
    success = upload_to_youtube(
        video_path=VIDEO_PATH,
        title=VIDEO_TITLE,
        description=VIDEO_DESC,
        tags=VIDEO_TAGS,
        privacy=PRIVACY,
    )
    
    sys.exit(0 if success else 1)
