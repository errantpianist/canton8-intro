import urllib.request
import json
import uuid
import subprocess
import os
import base64
from test_auth import get_token

ledger_url = "https://api.validator.dev.digik.cantor8.tech/api/ledger"

# Coordinates:
receiver_party = "ezoh::1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"
provider_party = "cantor8-digik-1::12204e94c0e449c0efcd270dd1e68259c36471cebef132e5c7dfc2750fe8c9eed77f"
pkg_id = "d9a91419b27aa27002a883334015a892c35075967b07008a446bc4b5073051ec"
key_fingerprint = "1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"
key_file = "party_key_ezoh.pem"

def sign_hash_bytes(hash_b64):
    hash_bytes = base64.b64decode(hash_b64)
    with open("temp_hash_ezoh.bin", "wb") as f:
        f.write(hash_bytes)
    subprocess.run([
        "openssl", "pkeyutl", "-sign",
        "-inkey", key_file,
        "-rawin", "-in", "temp_hash_ezoh.bin",
        "-out", "temp_sig_ezoh.bin"
    ], check=True)
    with open("temp_sig_ezoh.bin", "rb") as f:
        sig_bytes = f.read()
    os.remove("temp_hash_ezoh.bin")
    os.remove("temp_sig_ezoh.bin")
    return sig_bytes

def prepare_submission():
    token = get_token()
    url = f"{ledger_url}/v2/interactive-submission/prepare"
    command_id = f"preapproval-{uuid.uuid4()}"
    template_id = f"{pkg_id}:Splice.Wallet.TransferPreapproval:TransferPreapprovalProposal"
    
    data = {
        "commandId": command_id,
        "actAs": [receiver_party],
        "synchronizerId": "global-domain::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a",
        "packageIdSelectionPreference": [pkg_id],
        "commands": [
            {
                "CreateCommand": {
                    "templateId": template_id,
                    "createArguments": {
                        "receiver": receiver_party,
                        "provider": provider_party
                    }
                }
            }
        ]
    }
    
    encoded_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, method='POST', data=encoded_data)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        if hasattr(e, 'read'):
            print("Prepare error body:", e.read().decode('utf-8'))
        raise e

def execute_submission(prepared_tx, hashing_scheme, sig_encoded):
    token = get_token()
    url = f"{ledger_url}/v2/interactive-submission/executeAndWait"
    submission_id = str(uuid.uuid4())
    
    data = {
        "preparedTransaction": prepared_tx,
        "hashingSchemeVersion": hashing_scheme,
        "submissionId": submission_id,
        "deduplicationPeriod": {"Empty": {}},
        "partySignatures": {
            "signatures": [
                {
                    "party": receiver_party,
                    "signatures": [
                        {
                            "format": "SIGNATURE_FORMAT_CONCAT",
                            "signature": sig_encoded,
                            "signedBy": key_fingerprint,
                            "signingAlgorithmSpec": "SIGNING_ALGORITHM_SPEC_ED25519"
                        }
                    ]
                }
            ]
        }
    }
    
    encoded_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, method='POST', data=encoded_data)
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
    print("Step 1: Preparing transaction on Ledger API...")
    prep_resp = prepare_submission()
    prepared_tx = prep_resp["preparedTransaction"]
    prep_hash = prep_resp["preparedTransactionHash"]
    hashing_scheme = prep_resp["hashingSchemeVersion"]
    print("Prepared Transaction Hash:", prep_hash)
    
    print("\nStep 2: Signing the transaction hash using private key...")
    sig_bytes = sign_hash_bytes(prep_hash)
    sig_base64 = base64.b64encode(sig_bytes).decode('utf-8')
    
    print("\nStep 3: Executing submission...")
    success, resp = execute_submission(prepared_tx, hashing_scheme, sig_base64)
    if success:
        print("PREAPPROVAL SUBMIT SUCCESS FOR EZOH!")
        print(json.dumps(resp, indent=2))
    else:
        print("Preapproval submission failed:", resp)

if __name__ == "__main__":
    main()
