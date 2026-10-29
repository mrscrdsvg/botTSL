import os
import asyncio
import requests
from flask import Flask, request, jsonify
from threading import Thread
from openai import OpenAI
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ENVRIONNEMENT ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9151678108:AAEDK84KdO-dc_CiWTtvoFkqUiiHOKzgutU")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8318321568")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TASTYSLIPS_COOKIE = os.getenv("TASTYSLIPS_COOKIE")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Dictionnaire temporaire pour stocker les propositions en attente de validation
pending_replies = {}

# --- SYSTEM PROMPT POUR L'IA ---
SYSTEM_PROMPT = """
Tu es l'assistante virtuelle d'Amaris Creed sur TastySlips. Ton ton doit être naturel, court, fluide et pro.

CONSIGNES STRICTES DE STYLE :
- Pas de sur-utilisation de points d'exclamation.
- Maximum UN SEUL emoji à la toute fin du message.
- Langue : Réponds en FRANÇAIS si le client écrit en français. Si le client écrit dans n'importe quelle AUTRE langue (anglais, allemand, espagnol, etc.), réponds obligatoirement en ANGLAIS.

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
        f"👇 *Clique sur Valider ou réponds à ce message Telegram pour modifier la réponse.*"
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

# --- BOT DE SURVEILLANCE AUTONOME (PLAYWRIGHT) ---
async def run_tastyslips_watcher():
    if not TASTYSLIPS_COOKIE:
        print("[ERR] TASTYSLIPS_COOKIE manquant dans l'environnement.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Injection du cookie de session
        await context.add_cookies([{
            'name': 'session', # À adapter selon le nom exact du cookie TastySlips
            'value': TASTYSLIPS_COOKIE,
            'domain': '.tastyslips.com',
            'path': '/'
        }])

        page = await context.new_page()
        print("[Watcher] Connexion autonome à TastySlips lancée...")

        last_processed_msg = ""

        while True:
            try:
                await page.goto("https://www.tastyslips.com/messages", wait_until="networkidle")
                
                # Extraction du dernier message reçu
                message_el = await page.query_selector('.text-sm, .truncate')
                if message_el:
                    text = (await message_el.inner_text()).strip()
                    
                    if text and text != last_processed_msg and len(text) > 2:
                        last_processed_msg = text
                        msg_id = str(hash(text))
                        
                        # Génération de la réponse via l'IA
                        ai_reply = generate_ai_reply(text)
                        pending_replies[msg_id] = {
                            "client_msg": text,
                            "reply": ai_reply
                        }
                        
                        # Envoi de l'alerte Telegram
                        send_telegram_alert(msg_id, text, ai_reply)

            except Exception as e:
                print(f"[Watcher Error] {e}")

            # Attente de 60 secondes avant la prochaine vérification
            await asyncio.sleep(60)

# --- WEBHOOK TELEGRAM POUR VALIDATION / MODIFICATION ---
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()

    # 1. Gestion du clic sur le bouton "Valider"
    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        action_data = callback["data"]

        if action_data.startswith("approve_"):
            msg_id = action_data.split("approve_")[1]
            if msg_id in pending_replies:
                final_text = pending_replies[msg_id]["reply"]
                
                # TODO: Envoyer la réponse sur TastySlips via Playwright
                print(f"[ENVOI EFFECTUÉ] : {final_text}")

                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": callback_id,
                    "text": "Message validé et envoyé au client !"
                })
                del pending_replies[msg_id]

    # 2. Gestion de la modification par réponse directe sur Telegram
    elif "message" in data and "reply_to_message" in data["message"]:
        modified_text = data["message"]["text"]
        
        # On envoie la version modifiée
        print(f"[ENVOI TEXTE MODIFIÉ] : {modified_text}")
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"✅ Ta version modifiée a bien été envoyée :\n\"{modified_text}\""
        })

    return jsonify({"status": "ok"}), 200

@app.route('/')
def home():
    return "Bot TastySlips Autonome Opérationnel", 200

def start_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_tastyslips_watcher())

if __name__ == '__main__':
    # Lancement du navigateur de surveillance en arrière-plan
    t = Thread(target=start_async_loop)
    t.daemon = True
    t.start()
    
    # Lancement de l'application Flask
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
