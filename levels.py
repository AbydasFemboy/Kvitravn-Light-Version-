"""Level- & XP-System: XP pro Nachricht/Voice, Meilensteine (Bronze→Legend), /level."""
import random
import time
from typing import Optional

import discord
from discord import app_commands

import data, locales

MILESTONES = [
    (5, "Bronze"), (10, "Silver"), (15, "Gold"), (20, "Platinum"),
    (25, "Verified"), (30, "Master"), (40, "Grandmaster"), (50, "Legend"),
]
MSG_COOLDOWN = 60.0   # min. Abstand pro Nachricht pro User
MSG_BASE = 15         # min. XP pro Nachricht
MSG_BONUS = 10        # Bonus pro 50 Zeichen


def load_xp():
    return data.load("xp", {})


def save_xp(d):
    data.save("xp", d)


def _user_xp(user_id):
    xp = load_xp()
    u = xp.setdefault(str(user_id), {"xp": 0, "last_msg": 0.0, "voice_last": 0.0})
    u.setdefault("xp", 0)
    return u


def message_xp(message):
    """Wird bei jeder Bot-Nachricht (nicht-Bot-Accounts, Guilds) aufgerufen."""
    if not message.guild or message.author.bot:
        return
    xp = load_xp()
    u = xp.setdefault(str(message.author.id), {"xp": 0, "last_msg": 0.0, "voice_last": 0.0})
    now = time.time()
    if now - u.get("last_msg", 0.0) < MSG_COOLDOWN:
        return
    amount = MSG_BASE + random.randint(0, 10)
    bonus = (len(message.content or "") // 50) * MSG_BONUS
    u["xp"] = u.get("xp", 0) + amount + bonus
    u["last_msg"] = now
    save_xp(xp)


async def voice_xp(bot, member, channel):
    """Voice-XP: 5 XP alle 2 Min. bei aktivem Voice (≥2 Personen, nicht-Bot-Member)."""
    if member.bot or not channel:
        return
    if len([m for m in channel.members if not m.bot]) < 2:
        return
    xp = load_xp()
    u = xp.setdefault(str(member.id), {"xp": 0, "last_msg": 0.0, "voice_last": 0.0})
    now = time.time()
    if now - u.get("voice_last", 0.0) < 120.0:
        return
    u["voice_last"] = now
    u["xp"] = u.get("xp", 0) + 5
    save_xp(xp)
    await maybe_grant_role(bot, member)


def level_info(xp):
    level = 0
    name = "Neuling"
    for i, (req, nm) in enumerate(MILESTONES):
        if xp >= req:
            level = i + 1
            name = nm
        else:
            break
    if level == 0:
        cur, nxt = 0, MILESTONES[0][0] if MILESTONES else 0
    elif level < len(MILESTONES):
        cur = MILESTONES[level - 2][0] if level >= 2 else 0
        nxt = MILESTONES[level][0]
    else:
        cur, nxt = MILESTONES[-1][0], xp
    span = nxt - cur if nxt > cur else 1
    filled = 0 if xp < cur else min(10, int(round((xp - cur) / span * 10)))
    if level >= len(MILESTONES):
        filled = 10
    return {"level": level, "name": name, "xp": xp, "cur": cur, "next": nxt,
            "bar": "█" * filled + "░" * (10 - filled)}


async def maybe_grant_role(bot, member):
    """Verleiht das passende Meilenstein-Rolle (z.B. 'Verified' – default color)."""
    xp = load_xp()
    info = level_info(xp.get(str(member.id), {}).get("xp", 0))
    role = bot.role_by_name(member.guild, info["name"])
    if role is not None and role not in member.roles:
        try:
            await member.add_role(role, reason=f"Level-Aufstieg: {info['name']}")
        except (discord.Forbidden, discord.HTTPException):
            pass


@app_commands.describe(user="Zielnutzer (default: du selbst)")
async def _cmd_level(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    info = level_info(load_xp().get(str(user.id), {}).get("xp", 0))
    emb = discord.Embed(color=0x57F287)
    emb.title = locales.t(interaction.user.id, "level_title", user=user)
    emb.description = (locales.t(interaction.user.id, "level_line", level=info["level"],
                                 name=info["name"], xp=info["xp"], next=info["next"])
                       + "\n" + locales.t(interaction.user.id, "level_progress",
                                          bar=info["bar"], cur=info["cur"], next=info["next"]))
    if not info["level"] and not info["xp"]:
        emb.description += "\n" + locales.t(interaction.user.id, "level_none", user=user)
    await interaction.response.send_message(embed=emb)


def register(bot):
    bot.tree.add_command(app_commands.command(name="level", description="Level und Fortschritt anzeigen")(_cmd_level))
