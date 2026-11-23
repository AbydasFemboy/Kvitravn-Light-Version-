"""Hauptmodul: MyBot (intents, Listener, Setup), load_config, main()."""
import json
import time
from pathlib import Path

import discord
from discord.ext import commands

import data, locales, moderation, music, levels, tickets, dashboard

CONFIG_FILE = Path("config.json")

DEFAULT_CONFIG = {
    "token": "DEIN_BOT_TOKEN_HIER_EINFÜGEN",
    "guild_id": None,
    "mod_role": "Moderation",
    "admin_role": "Admin",
    "owner_role": "Owner",
    "modlog_channel_id": None,
    "report_channel_id": None,
    "join_gate_role": "Unverified",
    "restricted_role": "Restricted",
    "verified_role": "Verified",
    "nsfw_role": "Verified 18+",
    "ticket_category": "kvitravn-support-tickets",
    "ticket_panel_channel_id": None,
    "voice_count_channel_id": None,
    "auto_join_voice": True,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def _guild_vc(bot, guild):
    for vc in bot.voice_clients:
        if vc.guild is guild:
            return vc
    return None


class MyBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="/", intents=intents,
                         help_command=None, description="Discord Bot")
        self.config = config
        self._nsfw_warned = set()
        self._rates = {}
        self.players = {}
        self.temp_voice_channels = set(data.load("voices", {"temp_channels": []}).get("temp_channels", []))
        # Command-Throttling für Slash-Commands (5/30s pro User)
        self.tree.interaction_check = self._tree_interaction_check

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def save_config(self):
        try:
            CONFIG_FILE.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def role_by_name(self, guild, name):
        for r in guild.roles:
            if r.name == name:
                return r
        return None

    def user_allowed(self, user, names):
        return any(r.name in names for r in user.roles)

    def rate_ok(self, user, name, maxn=5, window=30.0):
        now = time.time()
        ts = self._rates.setdefault(user.id, [])
        ts[:] = [t for t in ts if now - t < window]
        if len(ts) >= maxn:
            return False
        ts.append(now)
        return True

    async def log_ledger(self, action, target=None, mod=None, reason="", channel=None):
        await moderation.log_ledger(self, action, target, mod, reason, channel)

    async def _tree_interaction_check(self, interaction):
        try:
            user = interaction.user
            if user is not None and not self.rate_ok(user, "cmd:*"):
                try:
                    await interaction.response.send_message(locales.t(user.id, "throttled"), ephemeral=True)
                except Exception:
                    pass
                return False
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------
    # Setup (on_ready)
    # ------------------------------------------------------------------
    async def on_ready(self):
        print(f"[{time.strftime('%H:%M:%S')}] Bot eingeloggt als {self.user}")
        for guild in self.guilds:
            await self._setup_guild(guild)
        await self.tree.sync()
        moderation.register_aliases(self)
        print(f"[{time.strftime('%H:%M:%S')}] {len(self.tree.get_commands())} Slash-Commands synchronisiert")

    async def _setup_guild(self, guild):
        # Verified-Rolle (standardmäßig farblos)
        vname = self.config.get("verified_role", "Verified")
        if self.role_by_name(guild, vname) is None:
            try:
                await guild.create_role(name=vname, color=discord.Color.default(), reason="Verified-Rolle erstellt")
            except discord.HTTPException:
                pass
        # Mod-Log-Kanal
        mid = self.config.get("modlog_channel_id")
        if not mid or guild.get_channel(mid) is None:
            try:
                ch = await guild.create_text_channel("mod-log", reason="Mod-Log-Kanal erstellt")
                self.config["modlog_channel_id"] = ch.id
                self.save_config()
            except discord.HTTPException:
                pass
        # Tickets (Kategorie + #ticket-panel mit Buttons)
        try:
            await tickets.setup(self, guild)
        except Exception as e:
            print("Ticket-Setup fehlgeschlagen:", e)
        # Voice-Count-Kanal
        vcid = self.config.get("voice_count_channel_id")
        if not vcid or guild.get_channel(vcid) is None:
            try:
                ch = await guild.create_text_channel("🎙️ Voice")
                self.config["voice_count_channel_id"] = ch.id
                self.save_config()
                await self._update_voice_count(guild)
            except discord.HTTPException:
                pass

    async def _update_voice_count(self, guild):
        ch_id = self.config.get("voice_count_channel_id")
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if ch is None:
            return
        count = sum(len(vc.members) for vc in guild.voice_channels if getattr(vc, "members", None))
        try:
            await ch.edit(name=f"🎙️ Voice ({count})")
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # AutoMod (on_message)
    # ------------------------------------------------------------------
    async def _nsfw_check(self, message):
        ch = message.channel
        if not getattr(ch, "nsfw", False) or message.author.bot:
            return
        role_name = self.config.get("nsfw_role", "Verified 18+")
        role = self.role_by_name(message.guild, role_name)
        if role is not None and role in message.author.roles:
            return
        uid = str(message.author.id)
        if uid in self._nsfw_warned:
            return
        self._nsfw_warned.add(uid)
        try:
            await message.delete(reason="NSFW-Zugang")
        except discord.HTTPException:
            pass
        try:
            await message.channel.send(f"⛔ NSFW-Zugang erfordert die **{role_name}**-Rolle. (`/verify18`)")
        except discord.HTTPException:
            pass

    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        try:
            await self._nsfw_check(message)
        except Exception:
            pass
        try:
            levels.message_xp(message)
        except Exception:
            pass
        try:
            await moderation.automod_on_message(self, message)
        except Exception:
            pass
        content = message.content or ""
        if content.startswith("/"):
            name = content[1:].split()[0] if content[1:].split() else ""
            if name and not self.rate_ok(message.author, f"cmd:{name}"):
                return
        await self.process_commands(message)

    # ------------------------------------------------------------------
    # Member events
    # ------------------------------------------------------------------
    async def on_member_join(self, member):
        try:
            role_name = self.config.get("join_gate_role")
            if role_name and not member.bot:
                role = self.role_by_name(member.guild, role_name)
                if role is not None and role not in member.roles:
                    await member.add_role(role, reason="Join-Gate")
        except Exception:
            pass

    async def on_member_update(self, before, after):
        try:
            if not after.nick or before.nick == after.nick:
                return
            if moderation.INVITE_RE.search(after.nick):
                await after.edit(nick=before.nick or after.name, reason="Nickname mit Invite-Link")
                await self.log_ledger("Nickname-Reset", after, None, f"Invite-Link im Nickname: {after.nick}", None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Voice events
    # ------------------------------------------------------------------
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        # Voice-XP
        try:
            if after and after.channel and not member.bot:
                await levels.voice_xp(self, member, after.channel)
        except Exception:
            pass
        # Temp-Voice-Channels: beim Betreten eines temporären Channels einen neuen für den User
        try:
            if after and after.channel and after.channel.id in self.temp_voice_channels:
                new_ch = await guild.create_voice_channel(
                    name=f"{member.display_name} 🎙️",
                    category=after.channel.category,
                    position=after.channel.position + 1)
                self.temp_voice_channels.add(new_ch.id)
                data.save("voices", {"temp_channels": list(self.temp_voice_channels)})
                await member.move_to(new_ch)
        except Exception:
            pass
        # Auto-Join
        try:
            if after and after.channel and self.config.get("auto_join_voice"):
                if _guild_vc(self, guild) is None:
                    await after.channel.connect()
                else:
                    vc = _guild_vc(self, guild)
                    if vc.channel != after.channel:
                        await vc.move_to(after.channel)
        except Exception:
            pass
        # Voice-Count-Kanal aktualisieren
        try:
            await self._update_voice_count(guild)
        except Exception:
            pass

    async def on_error(self, event_name, *args, **kwargs):
        import traceback
        print(f"[ERROR] Fehler in {event_name}")
        traceback.print_exc()


def main():
    config = load_config()
    token_ok = bool(config.get("token")) and config["token"] != DEFAULT_CONFIG["token"]
    if not token_ok:
        print("⚠️  Kein Bot-Token in config.json gefunden — trage deinen Token ein.")
    bot = MyBot(config)
    for mod in (moderation, music, levels, tickets, dashboard):
        mod.register(bot)
    moderation.register_aliases(bot)
    if token_ok:
        bot.run(config["token"])
    else:
        print("Bot nicht gestartet (kein Token).")


if __name__ == "__main__":
    main()
