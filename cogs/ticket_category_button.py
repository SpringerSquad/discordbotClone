import discord
from discord.ext import commands
from discord.ui import View, Select
import os, json
from datetime import datetime

from utils.ticket_claim_close import TicketActionView
from utils.ticket_log import log_ticket_create

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "../config.json")
TICKET_COUNTER_PATH = os.path.join(BASE_DIR, "../ticket_counter.txt")
TICKET_DIR = os.path.join(BASE_DIR, "../tickets")


class CategorySelect(discord.ui.Select):
    def __init__(self, categories):
        options = [discord.SelectOption(label=cat, value=cat) for cat in categories]
        super().__init__(
            placeholder="Wähle eine Kategorie...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_message(
            f"✅ Kategorie **{selected}** gewählt. Ticket wird erstellt …",
            ephemeral=True
        )

        # Config & Begrüßung
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        greeting = config.get("default_greeting", "Willkommen im Ticket!")

        # Ticketnummer
        if os.path.exists(TICKET_COUNTER_PATH):
            with open(TICKET_COUNTER_PATH, "r") as f:
                counter = int(f.read())
        else:
            counter = 1
        counter += 1
        with open(TICKET_COUNTER_PATH, "w") as f:
            f.write(str(counter))

        # Channelname
        username = interaction.user.name.lower().replace(" ", "-")
        ticket_name = f"ticket-{selected.lower()}-{counter}"[:32]

        # Rechte
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        # Channel erstellen
        channel = await interaction.guild.create_text_channel(
            name=ticket_name,
            overwrites=overwrites,
            reason=f"Ticket von {interaction.user} ({selected})"
        )

        # Logging
        log_ticket_create(channel.name, interaction.user.id, channel.id, interaction.user.display_name)

        # Begrüßung + Buttons senden
        await channel.send(
            f"{interaction.user.mention}\n**Kategorie:** {selected}\n{greeting}",
            view=TicketActionView(interaction.user)
        )

        # Ticket speichern
        os.makedirs(TICKET_DIR, exist_ok=True)
        ticket_data = {
            "id": counter,
            "user": str(interaction.user),
            "user_id": interaction.user.id,
            "status": "offen",
            "category": selected,
            "created": datetime.utcnow().isoformat(),
            "channel_id": channel.id
        }
        ticket_file = os.path.join(TICKET_DIR, f"{counter}_{username}.json")
        with open(ticket_file, "w", encoding="utf-8") as f:
            json.dump(ticket_data, f, indent=4)


class CategoryTicketView(View):
    def __init__(self, categories):
        super().__init__(timeout=60)
        self.add_item(CategorySelect(categories))


class CategoryTicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def kategorie(self, ctx):
        """Starte Ticketerstellung mit Kategorie-Auswahl + Button-Logik"""
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        categories = config.get("ticket_categories", ["Allgemein"])
        view = CategoryTicketView(categories)
        await ctx.send("Bitte wähle eine Kategorie für dein Ticket:", view=view)


async def setup(bot):
    await bot.add_cog(CategoryTicketCog(bot))
