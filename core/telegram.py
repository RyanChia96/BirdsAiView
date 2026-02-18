"""
Telegram notification logic. Load config from config.json or env.
"""
import os
import requests


def get_telegram_config(config: dict | None = None) -> tuple[str, str]:
    """Return (bot_token, chat_id). Prefer config dict, then env."""
    if config:
        token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = config.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    else:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError("Telegram credentials missing. Set in config.json or .env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).")
    return token, chat_id


def send_telegram(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=20)
    if not r.ok:
        try:
            err = r.json()
            msg = err.get("description", r.text)
        except Exception:
            msg = r.text or r.reason
        raise requests.HTTPError(f"Telegram API: {msg}", response=r)


def html_escape(s: str) -> str:
    """Escape text for Telegram HTML parse_mode: & < >"""
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
