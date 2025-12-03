import re
import discord
from discord.ui import View, Button, Modal, TextInput
from utils.ticket_log import (
    log_ticket_create,
    log_ticket_close,
    log_ticket_reopen,
    update_ticket_status
)
from utils.ticket_storage import set_ticket_status_by_channel


class CloseModal(Modal):
    def __init__(self, opener: discord.Member, parent_view: View):
        super().__init__(title="Grund für Schließung")
        self.opener = opener
        self.parent_view = parent_view
        self.ticket_id = parent_view.ticket_id
        self.channel = parent_view.channel

        self.reason = TextInput(
            label="Schließungs-Grund",
            style=discord.TextStyle.paragraph,
            placeholder="Bitte gib hier den Grund ein …",
            required=True,
            max_length=200
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user != self.opener:
            return await interaction.response.send_message(
                "❌ Nur der Ersteller kann das Ticket schließen.", ephemeral=True
            )

        old_name = self.channel.name
        new_name = f"geschlossen-{old_name}"
        await self.channel.edit(name=new_name, sync_permissions=True)

        update_ticket_status(self.ticket_id, "geschlossen")
        set_ticket_status_by_channel(self.channel.id, "geschlossen")
        log_ticket_close(old_name, interaction.user.id, self.channel.id)

        await interaction.response.send_message("✅ Ticket geschlossen.", ephemeral=True)
        await interaction.followup.send(
            f"🔒 Ticket wurde von **{interaction.user.display_name}** geschlossen.\n"
            f"💬 Grund: {self.reason.value}"
        )

        # Buttons live updaten
        for child in self.parent_view.children:
            if child.custom_id in ("ticket_claim", "ticket_close"):
                child.disabled = True
            if child.custom_id == "ticket_reopen":
                child.disabled = False

        if getattr(self.parent_view, "message", None):
            await self.parent_view.message.edit(view=self.parent_view)


class ReopenModal(Modal):
    def __init__(self, opener: discord.Member, parent_view: View):
        super().__init__(title="Grund für Wiederöffnung")
        self.opener = opener
        self.parent_view = parent_view
        self.ticket_id = parent_view.ticket_id
        self.channel = parent_view.channel

        self.reason = TextInput(
            label="Wiederöffnungs-Grund",
            style=discord.TextStyle.paragraph,
            placeholder="Bitte gib hier den Grund ein …",
            required=True,
            max_length=200
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user != self.opener:
            return await interaction.response.send_message(
                "❌ Nur der Ersteller kann das Ticket wieder öffnen.", ephemeral=True
            )

        old_name = self.channel.name
        new_name = old_name.replace("geschlossen-", "")
        await self.channel.edit(name=new_name, sync_permissions=True)

        update_ticket_status(self.ticket_id, "offen")
        set_ticket_status_by_channel(self.channel.id, "offen")
        log_ticket_reopen(old_name, interaction.user.id, self.channel.id)

        await interaction.response.send_message("✅ Ticket wieder geöffnet.", ephemeral=True)
        await interaction.followup.send(
            f"♻️ Ticket wurde von **{interaction.user.display_name}** wieder geöffnet.\n"
            f"💬 Grund: {self.reason.value}"
        )

        for child in self.parent_view.children:
            if child.custom_id == "ticket_reopen":
                child.disabled = True
            if child.custom_id in ("ticket_claim", "ticket_close"):
                child.disabled = False

        if getattr(self.parent_view, "message", None):
            await self.parent_view.message.edit(view=self.parent_view)


class TicketActionView(View):
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener
        self.ticket_id: str | None = None
        self.channel: discord.TextChannel | None = None
        self.message: discord.Message | None = None

    @discord.ui.button(
        label="Übernehmen",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_claim"
    )
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        self.channel = interaction.channel  # type: ignore
        m = re.search(r"(?:geschlossen-)?ticket-[\w-]+-(\d+)", self.channel.name)
        self.ticket_id = m.group(1) if m else None

        # Claim direkt ausführen
        log_ticket_create(
            self.channel.name,
            interaction.user.id,
            self.channel.id,
            interaction.user.display_name
        )

        status = f"Geclaimt von {interaction.user.display_name}"
        set_ticket_status_by_channel(self.channel.id, status)

        await interaction.response.send_message("✅ Ticket übernommen.", ephemeral=True)
        await interaction.followup.send(
            f"🛡️ Ticket wurde übernommen von **{interaction.user.display_name}**"
        )

        # Buttons in dieser View deaktivieren
        for child in self.children:
            if child.custom_id == "ticket_claim":
                child.disabled = True

        if getattr(self, "message", None):
            await self.message.edit(view=self)

    @discord.ui.button(
        label="Schließen",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close"
    )
    async def close_button(self, interaction: discord.Interaction, button: Button):
        self.channel = interaction.channel  # type: ignore
        m = re.search(r"(?:geschlossen-)?ticket-[\w-]+-(\d+)", self.channel.name)
        self.ticket_id = m.group(1) if m else None
        await interaction.response.send_modal(CloseModal(self.opener, self))

    @discord.ui.button(
        label="Wieder öffnen",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_reopen",
        disabled=True
    )
    async def reopen_button(self, interaction: discord.Interaction, button: Button):
        self.channel = interaction.channel  # type: ignore
        m = re.search(r"(?:geschlossen-)?ticket-[\w-]+-(\d+)", self.channel.name)
        self.ticket_id = m.group(1) if m else None
        await interaction.response.send_modal(ReopenModal(self.opener, self))
