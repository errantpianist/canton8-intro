import subprocess
import urllib.request
import json
import os
from test_auth import get_token

validator_url = "https://api.validator.dev.digik.cantor8.tech/api/validator"
key_file = "party_key_ezoh.pem"

def generate_key():
    if os.path.exists(key_file):
        os.remove(key_file)
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", key_file], check=True)
    
    # Get public key in DER
    subprocess.run(["openssl", "pkey", "-in", key_file, "-pubout", "-outform", "DER", "-out", "pub_ezoh.der"], check=True)
    with open("pub_ezoh.der", "rb") as f:
        der_bytes = f.read()
    os.remove("pub_ezoh.der")
    
    # Raw public key is the last 32 bytes of the DER SubjectPublicKeyInfo
    raw_pub_hex = der_bytes[-32:].hex()
    return raw_pub_hex

def sign_data(hex_data):
    data_bytes = bytes.fromhex(hex_data)
    with open("temp_msg_ezoh.bin", "wb") as f:
        f.write(data_bytes)
    subprocess.run([
        "openssl", "pkeyutl", "-sign",
        "-inkey", key_file,
        "-rawin", "-in", "temp_msg_ezoh.bin",
        "-out", "temp_sig_ezoh.bin"
    ], check=True)
    with open("temp_sig_ezoh.bin", "rb") as f:
        sig_bytes = f.read()
    os.remove("temp_msg_ezoh.bin")
    os.remove("temp_sig_ezoh.bin")
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
    party_hint = "ezoh"
    print("Step 1: Generating Ed25519 key...")
    raw_pub_hex = generate_key()
    print(f"Raw public key hex: {raw_pub_hex}")
    
    print("\nStep 2: Generating topology transactions...")
    gen_resp = call_generate(raw_pub_hex, party_hint)
    party_id = gen_resp["party_id"]
    txs = gen_resp["topology_txs"]
    print(f"Allocating Party ID: {party_id}")
    
    print("\nStep 3: Signing the topology transactions...")
    signed_txs = []
    for tx in txs:
        multihash = tx["hash"]
        signature = sign_data(multihash)
        signed_txs.append({
            "topology_tx": tx["topology_tx"],
            "signed_hash": signature
        })
    
    print("\nStep 4: Submitting to validator...")
    success, resp = call_submit(raw_pub_hex, signed_txs)
    if success:
        print("ONBOARD SUCCESS!")
        print("New Party ID:", resp["party_id"])
    else:
        print("ONBOARD FAILED:", resp)

if __name__ == "__main__":
    main()
