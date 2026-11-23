"""Tickets-System: #ticket-panel mit Buttons, Private-Kanäle (Moderation+Admin sichtbar,
User sichtbar), 18+-Verifizierung mit /verify18."""
import discord
from discord import app_commands

import data, locales


def _data():
    return data.load("tickets", {"open": {}, "verified": []})


def _save(d):
    data.save("tickets", d)


class TicketPanelView(discord.ui.View):
    def __init__(self, timeout=None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="🎟️ Support-Ticket erstellen", style=discord.ButtonStyle.success, custom_id="tickets_create")
    async def _create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction)


async def setup(bot, guild):
    """Erstellt (falls nicht vorhanden) den #ticket-panel und postet das Panel."""
    ch_id = bot.config.get("ticket_panel_channel_id")
    ch = guild.get_channel(ch_id) if ch_id else None
    if ch is None:
        ch = await guild.create_text_channel("ticket-panel", reason="Ticket-Panel erstellt")
        bot.config["ticket_panel_channel_id"] = ch.id
        bot.save_config()
    emb = discord.Embed(title="🎟️ Support-Ticket",
                        description=locales.t(None, "ticket_panel_title"))
    emb.color = 0x2B2D42
    await ch.send(embed=emb, view=TicketPanelView())


async def create_ticket(interaction: discord.Interaction):
    bot = interaction.client
    user = interaction.user
    guild = interaction.guild
    d = _data()
    uid = str(user.id)
    if uid in d["open"]:
        ch = guild.get_channel(d["open"][uid])
        if ch:
            await interaction.response.send_message(locales.t(user.id, "ticket_exists", channel=ch.mention), ephemeral=True)
            return
        d["open"].pop(uid, None)
        _save(d)
    # Kategorie 'kvitravn-support-tickets'
    cat_name = bot.config.get("ticket_category", "kvitravn-support-tickets")
    cat = next((c for c in guild.categories if c.name == cat_name), None)
    if cat is None:
        try:
            cat = await guild.create_category(cat_name, reason="Ticket-Kategorie erstellt")
        except discord.HTTPException:
            cat = None
    channel = await guild.create_text_channel(
        f"ticket-{uid}-{user.display_name[:20].lower()}", category=cat, topic="Support-Ticket")
    # Berechtigungen: Moderation/Admin/Owner sichtbar+schreibbar, User sichtbar, alles andere schreibgeschützt
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    for name in ("Moderation", "Admin", "Owner"):
        r = next((r for r in guild.roles if r.name == name), None)
        if r is not None:
            overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    try:
        await channel.edit(overwrites=overwrites)
    except discord.HTTPException:
        pass
    try:
        await user.move_to(channel)
    except discord.HTTPException:
        pass
    d["open"][uid] = channel.id
    _save(d)
    await interaction.response.send_message(locales.t(user.id, "ticket_created", channel=channel.mention), ephemeral=True)
    mods = [r.mention for r in guild.roles if r.name in ("Moderation", "Admin", "Owner")]
    await channel.send(locales.t(user.id, "ticket_notify", user=user, mods=" ".join(mods) if mods else "(keine)"))


async def _cmd_verify18(interaction: discord.Interaction):
    bot = interaction.client
    user = interaction.user
    if interaction.guild is None:
        await interaction.response.send_message("❌ Nur im Server möglich.", ephemeral=True)
        return
    role_name = bot.config.get("nsfw_role", "Verified 18+")
    role = next((r for r in interaction.guild.roles if r.name == role_name), None)
    if role is None:
        try:
            role = await interaction.guild.create_role(name=role_name, reason="Rolle '18+' erstellt")
        except discord.HTTPException:
            role = None
    if role is not None and role in user.roles:
        await interaction.response.send_message(locales.t(user.id, "verify_already"), ephemeral=True)
        return
    if role is not None:
        try:
            await user.add_role(role, reason="Verifiziert 18+")
        except discord.HTTPException:
            pass
        d = _data()
        if user.id not in d["verified"]:
            d["verified"].append(user.id)
            _save(d)
    await interaction.response.send_message(locales.t(user.id, "verify_ok"), ephemeral=True)


def register(bot):
    bot.tree.add_command(app_commands.command(name="verify18", description="18+-Verifizierung (Rollenaufgabe)")(_cmd_verify18))
