"""Moderations-Befehle (Timeout/Mute/Purge/Slowmode/Rolle/Warn/Report/...), Warn-Eskalation
(3→10Min, 5→60Min, 7→24h), Shadow Ledger (modlog.json) und den Spam/Mention/Invite-Blocker."""
import hashlib
import re
import time
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands

import data, locales

MOD_NAMES = ["Moderation", "Admin", "Owner"]
ADMIN_NAMES = ["Admin", "Owner"]

INVITE_RE = re.compile(r"discord\.(?:gg|com/invite|com/jo[i]n)/[A-Za-z0-9-]+")


def role_by_name(bot, guild, name):
    for r in guild.roles:
        if r.name == name:
            return r
    return None


def user_allowed(user, names):
    return any(r.name in names for r in user.roles)


# ---------------------------------------------------------------------------
# Shadow Ledger (Mod-Log)
# ---------------------------------------------------------------------------
async def log_ledger(bot, action, target=None, mod=None, reason="", channel=None):
    """Appends an entry to the Shadow Ledger and posts it to the mod-log channel."""
    entry = {
        "time": data.fmt_time(time.time()),
        "action": action,
        "target": str(target) if target else "",
        "mod": str(mod) if mod else "",
        "reason": reason or "",
        "channel": str(channel) if channel else "",
    }
    entries = data.load("modlog", [])
    entries.insert(0, entry)
    data.save("modlog", entries[:50])
    ch_id = bot.config.get("modlog_channel_id")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            try:
                line = locales.t(0, "modlog_line", time=entry["time"], action=action,
                                 target=entry["target"], reason=entry["reason"], mod=entry["mod"])
                await ch.send(embed=discord.Embed(description=line, color=0x7289DA))
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# Warn-System mit Eskalations-Timeout
# ---------------------------------------------------------------------------
async def warn_user(bot, user, reason, mod=None):
    """Warns a user; at counts 3/5/7 applies escalating timeouts (10m/60m/24h).

    Returns (total_warns, escalation_minutes_or_None, escalation_text)."""
    warns = data.load("warns", {})
    lst = warns.setdefault(str(user.id), [])
    lst.append({"time": time.time(), "reason": reason, "mod": str(mod) if mod else ""})
    warns[str(user.id)] = lst
    data.save("warns", warns)
    total = len(lst)
    minutes = None
    if total >= 7:
        minutes = 24 * 60
    elif total >= 5:
        minutes = 60
    elif total >= 3:
        minutes = 10
    if minutes and user.guild is not None:
        try:
            await user.timeout(timedelta(minutes=minutes), reason=f"Escalation (Warn #{total})")
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass
    note = locales.t(user.id, "warn_escalation", n=total, min=minutes) if minutes else ""
    return total, minutes, note


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@app_commands.describe(user="Zielnutzer", minutes="Dauer in Minuten (1–40320)")
async def _cmd_timeout(interaction: discord.Interaction, user: discord.Member, minutes: int):
    bot = interaction.client
    if not user_allowed(interaction.user, MOD_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    if not bot.rate_ok(interaction.user, "timeout"):
        await interaction.response.send_message(locales.t(interaction.user.id, "throttled"), ephemeral=True)
        return
    if minutes < 1 or minutes > 40320:
        await interaction.response.send_message(locales.t(interaction.user.id, "timeout_range"), ephemeral=True)
        return
    try:
        await user.timeout(timedelta(minutes=minutes), reason=f"Timeout ({minutes} Min.)")
    except discord.HTTPException:
        await interaction.response.send_message("❌ Timeout konnte nicht gesetzt werden.", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "timeout_ok", user=user, minutes=minutes))
    await log_ledger(bot, "Timeout", user, interaction.user, f"{minutes} Min.", channel=interaction.channel)


@app_commands.describe(user="Zielnutzer")
async def _cmd_mute(interaction: discord.Interaction, user: discord.Member):
    if not user_allowed(interaction.user, MOD_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    try:
        await user.edit(mute=True, reason="/mute")
    except discord.HTTPException:
        await interaction.response.send_message("❌ Mute fehlgeschlagen.", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "mute_ok", user=user))
    await log_ledger(interaction.client, "Mute", user, interaction.user, "/mute", channel=interaction.channel)


@app_commands.describe(count="Anzahl Nachrichten (1–200)")
async def _cmd_purge(interaction: discord.Interaction, count: app_commands.Range[int, 1, 200]):
    if not user_allowed(interaction.user, MOD_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    ch = interaction.channel
    if not isinstance(ch, discord.TextChannel):
        await interaction.response.send_message("❌ Nur in Text-Channels möglich.", ephemeral=True)
        return
    try:
        deleted = await ch.purge(limit=count, reason="/purge")
    except discord.Forbidden:
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    except discord.HTTPException:
        await interaction.response.send_message("❌ Purge fehlgeschlagen.", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "purge_ok", count=len(deleted)))


@app_commands.describe(channel="Zielkanal", seconds="Slowmode in Sekunden (0–21600)")
async def _cmd_slowmode(interaction: discord.Interaction, channel: discord.TextChannel, seconds: app_commands.Range[int, 0, 21600]):
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    try:
        await channel.edit(slowmode_delay=seconds, reason="/slowmode")
    except discord.HTTPException:
        await interaction.response.send_message("❌ Slowmode konnte nicht gesetzt werden.", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "slowmode_ok", seconds=seconds))


async def _cmd_restrict_all(interaction: discord.Interaction):
    bot = interaction.client
    guild = interaction.guild
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    role_name = bot.config.get("restricted_role", "Restricted")
    role = role_by_name(bot, guild, role_name)
    if role is None:
        try:
            role = await guild.create_role(name=role_name, reason="Restricted-Rolle erstellt")
        except discord.HTTPException:
            await interaction.response.send_message("❌ Rolle konnte nicht erstellt werden.", ephemeral=True)
            return
    for member in list(guild.members):
        if role in member.roles:
            continue
        try:
            await member.add_role(role, reason="Restricted-Rolle verteilt")
        except (discord.Forbidden, discord.HTTPException):
            pass
    await interaction.response.send_message(locales.t(interaction.user.id, "restrict_all_ok", role=role.name))
    await log_ledger(bot, "Restrict-All", None, interaction.user, f"Rolle '{role.name}' an alle verteilt", channel=interaction.channel)


@app_commands.describe(user="Zielnutzer", add="Rollen zum Verleihen (kommasepariert)", remove="Rollen zum Entziehen (kommasepariert)")
async def _cmd_rolle(interaction: discord.Interaction, user: discord.Member,
                     add: Optional[str] = None, remove: Optional[str] = None):
    bot = interaction.client
    guild = interaction.guild
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    granted, removed, missing = [], [], []
    if add:
        for name in [n.strip() for n in add.split(",") if n.strip()]:
            r = role_by_name(bot, guild, name)
            if r is None:
                missing.append(name)
                continue
            try:
                await user.add_role(r, reason=f"Rolle vergeben: {r.name}")
            except (discord.Forbidden, discord.HTTPException):
                missing.append(name)
            else:
                granted.append(r.name)
    if remove:
        for name in [n.strip() for n in remove.split(",") if n.strip()]:
            r = role_by_name(bot, guild, name)
            if r is None:
                missing.append(name)
                continue
            try:
                await user.remove_role(r, reason=f"Rolle entfernt: {r.name}")
            except (discord.Forbidden, discord.HTTPException):
                missing.append(name)
            else:
                removed.append(r.name)
    if not granted and not removed:
        await interaction.response.send_message(locales.t(interaction.user.id, "rolle_none"), ephemeral=True)
        return
    msg = ""
    if granted:
        msg += locales.t(interaction.user.id, "rolle_granted", user=user, roles=", ".join(granted))
    if removed:
        msg += locales.t(interaction.user.id, "rolle_removed", user=user, roles=", ".join(removed))
    if missing:
        msg += f" (Nicht gefunden: {', '.join(missing)})"
    await interaction.response.send_message(msg)
    await log_ledger(bot, "Rolle", user, interaction.user, msg.replace("\n", " "), channel=interaction.channel)


@app_commands.describe(role="Name der Rolle, die gelöscht werden soll")
async def _cmd_rolle_loeschen(interaction: discord.Interaction, role: str):
    bot = interaction.client
    guild = interaction.guild
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    r = role_by_name(bot, guild, role)
    if r is None:
        await interaction.response.send_message(locales.t(interaction.user.id, "rolle_loeschen_notfound", role=role), ephemeral=True)
        return
    if r == guild.default_role:
        await interaction.response.send_message(locales.t(interaction.user.id, "rolle_loeschen_default"), ephemeral=True)
        return
    try:
        await r.delete(reason="/rolle_loeschen")
    except discord.HTTPException as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "rolle_loeschen_ok", role=role))
    await log_ledger(bot, "Rolle gelöscht", None, interaction.user, f"Rolle '{role}' gelöscht", channel=interaction.channel)


@app_commands.describe(user="Zielnutzer", reason="Vergründung / Begründung")
async def _cmd_warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    bot = interaction.client
    if not user_allowed(interaction.user, MOD_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    total, minutes, note = await warn_user(bot, user, reason, mod=interaction.user)
    text = locales.t(interaction.user.id, "warn_ok", user=user, reason=reason) + note
    await interaction.response.send_message(text)
    await log_ledger(bot, "Warn", user, interaction.user, reason + note, channel=interaction.channel)


@app_commands.describe(user="Zielnutzer")
async def _cmd_warns(interaction: discord.Interaction, user: discord.Member):
    if not user_allowed(interaction.user, MOD_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    warns = data.load("warns", {})
    lst = warns.get(str(user.id), [])
    if not lst:
        await interaction.response.send_message(locales.t(interaction.user.id, "warn_none", user=user), ephemeral=True)
        return
    lines = [locales.t(interaction.user.id, "warn_line", time=data.fmt_time(w["time"]),
                       reason=w["reason"], mod=w["mod"] or "?", extra="")
             for w in lst[-20:]]
    emb = discord.Embed(title=locales.t(interaction.user.id, "warn_count"), color=0xF1C40F)
    emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)


@app_commands.describe(user="Zielnutzer")
async def _cmd_unwarn(interaction: discord.Interaction, user: discord.Member):
    bot = interaction.client
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    warns = data.load("warns", {})
    lst = warns.get(str(user.id), [])
    if not lst:
        await interaction.response.send_message(locales.t(interaction.user.id, "unwarn_none", user=user), ephemeral=True)
        return
    w = lst.pop()
    warns[str(user.id)] = lst
    data.save("warns", warns)
    await interaction.response.send_message(locales.t(interaction.user.id, "unwarn_ok", user=user))
    await log_ledger(bot, "Unwarn", user, interaction.user, f"Verwarnung ({w['reason']}) entfernt", channel=interaction.channel)


# ---------------------------------------------------------------------------
# Report (an das Mod-Team)
# ---------------------------------------------------------------------------
@app_commands.describe(reason="Was soll gemeldet werden?")
async def _cmd_report(interaction: discord.Interaction, reason: str):
    bot = interaction.client
    if not bot.rate_ok(interaction.user, "report"):
        await interaction.response.send_message(locales.t(interaction.user.id, "throttled"), ephemeral=True)
        return
    reports = data.load("reports", [])
    reports.append({"time": time.time(), "user_id": str(interaction.user.id), "reason": reason})
    data.save("reports", reports[-100:])
    ch_id = bot.config.get("report_channel_id")
    ch = interaction.guild.get_channel(ch_id) if (ch_id and interaction.guild) else None
    if isinstance(ch, discord.TextChannel):
        await ch.send(locales.t(interaction.user.id, "report_sent", user=interaction.user, reason=reason, channel=ch.mention))
    else:
        await interaction.response.send_message(locales.t(interaction.user.id, "report_ok", reason=reason))


# ---------------------------------------------------------------------------
# Alias-Manager
# ---------------------------------------------------------------------------
ALIAS_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


@app_commands.describe(alias="Neuer Alias-Name", command="Zielbefehl (mit oder ohne /)")
async def _cmd_alias(interaction: discord.Interaction, alias: str, command: str):
    bot = interaction.client
    if not user_allowed(interaction.user, ADMIN_NAMES):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    alias = alias.strip().lstrip("/")
    command = command.strip().lstrip("/")
    if not ALIAS_RE.match(alias):
        await interaction.response.send_message(locales.t(interaction.user.id, "alias_invalid", alias=alias), ephemeral=True)
        return
    if bot.tree.get_command(command) is None:
        await interaction.response.send_message(locales.t(interaction.user.id, "alias_unknown_command", command=command), ephemeral=True)
        return
    aliases = data.load("aliases", {})
    aliases[alias] = command
    data.save("aliases", aliases)
    register_aliases(bot)
    await interaction.response.send_message(locales.t(interaction.user.id, "alias_set", alias=alias, command=command))


def register_aliases(bot):
    """Erstellt Slash-Command-Aliase aus data/aliases.json (alias -> target)."""
    aliases = data.load("aliases", {})
    for alias, target in aliases.items():
        if not ALIAS_RE.match(alias):
            continue
        if bot.tree.get_command(alias) is not None:
            continue
        cmd = bot.tree.get_command(target)
        if cmd is None:
            continue
        try:
            new_cmd = app_commands.command(name=alias, description=f"Alias für /{target}")(cmd.callback)
            bot.tree.add_command(new_cmd)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# AutoMod (Spam-Blocker, Mention-Flut-Blocker, Invite-Link-Blocker)
# ---------------------------------------------------------------------------
async def automod_on_message(bot, message):
    """Wird bei jeder Bot-Nachricht (automod) aufgerufen: deletes + warns für Probleme."""
    if not message.guild or message.author.bot or not message.content:
        return
    # 1) Invite-Link-Blocker (24h-Timeout)
    if INVITE_RE.search(message.content):
        try:
            await message.delete(reason="Invite-Link-Blocker")
        except discord.HTTPException:
            pass
        try:
            await message.author.timeout(timedelta(hours=24), reason="Invite-Link-Blocker")
        except (discord.Forbidden, discord.HTTPException):
            pass
        await warn_user(bot, message.author, "Invite-Link gepostet")
        await log_ledger(bot, "Invite-Blocker", message.author, None, "Invite-Link gepostet (24h-Timeout)", channel=message.channel)
        return
    # 2) Mention-Flut-Blocker (>8 Mentions)
    mentions = message.mentions + message.role_mentions
    if len(mentions) > 8:
        try:
            await message.delete(reason="Mention-Flut-Blocker")
        except discord.HTTPException:
            pass
        await warn_user(bot, message.author, f"Mention-Flut ({len(mentions)} Mentions)")
        await log_ledger(bot, "Mention-Blocker", message.author, None, "Mention-Flut blocking", channel=message.channel)
    # 3) Spam-Blocker (identische Messages, ≥3 in 15s / repeated chars)
    hist = data.load("automod", {})
    uid = str(message.author.id)
    now = time.time()
    entries = [e for e in hist.get(uid, []) if now - e[0] < 15]
    digest = hashlib.md5(message.content.encode("utf-8", "ignore")).hexdigest()
    entries.append([now, digest])
    hist[uid] = entries[-20:]
    data.save("automod", hist)
    same = sum(1 for e in entries if e[1] == digest)
    if same >= 3:
        try:
            await message.delete(reason="Spam-Blocker")
        except discord.HTTPException:
            pass
        await warn_user(bot, message.author, "Spam (identische Messages 3× in 15s)")
        await log_ledger(bot, "Spam-Blocker", message.author, None, "Spam: identische Messages 3× in 15s", channel=message.channel)
    if re.search(r"(.)\1{7,}", message.content):
        try:
            await message.delete(reason="Spam-Blocker (Wiederholungen)")
        except discord.HTTPException:
            pass
        await warn_user(bot, message.author, "Spam (Wiederholungen)")
        await log_ledger(bot, "Spam-Blocker", message.author, None, "Spam: Wiederholungen", channel=message.channel)


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------
def register(bot):
    cmds = [
        ("timeout", "Temporärer Timeout (1 Min – 28 Tage)", _cmd_timeout),
        ("mute", "Kanal-spezifische Stummschaltung (send_messages=False)", _cmd_mute),
        ("purge", "Nachrichten löschen (1–200)", _cmd_purge),
        ("slowmode", "Slowmode für Kanal (0–21600 s)", _cmd_slowmode),
        ("restrict_all", "Restricted-Rolle an alle verteilen", _cmd_restrict_all),
        ("rolle", "Rollen vergeben/entziehen", _cmd_rolle),
        ("rolle_loeschen", "Serverrolle endgültig löschen", _cmd_rolle_loeschen),
        ("warn", "Verwarnung mit Eskalation (3→10Min, 5→60Min, 7→24h)", _cmd_warn),
        ("warns", "Verwarnungen anzeigen", _cmd_warns),
        ("unwarn", "Letzte Verwarnung entfernen", _cmd_unwarn),
        ("report", "Meldung an Mod-Team", _cmd_report),
        ("alias", "Alias für Befehle verwalten", _cmd_alias),
    ]
    for name, desc, func in cmds:
        bot.tree.add_command(app_commands.command(name=name, description=desc)(func))
