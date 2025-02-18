from flask import Flask, request, jsonify
import requests
import os
import traceback
from datetime import datetime
import time

app = Flask(__name__)

# Configuration with validation
try:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
    MONITORED_WALLET = "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS"
    
    HELIUS_RPC = f"https://rpc.helius.xyz/?api-key={HELIUS_API_KEY}"
    
    print("\n=== CONFIGURATION VALID ===")
    print(f"MONITORED_WALLET: {MONITORED_WALLET}")
    print(f"HELIUS_API_KEY: {'configured' if HELIUS_API_KEY else 'missing'}")
    print("Environment variables loaded successfully\n")
    
except KeyError as e:
    print(f"\n🚨 CRITICAL ERROR: Missing environment variable - {e}")
    exit(1)

def log_error(context, error, response=None):
    print(f"\n⚠️ ERROR IN {context.upper()} ⚠️")
    print(f"Type: {type(error).__name__}")
    print(f"Message: {str(error)}")
    
    if response:
        print(f"Response Status: {response.status_code}")
        print(f"Response Text: {response.text[:300]}...")
        
    traceback.print_exc()
    print("="*50)

def create_alert(event, amount, recipient, is_new):
    timestamp = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
    return (
        "🚨 SUSPICIOUS TRANSACTION DETECTED\n"
        f"• Amount: {amount:.2f} SOL\n"
        f"• From: {MONITORED_WALLET[:6]}...{MONITORED_WALLET[-4:]}\n"
        f"• To: {recipient[:6]}...{recipient[-4:]} "
        f"{'(🆕 NEW WALLET)' if is_new else ''}\n"
        f"• Time: {timestamp}\n"
        f"• Wallet: https://solscan.io/account/{recipient}\n"
        f"• TX: https://solscan.io/tx/{event['signature']}"
    )

def check_new_wallet(wallet_address, current_slot, current_tx_signature):
    """Check if wallet has ANY transactions before current one"""
    try:
        print(f"\n🔎 Freshness check for {wallet_address[:6]}...")
        
        # First check account creation slot
        acc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [wallet_address]
        }
        
        acc_response = requests.post(HELIUS_RPC, json=acc_payload)
        acc_response.raise_for_status()
        acc_data = acc_response.json()
        
        # If account doesn't exist, it's new
        if not acc_data['result']['value']:
            print("✅ Brand new wallet (no account exists)")
            return True
            
        creation_slot = acc_data['result']['value']['owner'] != "11111111111111111111111111111111" and \
                       acc_data['result']['value']['lamports'] > 0
        
        # Now check transaction history comprehensively
        all_txs = []
        before = None
        
        while True:
            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    wallet_address,
                    {"limit": 100, "before": before}
                ]
            }
            
            time.sleep(0.3)
            tx_response = requests.post(HELIUS_RPC, json=tx_payload)
            tx_response.raise_for_status()
            txs = tx_response.json().get('result', [])
            
            if not txs:
                break
                
            all_txs.extend(txs)
            before = txs[-1]['signature']

        # Check all historical transactions
        for tx in all_txs:
            if tx.get('signature') == current_tx_signature:
                continue
                
            if tx.get('slot', 0) < current_slot:
                print(f"🚫 Found older transaction: {tx['signature'][:6]}... (slot {tx['slot']})")
                return False
                
        print("✅ No older transactions found")
        return True
        
    except Exception as e:
        log_error("WALLET FRESHNESS CHECK", e, getattr(e, 'response', None))
        return False
        
def validate_transfer(event):
    """Validate transfer with strict amount filtering"""
    try:
        transfers = event.get('nativeTransfers', [])
        if not transfers:
            return False, 0, ""
            
        for transfer in transfers:
            amount = transfer.get('amount', 0)
            from_wallet = transfer.get('fromUserAccount', '')
            to_wallet = transfer.get('toUserAccount', '')
            
            amount_sol = amount / 1e9
            if 1 <= amount_sol <= 90 and from_wallet == MONITORED_WALLET:
                print(f"🟢 Valid transfer: {amount_sol:.2f} SOL to {to_wallet[:6]}...")
                return True, amount_sol, to_wallet
                
        return False, 0, ""
        
    except Exception as e:
        log_error("TRANSFER VALIDATION", e)
        return False, 0, ""

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
        events = request.json
        for event in events:
            valid, amount, recipient = validate_transfer(event)
            if valid:
                current_slot = event.get('slot')
                current_tx_signature = event.get('signature')
                
                is_new = check_new_wallet(recipient, current_slot, current_tx_signature)
                
                if is_new:
                    message = create_alert(event, amount, recipient, True)
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={
                            "chat_id": CHAT_ID,
                            "text": message,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True
                        },
                        timeout=10
                    )
                    print("📤 Alert sent for new wallet")
                    
        return jsonify({"status": "processed"}), 200

    except Exception as e:
        log_error("WEBHOOK HANDLER", e)
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
