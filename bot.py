import os
import asyncio
import requests
from flask import Flask, request, jsonify
from threading import Thread
from openai import OpenAI
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ENVIRONNEMENT ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9151678108:AAEDK84KdO-dc_CiWTtvoFkqUiiHOKzgutU")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8318321568")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Dictionnaire pour stocker les messages en attente
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

# --- ACTION D'ENVOI AUTOMATISÉ SUR TASTYSLIPS ---
async def send_reply_to_tastyslips(reply_text):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigation vers la page des messages
            await page.goto("https://www.tastyslips.com/messages", wait_until="networkidle")
            
            # Simulation de la saisie dans le champ de message et clic sur envoyer
            # (S'adapte aux sélecteurs standards de messagerie)
            await page.fill("textarea, input[type='text']", reply_text)
            await page.keyboard.press("Enter")
            
            print(f"[Playwright] Réponse envoyée avec succès sur le site : {reply_text}")
        except Exception as e:
            print(f"[Playwright Erreur d'envoi] : {e}")
        finally:
            await browser.close()

# --- BOT DE SURVEILLANCE AUTONOME ---
async def run_tastyslips_watcher():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        
        print("[Watcher] Démarrage de la surveillance autonome...")
        last_processed_msg = ""

        while True:
            try:
                await page.goto("https://www.tastyslips.com/messages", wait_until="networkidle")
                
                message_el = await page.query_selector('.text-sm, .truncate')
                if message_el:
                    text = (await message_el.inner_text()).strip()
                    
                    if text and text != last_processed_msg and len(text) > 2:
                        last_processed_msg = text
                        msg_id = str(hash(text))
                        
                        ai_reply = generate_ai_reply(text)
                        pending_replies[msg_id] = {
                            "client_msg": text,
                            "reply": ai_reply
                        }
                        
                        send_telegram_alert(msg_id, text, ai_reply)

            except Exception as e:
                print(f"[Watcher Error] {e}")

            await asyncio.sleep(60)

# --- WEBHOOK TELEGRAM ---
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
                
                # Exécution de l'envoi automatisé
                asyncio.run(send_reply_to_tastyslips(final_text))

                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": callback_id,
                    "text": "Message validé et envoyé au client !"
                })
                del pending_replies[msg_id]

    elif "message" in data and "reply_to_message" in data["message"]:
        modified_text = data["message"]["text"]
        
        # Envoi de la version modifiée saisie sur Telegram
        asyncio.run(send_reply_to_tastyslips(modified_text))
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"✅ Version modifiée envoyée au client :\n\"{modified_text}\""
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
    t = Thread(target=start_async_loop)
    t.daemon = True
    t.start()
    
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
