import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "9151678108:AAEDK84KdO-dc_CiWTtvoFkqUiiHOKzgutU"
TELEGRAM_CHAT_ID = "8318321568"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

processed_messages = set()

SYSTEM_PROMPT = """Tu es une vraie personne qui discute sur un profil de vente en ligne. Tu réponds de façon ultra-naturelle, branchée et spontanée, sans aucun jargon commercial ni style robotique.

RÈGLE DES LANGUES :
- Si le client écrit en français ➔ réponds en français naturel.
- Si le client écrit dans une autre langue ➔ réponds en anglais fluide.

RÈGLE ANTI-RÉSEAUX EXTERNES :
- Si le client demande Snapchat, Telegram ou autre, refuse net mais poliment en disant qu'on reste uniquement ici sur le site.

TON ET STYLE :
- Adapte le tutoiement ou vouvoiement selon comment le client s'adresse à toi.
- Pas de prix fixes (dis juste que tu prends note pour confirmer le tarif).
- Style direct, zéro guillemets, zéro formule robotique."""

def ask_openai(client_message):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": client_message}
        ],
        "temperature": 0.8
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        res_json = response.json()
        reply = res_json["choices"][0]["message"]["content"].strip()
        if reply.startswith(('"', '“', '«')) and reply.endswith(('"', '”', '»')):
            reply = reply[1:-1].strip()
        return reply
    except Exception as e:
        print("Erreur OpenAI:", e)
        return "Bonjour, j'ai bien pris note de ton message !"

def send_telegram(client_message, ai_reply, is_returning):
    tag = "⭐ **IMPORTANT - Client récurrent**" if is_returning else "🚨 **IMPORTANT - Nouveau message client**"
    text = f"{tag} :\n{client_message}\n\n🤖 **Proposition** :\n{ai_reply}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

@app.route('/')
def home():
    return "Serveur Bot TastySlips actif !"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data:
        return "OK", 200

    client_message = data.get("message", "").strip()
    sender_status = data.get("status", "").lower()
    is_returning = data.get("is_returning", False)

    if "supprimé" in sender_status or "deleted" in sender_status or not client_message:
        return "Ignoré (Compte supprimé ou vide)", 200

    if client_message in processed_messages:
        return "Déjà traité", 200

    processed_messages.add(client_message)
    if len(processed_messages) > 500:
        processed_messages.pop()

    ai_reply = ask_openai(client_message)
    send_telegram(client_message, ai_reply, is_returning)

    return "Message traité avec succès", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
