# bot.py
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import json
import logging
import os
import asyncio

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ==== CONFIG LADEN ====
if not os.path.exists("config.json"):
    log.critical("❌ config.json nicht gefunden!")
    raise SystemExit(1)

with open("config.json", "r", encoding="utf-8") as f:
    try:
        config = json.load(f)
    except json.JSONDecodeError as e:
        log.critical(f"❌ Fehler beim Laden von config.json: {e}")
        raise SystemExit(1)

token = config.get("token")
if not token:
    log.critical("❌ Bot-Token nicht gefunden in config.json")
    raise SystemExit(1)

# ==== DISCORD INTENTS ====
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
intents.presences = True

# ==== BOT INITIALISIEREN ====
bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Ticket-Button-View importieren ====
try:
    from cogs.ticket_button_category_flow import TicketButtonView
except ImportError as e:
    log.error(f"❌ Konnte TicketButtonView nicht importieren – bitte cogs/ticket_button_category_flow.py prüfen. Fehler: {e}")
    TicketButtonView = None


@bot.event
async def on_ready():
    log.info(f"✅ Bot ist online als {bot.user} ({bot.user.id})")
    if TicketButtonView:
        # Persistent View registrieren (wichtig für Buttons nach Restart)
        bot.add_view(TicketButtonView())
        log.info("✅ Ticket-Button-Views registriert")


async def load_cogs():
    """Lädt alle benötigten Cogs"""
    cogs = [
        "cogs.role_cacher",
        "cogs.ticket_button_category_flow",
        "cogs.ticket_category_button",
        "cogs.absence_poster",  # ⬅️ NEU: Abwesenheiten automatisch posten
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            log.info(f"✅ Cog geladen: {cog}")
        except Exception as e:
            log.error(f"❌ Fehler beim Laden von {cog}: {e}")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(token)


if __name__ == "__main__":
    log.info("=== STARTE bot.py ===")
    log.info("✅ config.json geladen")
    log.info("→ Starte bot …")
    asyncio.run(main())
