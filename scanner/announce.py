"""One-off Telegram jobs: confirmation message, bot profile (description, commands, photo)."""
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOK = os.environ["TELEGRAM_BOT_TOKEN"].strip()
API = f"https://api.telegram.org/bot{TOK}"
chat = os.getenv("TELEGRAM_CHAT_ID") or json.loads((ROOT / "data" / "state.json").read_text()).get("tg_chat")

DESCRIPTION = (
    "Gold Desk watches XAUUSD (spot gold) at every 5-minute candle close, 24/5, and sends trade calls automatically.\n\n"
    "Every call: entry, stop loss, take profit, 0.01-lot risk in £.\n"
    "Strategy: Andrea Unger's systematic gold breakouts (4x World Cup Trading Champion), backtested on years of gold.\n"
    "News filter: no new trades ±30 min around red-folder USD news.\n"
    "Daily: 06:45 London brief · 08:30 news folders · 13:15 New York brief.\n\n"
    "Paper/demo trading only. Not financial advice."
)
SHORT = "Automatic gold (XAUUSD) signals: entry, stop, take profit. Checks every 5-min candle, 24/5. Demo only."
COMMANDS = [("price", "Live gold price"), ("levels", "4H/1H/daily levels map"), ("folders", "Today's news folders"),
            ("news", "News & headline risk"), ("status", "Is the bot running?")]

CONFIRM = (
    "✅ <b>Confirmed: I send signals on my own.</b>\n\n"
    "You never need to prompt me. When gold gives a setup, the call lands here automatically: entry, stop loss, take profit.\n\n"
    "I run on GitHub's servers, not your laptop, your phone or Claude. Everything of yours can be switched off and I keep "
    "watching gold every 5 minutes, Sunday 23:00 → Friday 22:00 UK.\n\n"
    "All you need is Telegram notifications on, so the message reaches you."
)


def call(method, **kw):
    r = requests.post(f"{API}/{method}", timeout=30, **kw)
    print(method, r.status_code, r.text[:200])
    return r


def main():
    what = os.getenv("WHAT", "all")
    if what in ("all", "profile"):
        call("setMyDescription", json={"description": DESCRIPTION})
        call("setMyShortDescription", json={"short_description": SHORT})
        call("setMyCommands", json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
        logo = ROOT / "brand" / "logo.png"
        # Newer Bot API versions allow a bot to set its own photo; fall back to BotFather if not.
        with open(logo, "rb") as f:
            r = call("setMyProfilePhoto", data={"photo": json.dumps({"type": "static", "photo": "attach://logo"})},
                     files={"logo": f})
        state = "set" if r.ok and r.json().get("ok") else "manual"
        with open(logo, "rb") as f:
            cap = ("🟡 <b>Your new Gold Desk logo</b>\n" + (
                "It's now set as my profile photo." if state == "set" else
                "To use it as my profile photo: open @BotFather → /setuserpic → pick @riogolddesk_bot → send this image."))
            call("sendPhoto", data={"chat_id": chat, "caption": cap, "parse_mode": "HTML"}, files={"photo": f})
    if what == "custom":
        call("sendMessage", json={"chat_id": chat, "text": os.environ["MESSAGE"], "parse_mode": "HTML"})
    if what in ("all", "confirm"):
        call("sendMessage", json={"chat_id": chat, "text": CONFIRM, "parse_mode": "HTML"})


if __name__ == "__main__":
    main()
