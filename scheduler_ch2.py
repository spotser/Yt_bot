import time
import schedule
import subprocess
from datetime import datetime

def run_youtube_bot_ch2():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🎬 Running BOLTAS CLIPS YouTube Automation...")
    try:
        # Run the tiktok_to_youtube_ch2.py script
        result = subprocess.run(
            ["python", "tiktok_to_youtube_ch2.py"],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Failed to run script: {e}")

# Target Indian times: 2:00 PM and 9:00 PM IST
# NOTE: The times below are in your local machine's timezone.
# If you run this on a VPS (usually UTC), adjust these times to UTC!
# (UTC times: 08:30 and 15:30)
# Assuming the machine running this is in IST:
schedule.every().day.at("14:00").do(run_youtube_bot_ch2)
schedule.every().day.at("21:00").do(run_youtube_bot_ch2)

print("🎬 Guaranteed BOLTAS CLIPS Scheduler is active!")
print("Waiting for the next scheduled post time (IST)...")

while True:
    schedule.run_pending()
    time.sleep(60)
