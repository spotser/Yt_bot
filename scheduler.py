import time
import schedule
import subprocess
from datetime import datetime

def run_youtube_bot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Running YouTube Automation...")
    try:
        # Run the tiktok_to_youtube.py script
        # Ensure the environment variables in tiktok_to_youtube.py or a .env file are set when running this!
        result = subprocess.run(
            ["python", "tiktok_to_youtube.py"],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Failed to run script: {e}")

# Target Indian times: 7:15 AM, 1:15 PM, 6:15 PM, 9:15 PM IST
# NOTE: The times below are in your local machine's timezone.
# If you run this on a VPS (usually UTC), adjust these times to UTC!
# (UTC times: 01:45, 07:45, 12:45, 15:45)
# Assuming the machine running this is in IST:
schedule.every().day.at("07:15").do(run_youtube_bot)
schedule.every().day.at("13:15").do(run_youtube_bot)
schedule.every().day.at("18:15").do(run_youtube_bot)
schedule.every().day.at("21:15").do(run_youtube_bot)

print("✅ Guaranteed YouTube Scheduler is active!")
print("Waiting for the next scheduled post time (IST)...")

while True:
    schedule.run_pending()
    time.sleep(60)
