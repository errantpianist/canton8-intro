import urllib.request
import urllib.parse
import json

import os

base_url = "https://auth.dev.digik.cantor8.tech"

def get_token():
    # Read client secret from local file (ignored by git)
    secret_path = os.path.join(os.path.dirname(__file__), "client_secret.txt")
    with open(secret_path, "r") as f:
        secret = f.read().strip()

    data = {
        'grant_type': 'client_credentials',
        'client_id': 'hackathon',
        'client_secret': secret,
    }
    url = f"{base_url}/realms/master/protocol/openid-connect/token"
    encoded_data = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req) as response:
            body = json.loads(response.read().decode('utf-8'))
            return body.get("access_token")
    except Exception as e:
        print(f"Error fetching token: {e}")
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'))
        return None

if __name__ == "__main__":
    token = get_token()
    if token:
        print("Successfully obtained token!")
        print(f"Token (first 30 chars): {token[:30]}...")
    else:
        print("Failed to obtain token.")
