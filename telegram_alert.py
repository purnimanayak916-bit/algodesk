"""
telegram_alert.py
Minimal Telegram bot notification helper. Requires:
  - a bot token from @BotFather
  - your chat_id (message @userinfobot to get it)
Both are read from Streamlit secrets, never hardcoded.
"""

import requests


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False
