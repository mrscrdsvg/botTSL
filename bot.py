import os
import requests
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "9151678108:AAEDK84KdO-dc_CiWTtvoFkqUiiHOKzgutU"
TELEGRAM_CHAT_ID = "8318321568"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

PENDING_MESSAGES = {}
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

def analyze_context(client_message):
    """Génère rapidement un mini-contexte pour savoir de quoi parle la discussion."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Résume le sujet de cette discussion en 3 ou 4 mots maximum (ex: Vente de vêtement, Question tarif, Négociation...). Soit très bref."},
            {"role": "user", "content": client_message}
        ],
        "temperature": 0.3
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        return response.json()["choices"][0]["message"]["content"].strip()
    except:
                return "Discussion en cours"

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
        print("Erreur OpenAI:", e, flush=True)
        return "Bonjour, j'ai bien pris note de ton message !"

def send_reply_to_tastyslips(reply_url, message_text):
    if not reply_url:
        print("Erreur: Aucune URL de réponse fournie", flush=True)
        return False
    try:
        payload = {"message": message_text}
        response = requests.post(reply_url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print("Erreur lors de l'envoi vers TastySlips:", e, flush=True)
        return False

def send_telegram_approval(client_message, ai_reply, is_returning, reply_url):
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    heure_str = now.strftime("%H:%M")
    
    # Analyse rapide du contexte
    context_topic = analyze_context(client_message)

    tag = "⭐ **CLIENT RÉCURRENT**" if is_returning else "🚨 **NOUVEAU MESSAGE CLIENT**"
    
    text = (
        f"{tag}\n"
        f"📌 **Contexte :** _{context_topic}_\n"
        f"📅 **Date :** {date_str} à {heure_str}\n\n"
        f"💬 **Message reçu :**\n{client_message}\n\n"
        f"🤖 **Proposition IA :**\n{ai_reply}\n\n"
        f"👉 *Clique ci-dessous pour envoyer ou réponds au message pour modifier.*"
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Valider et Envoyer", "callback_data": "approve"},
                {"text": "❌ Ignorer", "callback_data": "reject"}
            ]
        ]
    }
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        msg_data = resp.json()
        tg_msg_id = msg_data["result"]["message_id"]
        PENDING_MESSAGES[tg_msg_id] = {
            "ai_reply": ai_reply,
            "reply_url": reply_url
        }

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
    reply_url = data.get("reply_url") or data.get("url")

    if "supprimé" in sender_status or "deleted" in sender_status or not client_message:
        return "Ignoré", 200

    # Anti-doublon strict (ignore si le message exact a déjà été traité récemment)
    if client_message in processed_messages:
        return "Déjà traité", 200

    processed_messages.add(client_message)
    if len(processed_messages) > 200:
        processed_messages.pop(0)

    ai_reply = ask_openai(client_message)
    send_telegram_approval(client_message, ai_reply, is_returning, reply_url)

    return "OK", 200

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    if not update:
        return "OK", 200

    if "callback_query" in update:
        cq = update["callback_query"]
        tg_msg_id = cq["message"]["message_id"]
        data_action = cq["data"]
        
        url_answer = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
        
        if tg_msg_id in PENDING_MESSAGES:
            pending = PENDING_MESSAGES[tg_msg_id]
            if data_action == "approve":
                # Envoi effectif de la réponse vers la plateforme
                send_reply_to_tastyslips(pending["reply_url"], pending["ai_reply"])
                edit_text = cq["message"]["text"] + "\n\n✅ **STATUT : Envoyé avec succès !**"
            else:
                edit_text = cq["message"]["text"] + "\n\n❌ **STATUT : Ignoré.**"
                
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_id": tg_msg_id,
                "text": edit_text,
                "parse_mode": "Markdown"
            })
            requests.post(url_answer, json={"callback_query_id": cq["id"], "text": "Action prise en compte !"})
            del PENDING_MESSAGES[tg_msg_id]
        else:
            requests.post(url_answer, json={"callback_query_id": cq["id"], "text": "Déjà traité ou expiré."})

    elif "message" in update and "reply_to_message" in update["message"]:
        msg = update["message"]
        replied_msg_id = msg["reply_to_message"]["message_id"]
        custom_reply_text = msg.get("text", "").strip()
        
        if replied_msg_id in PENDING_MESSAGES and custom_reply_text:
            pending = PENDING_MESSAGES[replied_msg_id]
            send_reply_to_tastyslips(pending["reply_url"], custom_reply_text)
            
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"✍️ **Modifié et envoyé :**\n{custom_reply_text}",
                "parse_mode": "Markdown"
            })
            del PENDING_MESSAGES[replied_msg_id]

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
