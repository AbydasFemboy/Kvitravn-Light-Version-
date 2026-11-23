"""Mod-Team-Dashboard: /modlog (Shadow Ledger), /modreview (Übersicht),
/whisperlist @user, /whisper."""
import time
from collections import Counter

import discord
from discord import app_commands

import data, locales


def _leader_display(bot, guild, uid):
    try:
        m = guild.get_member(int(uid))
        if m is not None:
            return str(m)
    except Exception:
        pass
    return f"<@{uid}>"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
async def _cmd_modlog(interaction: discord.Interaction):
    if not any(r.name in ("Moderation", "Admin") for r in interaction.user.roles):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    entries = data.load("modlog", [])[:20]
    if not entries:
        await interaction.response.send_message(locales.t(interaction.user.id, "modlog_empty"), ephemeral=True)
        return
    emb = discord.Embed(title=locales.t(interaction.user.id, "modlog_title"), color=0x7289DA)
    lines = [locales.t(interaction.user.id, "modlog_line", time=e["time"], action=e["action"],
                       target=e["target"], reason=e["reason"], mod=e["mod"])
             for e in entries]
    emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)


async def _cmd_modreview(interaction: discord.Interaction):
    bot = interaction.client
    guild = interaction.guild
    if not any(r.name in ("Moderation", "Admin", "Owner") for r in interaction.user.roles):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    emb = discord.Embed(title=locales.t(interaction.user.id, "modreview_title"), color=0x7289DA)
    # ▪️ Top-Verstöße
    warns = data.load("warns", {})
    top = sorted(((uid, len(v)) for uid, v in warns.items() if v), key=lambda kv: (-kv[1], kv[0]))[:5]
    if top:
        lines = [locales.t(interaction.user.id, "modreview_top_line", n=i + 1,
                           user=_leader_display(bot, guild, uid), count=c)
                 for i, (uid, c) in enumerate(top)]
        emb.add_field(name=locales.t(interaction.user.id, "modreview_top"), value="\n".join(lines), inline=False)
    # ▪️ Banns (letzte 10)
    try:
        bans = []
        async for a in guild.audit_logs(limit=10, action=discord.AuditLogAction.ban):
            bans.append(locales.t(interaction.user.id, "modreview_ban_line", user=a.target, mod=a.user,
                                  date=data.fmt_time(a.created_at.timestamp())))
        if bans:
            emb.add_field(name=locales.t(interaction.user.id, "modreview_bans"), value="\n".join(bans), inline=False)
    except discord.HTTPException:
        pass
    # ▪️ Reporter (meist gemeldet)
    reports = data.load("reports", [])
    cnt = Counter(r["user_id"] for r in reports)
    top_rep = cnt.most_common(5)
    if top_rep:
        lines = [locales.t(interaction.user.id, "modreview_report_line", n=i + 1,
                           user=_leader_display(bot, guild, uid), count=c)
                 for i, (uid, c) in enumerate(top_rep)]
        emb.add_field(name=locales.t(interaction.user.id, "modreview_reporters"), value="\n".join(lines), inline=False)
    # ▪️ Whisper
    whisper = data.load("whisper", {})
    n = sum(len(v) for v in whisper.values())
    if n:
        emb.add_field(name=locales.t(interaction.user.id, "modreview_whisper"), value=f"{n} Notizen", inline=False)
    if emb.fields:
        await interaction.response.send_message(embed=emb)
    else:
        emb.description = "Keine Daten."
        await interaction.response.send_message(embed=emb)


@app_commands.describe(user="Zielnutzer")
async def _cmd_whisperlist(interaction: discord.Interaction, user: discord.Member):
    if not any(r.name in ("Moderation", "Admin", "Owner") for r in interaction.user.roles):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    whisper = data.load("whisper", {})
    notes = whisper.get(str(user.id), [])
    if not notes:
        await interaction.response.send_message(locales.t(interaction.user.id, "whisper_none", user=user), ephemeral=True)
        return
    emb = discord.Embed(title=locales.t(interaction.user.id, "whisper_title", user=user), color=0x2B2D42)
    lines = [locales.t(interaction.user.id, "whisper_line", time=data.fmt_time(n["time"]), text=n["text"])
             for n in notes[-20:]]
    emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)


@app_commands.describe(user="Zielnutzer", text="Whisper-Notiz")
async def _cmd_whisper(interaction: discord.Interaction, user: discord.Member, text: str):
    if not any(r.name in ("Moderation", "Admin", "Owner") for r in interaction.user.roles):
        await interaction.response.send_message(locales.t(interaction.user.id, "no_permission"), ephemeral=True)
        return
    whisper = data.load("whisper", {})
    whisper.setdefault(str(user.id), []).append({"time": time.time(), "text": text})
    data.save("whisper", whisper)
    await interaction.response.send_message(locales.t(interaction.user.id, "whisper_ok", user=user, text=text))


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------
def register(bot):
    cmds = [
        ("modlog", "Shadow Ledger anzeigen (letzte 20)", _cmd_modlog),
        ("modreview", "Moderationsübersicht: Top-Verstöße, Banns, Reporter, Whisper", _cmd_modreview),
        ("whisperlist", "Whisper-Archiv eines Nutzers anzeigen", _cmd_whisperlist),
        ("whisper", "Whisper-Notiz für Nutzer erstellen", _cmd_whisper),
    ]
    for name, desc, func in cmds:
        bot.tree.add_command(app_commands.command(name=name, description=desc)(func))
