import subprocess
import urllib.request
import json
import os
from test_auth import get_token

validator_url = "https://api.validator.dev.digik.cantor8.tech/api/validator"

def generate_key():
    if not os.path.exists("party_key.pem"):
        subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", "party_key.pem"], check=True)
    
    # Get public key in DER
    subprocess.run(["openssl", "pkey", "-in", "party_key.pem", "-pubout", "-outform", "DER", "-out", "pub.der"], check=True)
    with open("pub.der", "rb") as f:
        der_bytes = f.read()
    os.remove("pub.der")
    
    # Raw public key is the last 32 bytes of the DER SubjectPublicKeyInfo
    raw_pub_hex = der_bytes[-32:].hex()
    return raw_pub_hex

def sign_data(hex_data):
    data_bytes = bytes.fromhex(hex_data)
    with open("temp_msg.bin", "wb") as f:
        f.write(data_bytes)
    subprocess.run([
        "openssl", "pkeyutl", "-sign",
        "-inkey", "party_key.pem",
        "-rawin", "-in", "temp_msg.bin",
        "-out", "temp_sig.bin"
    ], check=True)
    with open("temp_sig.bin", "rb") as f:
        sig_bytes = f.read()
    os.remove("temp_msg.bin")
    os.remove("temp_sig.bin")
    return sig_bytes.hex()

def call_generate(raw_pub_hex, party_hint):
    token = get_token()
    url = f"{validator_url}/v0/admin/external-party/topology/generate"
    data = {
        "party_hint": party_hint,
        "public_key": raw_pub_hex
    }
    req = urllib.request.Request(url, method='POST', data=json.dumps(data).encode('utf-8'))
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def call_submit(raw_pub_hex, signed_txs):
    token = get_token()
    url = f"{validator_url}/v0/admin/external-party/topology/submit"
    data = {
        "public_key": raw_pub_hex,
        "signed_topology_txs": signed_txs
    }
    req = urllib.request.Request(url, method='POST', data=json.dumps(data).encode('utf-8'))
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as response:
            return True, json.loads(response.read().decode('utf-8'))
    except Exception as e:
        body = ""
        if hasattr(e, 'read'):
            try:
                body = e.read().decode('utf-8')
            except:
                pass
        return False, f"{e} - {body}"

def main():
    party_hint = "cantor8_intro_party"
    print("Step 1: Generating Ed25519 key...")
    raw_pub_hex = generate_key()
    print(f"Raw public key hex: {raw_pub_hex}")
    
    print("\nStep 2: Generating topology transactions...")
    gen_resp = call_generate(raw_pub_hex, party_hint)
    print("Generate response:", json.dumps(gen_resp, indent=2))
    party_id = gen_resp["party_id"]
    txs = gen_resp["topology_txs"]
    print(f"Allocating Party ID: {party_id}")
    print(f"Generated {len(txs)} topology transactions.")
    
    # Strategy 1: Sign the full multihash (e.g. 34 bytes starting with 1220)
    print("\nStrategy 1: Signing the full multihash (34 bytes)...")
    signed_txs_multihash = []
    for tx in txs:
        # tx has "topology_tx" (base64) and "hash" (hex string e.g. "1220...")
        multihash = tx["hash"]
        signature = sign_data(multihash)
        signed_txs_multihash.append({
            "topology_tx": tx["topology_tx"],
            "signed_hash": signature
        })
    
    success, resp = call_submit(raw_pub_hex, signed_txs_multihash)
    if success:
        print("SUCCESS using Strategy 1!")
        print("Response:", resp)
        print(f"\nFinal Registered Party ID: {party_id}")
        return
    else:
        print(f"Strategy 1 failed: {resp}")
        
    # Strategy 2: Sign the raw SHA-256 hash (32 bytes, strip first 4 hex chars "1220")
    print("\nStrategy 2: Signing the raw SHA-256 hash (32 bytes)...")
    signed_txs_raw = []
    for tx in txs:
        multihash = tx["hash"]
        raw_hash = multihash[4:] # strip "1220"
        signature = sign_data(raw_hash)
        signed_txs_raw.append({
            "topology_tx": tx["topology_tx"],
            "signed_hash": signature
        })
        
    success, resp = call_submit(raw_pub_hex, signed_txs_raw)
    if success:
        print("SUCCESS using Strategy 2!")
        print("Response:", resp)
        print(f"\nFinal Registered Party ID: {party_id}")
    else:
        print(f"Strategy 2 failed: {resp}")

if __name__ == "__main__":
    main()
