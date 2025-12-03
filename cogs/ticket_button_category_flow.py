# cogs/ticket_button_category_flow.py
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
from discord.utils import get
import json
from datetime import datetime

from utils.ticket_counter import get_next_ticket_number
from utils.ticket_storage import save_ticket
from utils.ticket_log import log_ticket_event
from utils.ticket_claim_close import TicketActionView  # ✅ Richtige View für Buttons
from database import SessionLocal
from models import User, RoleEnum

SETTINGS_FILE = "settings.json"
CONFIG_FILE = "config.json"


# ---------------------------
# Helpers: Settings / Config
# ---------------------------
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ---------------------------
# Helpers: ID-Konvertierung
# ---------------------------
def _to_int_or_none(value):
    """
    Konvertiert eine beliebige Eingabe robust zu int oder gibt None zurück.
    Ignoriert None, leere Strings und nicht-numerische Strings.
    """
    try:
        s = str(value).strip()
        if not s or not s.isdigit():
            return None
        return int(s)
    except Exception:
        return None


def _fetch_user_ids_by_role(session, role_enum_value):
    """
    Holt alle User.discord_id für eine bestimmte Rolle aus der DB
    und gibt eine Liste gültiger ints zurück (robust gegen '', None, 'abc').
    """
    users = (
        session.query(User)
        .filter(User.discord_id.isnot(None), User.role == role_enum_value)
        .all()
    )
    # Manche DB-Einträge können "" enthalten – das fangen wir hier sicher ab:
    return [i for i in (_to_int_or_none(u.discord_id) for u in users) if i is not None]


# ---------------------------
# Discord UI-Elemente
# ---------------------------
class CategoryDropdown(discord.ui.Select):
    def __init__(self):
        settings = load_settings()
        categories = settings.get("ticket_categories", ["Support", "Technik"])
        options = [discord.SelectOption(label=cat, value=cat) for cat in categories]

        super().__init__(
            placeholder="📂 Wähle eine Support Ticket-Kategorie...",
            options=options,
            custom_id="category_dropdown",
        )

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        settings = load_settings()
        guild = interaction.guild

        # Basis-Kanalrechte
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
        }

        # Admin-/Support-Mitglieder aus DB lesen (robust)
        with SessionLocal() as session:
            admin_ids = _fetch_user_ids_by_role(session, RoleEnum.admin)
            support_ids = _fetch_user_ids_by_role(session, RoleEnum.support)

        # Admin-/Support-Mitglieder Sichtberechtigung geben
        for admin_id in admin_ids:
            member = guild.get_member(admin_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True, manage_messages=True
                )

        for supporter_id in support_ids:
            member = guild.get_member(supporter_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True)

        # Ticketnummer + Benutzername im Kanalnamen
        ticket_number = get_next_ticket_number()
        safe_username = interaction.user.name.replace(" ", "-").lower()
        channel_name = f"ticket-{safe_username}-{ticket_number}"

        # Kategorie-Ordner suchen (optional anlegen, falls nicht vorhanden)
        ticket_parent = discord.utils.get(guild.categories, name="🎫 Tickets")

        # Kanal erstellen
        channel = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=ticket_parent
        )

        # Ticket-Daten speichern
        created_at = datetime.utcnow().isoformat()
        ticket_data = {
            "ticket_id": ticket_number,
            "user": interaction.user.name,
            "user_id": interaction.user.id,
            "channel_id": channel.id,
            "channel_name": channel.name,
            "category": category_name,
            "status": "offen",
            "created_at": created_at,
        }
        save_ticket(ticket_data)

        # Private Bestätigung
        await interaction.response.send_message(
            f"✅ Dein Ticket wurde erstellt: {channel.mention}", ephemeral=True
        )

        # Begrüßungsnachricht + Buttons
        welcome = settings.get("welcome_text", "Willkommen im Support!")
        mention_user = interaction.user.mention

        embed = discord.Embed(
            title=f"🎫 Ticket – {category_name}",
            description=f"{welcome}\n\n📂 **Kategorie:** {category_name}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"Ticket-ID: {ticket_number}")

        # View initialisieren mit Ticketinfos
        view = TicketActionView(interaction.user)
        view.ticket_id = str(ticket_number)
        view.channel = channel

        msg = await channel.send(content=mention_user, embed=embed, view=view)
        # WICHTIG: View kennt ihre Message, damit spätere Button-Updates zuverlässig funktionieren
        view.message = msg

        # Logging
        log_ticket_event(
            "ticket_created",
            {
                "ticket_id": ticket_number,
                "user": interaction.user.name,
                "user_id": interaction.user.id,
                "category": category_name,
                "channel_id": channel.id,
                "created_at": created_at,
            },
        )


class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CategoryDropdown())


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="🎟 Support Ticket erstellen",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_create_button",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "📂 Bitte wähle eine Kategorie zu der du Support brauchst:", view=CategoryView(), ephemeral=True
        )


class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())


# ---------------------------
# Haupt-Cog
# ---------------------------
class TicketCategoryFlow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_panel_data = None
        self.update_panel.start()

    def cog_unload(self):
        self.update_panel.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        # Versuche Panel direkt zu setzen (falls Channel vorhanden)
        await self.ensure_panel_message()

    def build_panel_embed(self, guild: discord.Guild):
        """
        Baut das Panel-Embed inkl. Online-Zählung für Admins/Supporter.
        Gibt (embed, daten_dict) zurück.
        """
        settings = load_settings()

        # Admin-/Support-Mitglieder aus DB lesen (robust)
        with SessionLocal() as session:
            admin_ids = _fetch_user_ids_by_role(session, RoleEnum.admin)
            support_ids = _fetch_user_ids_by_role(session, RoleEnum.support)

        # Online-Zählung (Status != offline)
        admin_online = sum(
            1 for m in guild.members if m.id in admin_ids and m.status != discord.Status.offline
        )
        support_online = sum(
            1 for m in guild.members if m.id in support_ids and m.status != discord.Status.offline
        )

        welcome = settings.get("welcome_text", "Willkommen im Support!")

        embed = discord.Embed(description=welcome, color=discord.Color.blue())
        embed.add_field(name="🟢 Admins online", value=str(admin_online), inline=True)
        embed.add_field(name="🟢 Supporter online", value=str(support_online), inline=True)
        embed.set_footer(
            text=f"Aktualisiert am {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )

        data = {
            "welcome": welcome,
            "admin_online": admin_online,
            "support_online": support_online,
        }
        return embed, data

    async def ensure_panel_message(self):
        """
        Stellt sicher, dass im konfigurierten Panel-Channel eine Panel-Nachricht
        mit Button-View existiert und aktualisiert sie bei Änderungen.
        """
        config = load_config()
        channel_id = config.get("ticket_panel_channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        embed, current_data = self.build_panel_embed(channel.guild)

        # Nur aktualisieren, wenn sich Daten geändert haben (spart Edit-Events)
        if current_data != self.last_panel_data:
            self.last_panel_data = current_data

            # Versuche, bestehende Bot-Panel-Nachricht (mit Components) zu finden und zu aktualisieren
            async for msg in channel.history(limit=10):
                if msg.author == self.bot.user and len(msg.components) > 0:
                    await msg.edit(embed=embed, view=TicketButtonView())
                    return

            # Falls keine vorhandene Panel-Message gefunden wurde → neu senden
            await channel.send(embed=embed, view=TicketButtonView())

    @tasks.loop(seconds=60)
    async def update_panel(self):
        # Läuft im Hintergrund und aktualisiert das Panel zyklisch
        await self.ensure_panel_message()

    @update_panel.before_loop
    async def before_update_panel(self):
        # Sicherstellen, dass der Bot ready ist, bevor die Loop startet
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TicketCategoryFlow(bot))
