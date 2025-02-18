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
    """Check if wallet has any transactions before current one"""
    try:
        print(f"\n🔎 Freshness check for {wallet_address[:6]}...")
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet_address, {"limit": 5}]
        }
        
        time.sleep(0.3)  # Rate limit protection
        response = requests.post(HELIUS_RPC, json=payload)
        response.raise_for_status()
        
        transactions = response.json().get('result', [])
        
        # No transactions = new wallet
        if not transactions:
            print("✅ Brand new wallet (no history)")
            return True
            
        # Check if any transaction is older than current one
        for tx in transactions:
            # Skip the current transaction itself
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