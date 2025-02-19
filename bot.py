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
    TATUM_API_KEY = os.getenv('TATUM_API_KEY')  # Changed from HELIUS_API_KEY
    MONITORED_WALLET = "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS"
    
    print("\n=== CONFIGURATION VALID ===")
    print(f"MONITORED_WALLET: {MONITORED_WALLET}")
    print(f"TATUM_API_KEY: {'configured' if TATUM_API_KEY else 'missing'}")
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

def create_alert(tx_data, amount, recipient, is_new):
    timestamp = datetime.fromtimestamp(tx_data['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')
    return (
        "🚨 SUSPICIOUS TRANSACTION DETECTED\n"
        f"• Amount: {amount:.2f} SOL\n"
        f"• From: {MONITORED_WALLET[:6]}...{MONITORED_WALLET[-4:]}\n"
        f"• To: {recipient[:6]}...{recipient[-4:]} "
        f"{'(🆕 NEW WALLET)' if is_new else ''}\n"
        f"• Time: {timestamp}\n"
        f"• Wallet: https://solscan.io/account/{recipient}\n"
        f"• TX: https://solscan.io/tx/{tx_data['txId']}"
    )

def check_new_wallet(wallet_address):
    """Check if wallet has any previous transactions using Tatum"""
    try:
        print(f"\n🔎 Freshness check for {wallet_address[:6]}...")
        
        response = requests.get(
            f"https://api.tatum.io/v3/solana/account/transaction/{wallet_address}",
            headers={"x-api-key": TATUM_API_KEY}
        )
        response.raise_for_status()
        
        transactions = response.json()
        
        # No transactions = new wallet
        if not transactions:
            print("✅ Brand new wallet (no history)")
            return True
            
        print(f"🚫 Found {len(transactions)} previous transactions")
        return False
        
    except Exception as e:
        log_error("WALLET FRESHNESS CHECK", e)
        return False

def validate_transfer(event):
    """Validate transfer with Tatum webhook structure"""
    try:
        # Tatum webhook structure for SOL_TRANSFER
        if event.get('type') != 'SOL_TRANSFER':
            return False, 0, ""
            
        amount = event.get('amount', 0)
        from_wallet = event.get('from', '')
        to_wallet = event.get('to', '')
        
        amount_sol = amount / 1e9
        if 1 <= amount_sol <= 5 and from_wallet == MONITORED_WALLET:
            print(f"🟢 Valid transfer: {amount_sol:.2f} SOL to {to_wallet[:6]}...")
            return True, amount_sol, to_wallet
            
        return False, 0, ""
        
    except Exception as e:
        log_error("TRANSFER VALIDATION", e)
        return False, 0, ""

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
        event = request.json  # Tatum sends single event per webhook
        valid, amount, recipient = validate_transfer(event)
        
        if valid:
            # Get additional transaction details
            tx_data = {
                'txId': event.get('txId'),
                'timestamp': event.get('timestamp'),
            }
            
            is_new = check_new_wallet(recipient)
            
            if is_new:
                message = create_alert(tx_data, amount, recipient, True)
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
