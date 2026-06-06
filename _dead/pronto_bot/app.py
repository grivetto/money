import os
import json
import hmac
import hashlib
import time
from dotenv import load_dotenv
from flask import Flask, request, jsonify

load_dotenv()

CRYPTOCOM_API_KEY = os.getenv('CRYPTOCOM_API_KEY')
CRYPTOCOM_API_SECRET = os.getenv('CRYPTOCOM_API_SECRET')

# WhatsApp Business API credentials
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'denaro_verify_2024')

app = Flask(__name__)


def generate_signature(method, path, timestamp, body):
    """Genera firma HMAC-SHA256 per API Crypto.com (se utilizzata)."""
    message = f"{method}{path}{timestamp}{body}"
    sig = hmac.new(
        CRYPTOCOM_API_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return sig


# ─── WhatsApp Business API Webhook Verification ───────────────────────
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Meta verifica il webhook all'avvio."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print('Webhook verificato con successo.')
        return challenge, 200
    else:
        return 'Token di verifica non valido.', 403


# ─── WhatsApp Incoming Messages ────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Riceve messaggi WhatsApp in ingresso e risponde automaticamente."""
    data = request.get_json()
    print(f"[WEBHOOK] Ricevuto: {json.dumps(data, indent=2)[:500]}")

    try:
        entry = data.get('entry', [])
        if not entry:
            return jsonify({'status': 'ignored'}), 200

        for e in entry:
            changes = e.get('changes', [])
            for change in changes:
                value = change.get('value', {})
                messages = value.get('messages', [])

                for msg in messages:
                    sender = msg.get('from', '')
                    text_body = msg.get('text', {}).get('body', '').strip().lower()

                    # Salva il messaggio nel log
                    with open('/home/sergio/denaro/pronto_bot/whatsapp_messages.log', 'a') as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {sender}: {msg}\n")

                    # Genera risposta automatica
                    response_text = get_auto_reply(text_body)
                    send_whatsapp_message(sender, response_text)

    except Exception as ex:
        print(f"[ERRORE WEBHOOK] {ex}")
        # Salva l'errore per debug
        with open('/home/sergio/denaro/pronto_bot/error.log', 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {str(ex)}\n")

    return jsonify({'status': 'ok'}), 200


# ─── Auto-Reply Logic ───────────────────────────────────────────────────
GREETING_KEYWORDS = ['ciao', 'buongiorno', 'buonasera', 'salve', 'hello', 'hi']
EMERGENCY_KEYWORDS = ['guasto', 'rotto', 'perdita', 'allagamento', 'gas', 'acqua',
                      'caldaia', 'tubo', 'rubinetto', 'scarico', 'lavandino',
                      'wc', 'bagno', 'cucina', 'riscaldamento', 'condizionatore',
                      'frigo', 'lavatrice', 'asciugatrice', 'lavastoviglie']
URGENCY_KEYWORDS = ['urgente', 'subito', 'adesso', 'emergenza', 'immediatamente',
                    'per favore', 'sta uscendo']


def get_auto_reply(text):
    """Genera risposta automatica contestuale al messaggio del cliente."""
    text_lower = text.lower()

    # Saluto iniziale
    if any(kw in text_lower for kw in GREETING_KEYWORDS):
        return ("Ciao! 👋 Sono l'assistente virtuale del Pronto Intervento.\n\n"
                "Il tecnico in questo momento ha le mani occupate in un intervento, "
                "ma ci penso io a passargli la tua urgenza!\n\n"
                "👉 *Per poterti aiutare subito, descrivimi il problema in poche parole* "
                "(es. 'tubo rotto', 'caldaia bloccata', 'salvavita scatta').")

    # Rilevamento emergenza
    has_emergency = any(kw in text_lower for kw in EMERGENCY_KEYWORDS)
    has_urgency = any(kw in text_lower for kw in URGENCY_KEYWORDS)

    if has_emergency:
        urgency_note = "⚡ *SEGNALATO COME URGENTE*" if has_urgency else ""
        return (f"Ho capito, sembra un'urgenza! {urgency_note}\n\n"
                "Per aiutare il tecnico a prepararsi al meglio, potresti:\n\n"
                "1️⃣ *Descrivere il problema* (es. 'il rubinetto del bagno perde acqua')\n"
                "2️⃣ *Inviare una FOTO* del guasto se possibile\n"
                "3️⃣ *Comunicare il tuo indirizzo*\n\n"
                "Riceverai una risposta dal tecnico il prima possibile. "
                "Grazie per la pazienza! 🙏")

    # Messaggio generico / non riconosciuto
    return ("Grazie per il messaggio! 📩\n\n"
            "Il tecnico è attualmente impegnato in un intervento. "
            "Ti risponderemo il prima possibile.\n\n"
            "Se hai un'urgenza, scrivi la parola *'urgenza'* per dare priorità al tuo messaggio. "
            "👷")


def send_whatsapp_message(to_phone, message_text):
    """Invia un messaggio WhatsApp tramite API Meta Business."""
    import requests

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[WHATSAPP] Inviato a {to_phone}: status={resp.status_code}")
        return resp.status_code == 200
    except Exception as ex:
        print(f"[WHATSAPP ERRORE] {ex}")
        return False


# ─── Health Check / Debug ────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'whatsapp_configured': bool(WHATSAPP_TOKEN)}), 200


@app.route('/test', methods=['GET'])
def test_send():
    """Endpoint di test: invia un messaggio di prova."""
    target = request.args.get('to', '')
    if target:
        send_whatsapp_message(target, "✅ Test automatizzato dal Pronto Intervento Bot.")
        return f"Messaggio di test inviato a {target}"
    return "Specifica ?to=<numero>", 400


# ─── Avvio Server ────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f'🔧 Pronto Intervento WhatsApp Bot avviato sulla porta {port}')
    print(f'📱 WhatsApp configurato: {bool(WHATSAPP_PHONE_ID)}')
    app.run(host='0.0.0.0', port=port, debug=False)