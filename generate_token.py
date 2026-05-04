#!/usr/bin/env python3
"""
Token Generator — Sirf ek baar local machine pe chalao
-------------------------------------------------------
USAGE:
  pip install google-auth google-auth-oauthlib
  python generate_token.py
"""

import pickle
import base64
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

print("🔄 Browser mein Google account select karo aur allow karo...\n")

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token.pickle", "wb") as f:
    pickle.dump(creds, f)

with open("token.pickle", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

with open("token_b64.txt", "w") as f:
    f.write(b64)

print("\n✅ Token generate ho gaya!")
print("📄 'token_b64.txt' ka content GitHub Secret TOKEN_PICKLE_B64 mein daalo.")
