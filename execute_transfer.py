import urllib.request
import json
import sys
import uuid
import datetime
import base64
import subprocess
import os
from test_auth import get_token

validator_url = "https://api.validator.dev.digik.cantor8.tech/api/validator"
ledger_url = "https://api.validator.dev.digik.cantor8.tech/api/ledger"
dso_party = "DSO::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a"

# Default parties:
ezoh_party = "ezoh::1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"
intro_party = "cantor8_intro_party::12209750ddd3a9ecae882e913fa31e0b6188b07f66739b2fd739d9c47d93cf86602f"

def get_ledger_end():
    token = get_token()
    url = f"{ledger_url}/v2/state/ledger-end"
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode('utf-8'))
        return body["offset"]

def get_active_holdings(sender_party, offset):
    token = get_token()
    url = f"{ledger_url}/v2/state/active-contracts"
    
    data = {
        "activeAtOffset": offset,
        "filter": {
            "filtersByParty": {
                sender_party: {
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
    
    holdings = []
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode('utf-8'))
        for entry in body:
            contract = entry.get("contractEntry", {}).get("JsActiveContract", {}).get("createdEvent", {})
            template_id = contract.get("templateId", "")
            if "Holding" in template_id or "Amulet" in template_id:
                holdings.append(contract)
    return holdings

def call_transfer_factory(sender, receiver, amount, input_cids, now_str, expiry_str):
    token = get_token()
    url = f"{validator_url}/v0/scan-proxy/registry/transfer-instruction/v1/transfer-factory"
    
    data = {
        "choiceArguments": {
            "expectedAdmin": dso_party,
            "transfer": {
                "sender": sender,
                "receiver": receiver,
                "amount": str(amount),
                "instrumentId": {
                    "admin": dso_party,
                    "id": "Amulet"
                },
                "inputHoldingCids": input_cids,
                "requestedAt": now_str,
                "executeBefore": expiry_str,
                "meta": {
                    "values": {}
                }
            }
        }
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
            print("Transfer Factory error details:", e.read().decode('utf-8'))
        raise e

def sign_hash_bytes(hash_b64, key_file):
    hash_bytes = base64.b64decode(hash_b64)
    with open("temp_tx_hash.bin", "wb") as f:
        f.write(hash_bytes)
    subprocess.run([
        "openssl", "pkeyutl", "-sign",
        "-inkey", key_file,
        "-rawin", "-in", "temp_tx_hash.bin",
        "-out", "temp_tx_sig.bin"
    ], check=True)
    with open("temp_tx_sig.bin", "rb") as f:
        sig_bytes = f.read()
    os.remove("temp_tx_hash.bin")
    os.remove("temp_tx_sig.bin")
    return sig_bytes

def prepare_submission(sender, receiver, amount, input_cids, now_str, expiry_str, factory_resp):
    token = get_token()
    url = f"{ledger_url}/v2/interactive-submission/prepare"
    command_id = f"transfer-{uuid.uuid4()}"
    transfer_pkg_id = "55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281"
    template_id = f"{transfer_pkg_id}:Splice.Api.Token.TransferInstructionV1:TransferFactory"
    
    data = {
        "commandId": command_id,
        "actAs": [sender],
        "synchronizerId": "global-domain::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a",
        "packageIdSelectionPreference": [transfer_pkg_id],
        "disclosedContracts": factory_resp["disclosedContracts"],
        "commands": [
            {
                "ExerciseCommand": {
                    "templateId": template_id,
                    "contractId": factory_resp["factoryId"],
                    "choice": "TransferFactory_Transfer",
                    "choiceArgument": {
                        "transfer": {
                            "sender": sender,
                            "receiver": receiver,
                            "amount": str(amount),
                            "instrumentId": {
                                "admin": dso_party,
                                "id": "Amulet"
                            },
                            "inputHoldingCids": input_cids,
                            "requestedAt": now_str,
                            "executeBefore": expiry_str,
                            "meta": {
                                "values": {}
                            }
                        },
                        "extraArgs": {
                            "meta": {
                                "values": {}
                            },
                            "context": factory_resp["choiceContext"]["choiceContextData"]
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
            print("Prepare exercise error details:", e.read().decode('utf-8'))
        raise e

def execute_submission(sender, prepared_tx, hashing_scheme, sig_encoded, key_fingerprint):
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
                    "party": sender,
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
    if len(sys.argv) < 3:
        print("Usage: python3 execute_transfer.py <recipient_party_id> <amount> [sender_party_hint: ezoh or intro]")
        sys.exit(1)
        
    recipient = sys.argv[1]
    amount = float(sys.argv[2])
    
    sender_hint = sys.argv[3] if len(sys.argv) > 3 else "ezoh"
    if sender_hint == "intro":
        sender = intro_party
        key_file = "party_key.pem"
        key_fingerprint = "12209750ddd3a9ecae882e913fa31e0b6188b07f66739b2fd739d9c47d93cf86602f"
    else:
        sender = ezoh_party
        key_file = "party_key_ezoh.pem"
        key_fingerprint = "1220df89de3eee5904250d6336dcbd24b427285b82d41598836beec234e53ee2d115"
        
    print(f"Transferring {amount} CC from {sender} to {recipient}...")
    
    print("\nStep 1: Finding active holdings for sender...")
    offset = get_ledger_end()
    holdings = get_active_holdings(sender, offset)
    print(f"Found {len(holdings)} holdings.")
    
    # Select holdings to cover amount
    selected_holdings = []
    selected_sum = 0.0
    for h in holdings:
        amt_info = h.get("createArgument", {}).get("amount", {})
        val = float(amt_info.get("initialAmount", amt_info.get("value", 0.0)))
        selected_holdings.append(h["contractId"])
        selected_sum += val
        if selected_sum >= amount:
            break
            
    if selected_sum < amount:
        print(f"INSUFFICIENT BALANCE! Total balance: {selected_sum} CC, requested: {amount} CC")
        sys.exit(1)
        
    print(f"Selected {len(selected_holdings)} inputs covering {selected_sum} CC.")
    
    # Timestamps (ISO 8601 UTC)
    now = datetime.datetime.utcnow()
    expiry = now + datetime.timedelta(minutes=5)
    now_str = now.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    expiry_str = expiry.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    
    print("\nStep 2: Requesting context from Transfer Factory...")
    factory_resp = call_transfer_factory(sender, recipient, amount, selected_holdings, now_str, expiry_str)
    print("Transfer Factory response obtained successfully.")
    
    print("\nStep 3: Preparing transaction on Ledger API...")
    prep_resp = prepare_submission(sender, recipient, amount, selected_holdings, now_str, expiry_str, factory_resp)
    prepared_tx = prep_resp["preparedTransaction"]
    prep_hash = prep_resp["preparedTransactionHash"]
    hashing_scheme = prep_resp["hashingSchemeVersion"]
    print("Prepared Transaction Hash:", prep_hash)
    
    print("\nStep 4: Signing the transaction hash locally...")
    sig_bytes = sign_hash_bytes(prep_hash, key_file)
    sig_base64 = base64.b64encode(sig_bytes).decode('utf-8')
    
    print("\nStep 5: Submitting execution package...")
    success, resp = execute_submission(sender, prepared_tx, hashing_scheme, sig_base64, key_fingerprint)
    if success:
        print("\n🎉 TRANSFER SUCCESS!")
        print("Update ID:", resp.get("updateId"))
        print(f"Verify new balance by running: python3 verify_balance.py {sender_hint}")
    else:
        print("\n❌ Transfer submission failed:", resp)

if __name__ == "__main__":
    main()
