import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# --- CONFIGURATION ENVIRONNEMENT ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9151678108:AAEDK84KdO-dc_CiWTtvoFkqUiiHOKzgutU")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8318321568")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Dictionnaire pour stocker les messages en attente de validation
pending_replies = {}

# --- SYSTEM PROMPT POUR L'IA ---
SYSTEM_PROMPT = """
Tu es l'assistante virtuelle d'Amaris Creed sur TastySlips. Ton ton doit être naturel, court, fluide et pro.

CONSIGNES STRICTES DE STYLE :
- Pas de sur-utilisation de points d'exclamation.
- Maximum UN SEUL emoji à la toute fin du message.
- Langue : Réponds en FRANÇAIS si le client écrit en français. Si le client écrit dans n'importe quelle AUTRE langue, réponds obligatoirement en ANGLAIS.

CONSIGNES MÉTIER :
1. Plateformes externes (Snapchat, Telegram, WhatsApp, etc.) : Refuse poliment. Dis que tout se passe exclusivement sur TastySlips.
2. Compréhension du besoin client :
   - Vidéos : Demande la durée, les positions/angles souhaités, s'il y a un fétiche spécifique.
   - Photos : Demande le nombre de photos, le style ou la tenue.
   - Articles physiques (culottes, chaussettes...) : Indique que les articles sont disponibles sur la boutique. Si la demande n'y est pas, précise que tu réalises des commandes custom sur-mesure dans la mesure du raisonnable.
3. Finalisation : Ne valide JAMAIS une vente directement, indique que tu prépares la commande ou que tu demandes confirmation.
"""

def generate_ai_reply(client_message):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": client_message}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        return "Désolée, je regarde ça et je te réponds très vite 😊"

def send_telegram_alert(msg_id, client_msg, ai_reply):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        f"📩 **Nouveau message client**\n\n"
        f"👤 **Client :** {client_msg}\n\n"
        f"🤖 **Proposition de l'IA :**\n{ai_reply}\n\n"
        f"👇 *Clique sur Valider pour confirmer.*"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Valider et Envoyer", "callback_data": f"approve_{msg_id}"}
            ]]
        }
    }
    requests.post(url, json=payload)

# --- WEBHOOK POUR RECEVOIR LES MESSAGES ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    client_message = data.get("message", "").strip()

    if not client_message:
        return jsonify({"status": "error", "reason": "message vide"}), 400

    msg_id = str(hash(client_message))
    ai_reply = generate_ai_reply(client_message)
    
    pending_replies[msg_id] = {
        "client_msg": client_message,
        "reply": ai_reply
    }

    send_telegram_alert(msg_id, client_message, ai_reply)
    return jsonify({"status": "success", "ai_reply": ai_reply}), 200

# --- WEBHOOK TELEGRAM POUR LES CLICS DE VALIDATION ---
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()

    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        action_data = callback["data"]

        if action_data.startswith("approve_"):
            msg_id = action_data.split("approve_")[1]
            if msg_id in pending_replies:
                final_text = pending_replies[msg_id]["reply"]
                
                print(f"[VALIDÉ PAR TOI] Envoi effectif de : {final_text}")

                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": callback_id,
                    "text": "Message validé avec succès !"
                })
                del pending_replies[msg_id]

    return jsonify({"status": "ok"}), 200

@app.route('/')
def home():
    return "Bot TastySlips Prêt et Opérationnel", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
