import urllib.request
import json
import sys
from test_auth import get_token

ledger_url = "https://api.validator.dev.digik.cantor8.tech/api/ledger"

# Default to the new ezoh party ID
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

def verify_balance(party_id, offset):
    token = get_token()
    url = f"{ledger_url}/v2/state/active-contracts"
    
    data = {
        "activeAtOffset": offset,
        "filter": {
            "filtersByParty": {
                party_id: {
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
    
    try:
        with urllib.request.urlopen(req) as response:
            body = json.loads(response.read().decode('utf-8'))
            
            holdings = []
            preapprovals = []
            preapproval_proposals = []
            
            for entry in body:
                contract = entry.get("contractEntry", {}).get("JsActiveContract", {}).get("createdEvent", {})
                template_id = contract.get("templateId", "")
                if "Holding" in template_id or "Amulet" in template_id:
                    holdings.append(contract)
                elif "TransferPreapprovalProposal" in template_id:
                    preapproval_proposals.append(contract)
                elif "TransferPreapproval" in template_id:
                    preapprovals.append(contract)
            
            print(f"\n================ BALANCE REPORT ================")
            print(f"Party ID: {party_id}")
            print(f"TransferPreapprovalProposal Contracts Active: {len(preapproval_proposals)}")
            print(f"TransferPreapproval Contracts Active (Accepted): {len(preapprovals)}")
            print(f"Canton Coin UTXOs: {len(holdings)}")
            
            total_balance = 0.0
            for h in holdings:
                args = h.get("createArgument", {})
                amt_info = args.get("amount", {})
                amount = float(amt_info.get("initialAmount", amt_info.get("value", 0.0)))
                total_balance += amount
                
            print(f"TOTAL CC BALANCE: {total_balance} CC")
            print(f"================================================\n")
            
            return body
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'read'):
            try:
                print(e.read().decode('utf-8'))
            except:
                pass

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "ezoh"
    if arg == "intro":
        party_id = intro_party
    elif arg == "ezoh":
        party_id = ezoh_party
    else:
        party_id = arg
    offset = get_ledger_end()
    verify_balance(party_id, offset)
