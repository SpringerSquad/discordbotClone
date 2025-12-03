# cogs/absence_poster.py
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
import json
from typing import Optional, List
from datetime import datetime

from utils.absence_storage import list_absences, mark_posted

SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


class AbsencePoster(commands.Cog):
    """
    Sammelt neue Abwesenheiten aus utils/absences.json (posted == False),
    postet sie als Embed in den in settings.json konfigurierten Channel
    und markiert danach 'posted': True, damit nichts doppelt gesendet wird.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_new_absences.start()

    def cog_unload(self):
        self.check_new_absences.cancel()

    @tasks.loop(seconds=30)
    async def check_new_absences(self):
        settings = load_settings()
        channel_id = int(settings.get("absence_channel_id") or 0)
        if not channel_id:
            return  # kein Ziel konfiguriert

        channel: Optional[discord.TextChannel] = self.bot.get_channel(channel_id)
        if channel is None:
            # versuche lazy fetch
            try:
                channel = await self.bot.fetch_channel(channel_id)  # type: ignore
            except Exception:
                return

        # Hol ungesendete Einträge
        pending = [it for it in list_absences() if not it.get("posted")]
        if not pending:
            return

        for item in reversed(pending):  # älteste zuerst posten
            try:
                embed = discord.Embed(
                    title="📢 Abwesenheitsmeldung",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Mitglied", value=item.get("user_display") or "—", inline=False)
                embed.add_field(name="Zeitraum", value=f"{item.get('start_date','?')} bis {item.get('end_date','?')}", inline=False)
                reason = item.get("reason") or "—"
                if len(reason) > 1024:
                    reason = reason[:1021] + "..."
                embed.add_field(name="Grund", value=reason, inline=False)
                submitted_by = item.get("submitted_by") or "Web-Panel"
                embed.set_footer(text=f"Eingereicht von: {submitted_by}")

                msg = await channel.send(embed=embed)
                mark_posted(item["id"], channel_id=channel.id, message_id=msg.id)
            except Exception as e:
                # Optional: Logging erweitern
                print(f"[AbsencePoster] Fehler beim Posten: {e}")

    @check_new_absences.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(AbsencePoster(bot))
