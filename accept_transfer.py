import urllib.request
import json
import uuid
import base64
import subprocess
import os
from test_auth import get_token

validator_url = "https://api.validator.dev.digik.cantor8.tech/api/validator"
ledger_url = "https://api.validator.dev.digik.cantor8.tech/api/ledger"
ezoh_party = "ezoh::1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"
key_file = "party_key_ezoh.pem"
key_fingerprint = "1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"

# Package ID for TransferInstruction interface:
transfer_pkg_id = "55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281"
interface_id = f"{transfer_pkg_id}:Splice.Api.Token.TransferInstructionV1:TransferInstruction"

def get_ledger_end():
    token = get_token()
    url = f"{ledger_url}/v2/state/ledger-end"
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode('utf-8'))
        return body["offset"]

def find_transfer_instruction(offset):
    token = get_token()
    url = f"{ledger_url}/v2/state/active-contracts"
    
    data = {
        "activeAtOffset": offset,
        "filter": {
            "filtersByParty": {
                ezoh_party: {
                    "cumulative": [
                        {
                            "identifierFilter": {
                                "WildcardFilter": {
                                    "value": {}
                                }
                            }
                        }
                    ]
                }
            }
        }
    }
    
    encoded_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, method='POST', data=encoded_data)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode('utf-8'))
        for entry in body:
            contract = entry.get("contractEntry", {}).get("JsActiveContract", {}).get("createdEvent", {})
            template_id = contract.get("templateId", "")
            if "AmuletTransferInstruction" in template_id:
                return contract["contractId"]
    return None

def get_choice_contexts(contract_id):
    token = get_token()
    url = f"{validator_url}/v0/scan-proxy/registry/transfer-instruction/v1/{contract_id}/choice-contexts/accept"
    
    req = urllib.request.Request(url, method='POST', data=b'{}')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def sign_hash_bytes(hash_b64):
    hash_bytes = base64.b64decode(hash_b64)
    with open("temp_accept_hash.bin", "wb") as f:
        f.write(hash_bytes)
    subprocess.run([
        "openssl", "pkeyutl", "-sign",
        "-inkey", key_file,
        "-rawin", "-in", "temp_accept_hash.bin",
        "-out", "temp_accept_sig.bin"
    ], check=True)
    with open("temp_accept_sig.bin", "rb") as f:
        sig_bytes = f.read()
    os.remove("temp_accept_hash.bin")
    os.remove("temp_accept_sig.bin")
    return sig_bytes

def prepare_exercise(contract_id, context_resp):
    token = get_token()
    url = f"{ledger_url}/v2/interactive-submission/prepare"
    command_id = f"accept-transfer-{uuid.uuid4()}"
    
    data = {
        "commandId": command_id,
        "actAs": [ezoh_party],
        "synchronizerId": "global-domain::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a",
        "packageIdSelectionPreference": [transfer_pkg_id],
        "disclosedContracts": context_resp["disclosedContracts"],
        "commands": [
            {
                "ExerciseCommand": {
                    "templateId": interface_id,
                    "contractId": contract_id,
                    "choice": "TransferInstruction_Accept",
                    "choiceArgument": {
                        "extraArgs": {
                            "meta": {
                                "values": {}
                            },
                            "context": context_resp["choiceContextData"]
                        }
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
            print("Prepare error details:", e.read().decode('utf-8'))
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
                    "party": ezoh_party,
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
    print("Finding transfer instruction for ezoh...")
    offset = get_ledger_end()
    cid = find_transfer_instruction(offset)
    if not cid:
        print("No pending transfer instructions found.")
        return
        
    print("Found Transfer Instruction Contract ID:", cid)
    
    print("\nStep 1: Requesting Choice Context from Scan Proxy...")
    context_resp = get_choice_contexts(cid)
    
    print("\nStep 2: Preparing Exercise command on Ledger API...")
    prep_resp = prepare_exercise(cid, context_resp)
    prepared_tx = prep_resp["preparedTransaction"]
    prep_hash = prep_resp["preparedTransactionHash"]
    hashing_scheme = prep_resp["hashingSchemeVersion"]
    print("Prepared Transaction Hash:", prep_hash)
    
    print("\nStep 3: Signing the transaction hash locally...")
    sig_bytes = sign_hash_bytes(prep_hash)
    sig_base64 = base64.b64encode(sig_bytes).decode('utf-8')
    
    print("\nStep 4: Executing submission package...")
    success, resp = execute_submission(prepared_tx, hashing_scheme, sig_base64)
    if success:
        print("\n🎉 TRANSFER INSTRUCTION ACCEPTED SUCCESSFULLY!")
        print("Update ID:", resp.get("updateId"))
    else:
        print("\n❌ Acceptance failed:", resp)

if __name__ == "__main__":
    main()
