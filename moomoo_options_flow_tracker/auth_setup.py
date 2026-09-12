import base64
import hashlib
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
import requests

BASE = "https://webapi.moomoo.com"
REDIRECT_URI = "http://localhost:60355/callback"
TOKEN_FILE = Path("tokens.json")
CLIENT_FILE = Path("oauth_client.json")

def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def register_client():
    payload = {
        "redirect_uris": [REDIRECT_URI],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": "Options Flow Tracker",
    }
    r = requests.post(f"{BASE}/oauth2/register", json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    CLIENT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data["client_id"]

def get_client_id():
    if CLIENT_FILE.exists():
        data = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
        if data.get("client_id"):
            return data["client_id"]
    return register_client()

def main():
    client_id = get_client_id()
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(24)

    auth_url = f"{BASE}/oauth2/authorize/confirm?" + urlencode({
        "client_id": client_id,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
    })

    result = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404); self.end_headers(); return
            qs = parse_qs(parsed.query)
            if qs.get("state", [""])[0] != state:
                self.send_response(400); self.end_headers()
                self.wfile.write(b"Invalid OAuth state.")
                done.set()
                return
            result["code"] = qs.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Moomoo authorization received.</h2>"
                b"<p>You may close this browser tab.</p>"
            )
            done.set()
        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 60355), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("Opening Moomoo authorization page...")
    webbrowser.open(auth_url)
    done.wait(timeout=300)
    server.shutdown()

    code = result.get("code")
    if not code:
        raise RuntimeError("No authorization code received.")

    r = requests.post(
        f"{BASE}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    r.raise_for_status()
    token = r.json()
    token["client_id"] = client_id
    TOKEN_FILE.write_text(json.dumps(token, indent=2), encoding="utf-8")
    print("Authorization saved.")

if __name__ == "__main__":
    main()
