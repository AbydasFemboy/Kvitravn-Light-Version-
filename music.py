"""Musik & Audio: Player (yt-dlp -> FFmpeg), Playlists, Warteschlange, Volume, Seek,
Voice-Hilfen (Auto-Join, Temp-Voice, Voice-Count), TTS (Edge TTS) und /ritual-Sounds."""
import asyncio
import hashlib
import math
import re
import struct
import tempfile
import wave
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
import yt_dlp
import edge_tts

import data, locales


# ---------------------------------------------------------------------------
# Track + yt-dlp-Suche
# ---------------------------------------------------------------------------
class Track:
    def __init__(self, title, url, duration=0):
        self.title = title or "Unbekannter Titel"
        self.url = url or ""
        self.duration = int(duration or 0)

    def to_dict(self):
        return {"title": self.title, "url": self.url, "duration": self.duration}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("title"), d.get("url"), d.get("duration", 0))

    def __repr__(self):
        return f"<Track {self.title!r} {self.duration}s>"


def pick_url(entry):
    """Bestes Audio-Format (vcodec none) aus einem yt-dlp-Eintrag auswaehlen."""
    best = None
    for f in entry.get("formats") or []:
        url = f.get("url")
        if not url:
            continue
        is_audio = (f.get("vcodec") or "none") == "none"
        if best is None or (is_audio and (best.get("vcodec") or "none") != "none"):
            best = f
        elif is_audio and (f.get("abr") or 0) > (best.get("abr") or 0):
            best = f
    return (best or {}).get("url") or entry.get("url") or ""


def search_tracks(bot, query, limit=1):
    """yt-dlp Search -> Liste von Tracks (erste `limit` Treffer)."""
    tracks = []
    if not query or not query.strip():
        return tracks
    params = {"quiet": True, "noplaylist": True, "skip_download": True, "default_search": "ytsearch"}
    try:
        with yt_dlp.YoutubeDL(params) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception:
        return tracks
    for e in info.get("entries") or [info]:
        if not e or len(tracks) >= limit:
            break
        url = pick_url(e)
        if not url:
            continue
        tracks.append(Track(e.get("title") or e.get("id") or "Unbekannt", url, e.get("duration") or 0))
    return tracks


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class MusicPlayer:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.vc = None
        self.tracks = []          # Warteschlange
        self.current = None       # aktueller Track
        self.loop = "none"        # none | track | queue
        self.shuffle = False
        self.autoplay = False
        self.volume = 1.0
        self._skip_next = False

    @property
    def playing(self):
        return self.vc is not None and self.vc.is_playing()

    def _set_volume(self):
        try:
            self.vc.source.volume = self.volume
        except Exception:
            pass

    async def play_track(self, track, offset=0):
        if not track or not track.url or not self.vc or not self.vc.is_connected():
            return False
        self.current = track
        before = "-reconnect 1 -reconnect_streamed 1"
        if offset > 0:
            before = f"-ss {offset} " + before
        try:
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(track.url, before_options=before), volume=self.volume)
            self.vc.play(source, after=lambda exc: asyncio.ensure_future(self._on_end()))
        except Exception:
            return False
        return True

    async def _on_end(self):
        """Wird aufgerufen, wenn der aktuelle Track endet (natuerlich)."""
        if self._skip_next:
            self._skip_next = False
            self.current = None
            return
        if self.loop == "track" and self.current:
            await self.play_track(self.current)
            return
        nxt = None
        if self.tracks:
            nxt = self.tracks.pop(0)
        elif self.autoplay:
            nxt = await self.autoplay_track()
        if nxt:
            await self.play_track(nxt)
        else:
            self.current = None

    async def skip(self):
        nxt = None
        if self.tracks:
            nxt = self.tracks.pop(0)
        elif self.autoplay:
            nxt = await self.autoplay_track()
        if self.vc and self.playing:
            self._skip_next = True
            try:
                self.vc.stop()
            except Exception:
                pass
        if nxt:
            await self.play_track(nxt)
        else:
            self.current = None

    async def stop(self):
        if self.vc:
            try:
                self.vc.stop()
            except Exception:
                pass
        self.current = None
        self.tracks.clear()

    async def seek(self, seconds):
        if not self.current or not self.playing:
            return False
        pos = seconds
        if self.current.duration:
            pos = min(pos, max(0, self.current.duration - 1))
        return await self.play_track(self.current, offset=pos)

    async def autoplay_track(self):
        if not self.current:
            return None
        try:
            tracks = search_tracks(self.bot, f"{self.current.title} mix", limit=1)
        except Exception:
            return None
        return tracks[0] if tracks else None


def get_player(bot, guild):
    p = bot.players.get(guild.id)
    if p is None:
        p = MusicPlayer(bot, guild)
        bot.players[guild.id] = p
    return p


# ---------------------------------------------------------------------------
# /ritual — Sound-Dateien (gesamt-offline generierte Töne)
# ---------------------------------------------------------------------------
def _sound_file(name):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:20] or "sound"
    path = Path("sounds") / f"{safe}.wav"
    if not path.exists():
        try:
            path.parent.mkdir(exist_ok=True)
        except OSError:
            pass
        try:
            freq = 300 + (int(hashlib.md5(name.encode()).hexdigest(), 16) % 500)
            rate = 48000
            dur = 0.7
            frames = bytearray()
            n = int(rate * dur)
            for i in range(n):
                t = i / rate
                env = min(1.0, t * 6, (dur - t) * 6)
                frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * freq * t)))
            with wave.open(str(path), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(bytes(frames))
        except Exception:
            return None
    return str(path)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@app_commands.describe(query="Suchbegriff oder YouTube-URL")
async def _cmd_play(interaction: discord.Interaction, query: str):
    bot = interaction.client
    user = interaction.user
    vc = user.voice.channel if user.voice else None
    if not vc:
        await interaction.response.send_message(locales.t(user.id, "play_join_first"), ephemeral=True)
        return
    player = get_player(bot, interaction.guild)
    if player.vc is None or not player.vc.is_connected():
        try:
            player.vc = await vc.connect()
        except (discord.HTTPException, discord.ClientException) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
    elif player.vc.channel != vc:
        try:
            await player.vc.move_to(vc)
        except discord.HTTPException:
            pass
    playlists = data.load("playlists", {})
    tracks = playlists.get(query)
    if tracks:
        player.tracks.extend([Track.from_dict(d) for d in tracks])
    else:
        found = search_tracks(bot, query, limit=1)
        if not found:
            await interaction.response.send_message(locales.t(user.id, "play_results"), ephemeral=True)
            return
        player.tracks.append(found[0])
    if not player.playing and not player.current:
        nxt = player.tracks.pop(0) if player.tracks else None
        if nxt:
            await player.play_track(nxt)
    if player.current:
        title = player.current.title
    elif player.tracks:
        title = player.tracks[0].title
    else:
        title = "?"
    await interaction.response.send_message(locales.t(user.id, "play_ok", title=title))


@app_commands.describe(name="Name der Playlist (ohne = Liste anzeigen)")
async def _cmd_playliste(interaction: discord.Interaction, name: Optional[str] = None):
    player = get_player(interaction.client, interaction.guild)
    playlists = data.load("playlists", {})
    if name is None:
        if not playlists:
            await interaction.response.send_message(locales.t(interaction.user.id, "playlist_list_empty"), ephemeral=True)
            return
        lines = [f"• {k} ({len(v)} Lieder)" for k, v in list(playlists.items())[:10]]
        await interaction.response.send_message(locales.t(interaction.user.id, "playlist_list") + "\n" + "\n".join(lines))
        return
    if not player.tracks:
        await interaction.response.send_message(locales.t(interaction.user.id, "playlist_empty"), ephemeral=True)
        return
    playlists[name] = [tr.to_dict() for tr in player.tracks]
    data.save("playlists", playlists)
    await interaction.response.send_message(locales.t(interaction.user.id, "playlist_saved", name=name, n=len(player.tracks)))


async def _cmd_stop(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    await player.stop()
    await interaction.response.send_message(locales.t(interaction.user.id, "stop_ok"))


async def _cmd_skip(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    await player.skip()
    await interaction.response.send_message(locales.t(interaction.user.id, "skip_ok") if player.current or player.tracks else locales.t(interaction.user.id, "skip_none"))


async def _cmd_queue(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    if not player.current and not player.tracks:
        await interaction.response.send_message(locales.t(interaction.user.id, "queue_empty"), ephemeral=True)
        return
    emb = discord.Embed(color=0x57F287)
    emb.title = locales.t(interaction.user.id, "queue_title", n=len(player.tracks) + (1 if player.current else 0))
    lines = []
    if player.current:
        lines.append(locales.t(interaction.user.id, "queue_now") + ": " + player.current.title[:100])
    for i, tr in enumerate(player.tracks[:15], 1):
        lines.append(locales.t(interaction.user.id, "queue_line", i=i, title=tr.title[:90]))
    if lines:
        emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)


@app_commands.describe(mode="'track', 'queue' oder 'none' (leer: togglen)")
async def _cmd_loop(interaction: discord.Interaction, mode: Optional[str] = None):
    player = get_player(interaction.client, interaction.guild)
    if mode is None:
        if player.loop == "none":
            player.loop = "track"
        elif player.loop == "track":
            player.loop = "queue"
        else:
            player.loop = "none"
    elif mode in ("none", "track", "queue"):
        player.loop = mode
    else:
        await interaction.response.send_message("❌ Modus 'none', 'track' oder 'queue'.", ephemeral=True)
        return
    if player.loop == "none":
        await interaction.response.send_message(locales.t(interaction.user.id, "loop_off"))
    else:
        await interaction.response.send_message(locales.t(interaction.user.id, "loop_on", mode=player.loop))


async def _cmd_shuffle(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    player.shuffle = not player.shuffle
    await interaction.response.send_message(locales.t(interaction.user.id, "shuffle_on") if player.shuffle else locales.t(interaction.user.id, "shuffle_off"))


@app_commands.describe(level="Lautstärke 0–200%")
async def _cmd_volume(interaction: discord.Interaction, level: app_commands.Range[int, 0, 200]):
    player = get_player(interaction.client, interaction.guild)
    player.volume = level / 100
    player._set_volume()
    await interaction.response.send_message(locales.t(interaction.user.id, "volume_ok", v=level))


@app_commands.describe(seconds="Sekunden bis Sprung (0–1000000)")
async def _cmd_seek(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 1000000]):
    player = get_player(interaction.client, interaction.guild)
    if not player.current or not player.playing:
        await interaction.response.send_message(locales.t(interaction.user.id, "seek_none"), ephemeral=True)
        return
    pos = seconds
    if player.current.duration:
        pos = min(pos, max(0, player.current.duration - 1))
    ok = await player.seek(pos)
    if ok:
        await interaction.response.send_message(locales.t(interaction.user.id, "seek_ok", t=f"{pos // 60}:{pos % 60:02d}"))
    else:
        await interaction.response.send_message(locales.t(interaction.user.id, "seek_none"), ephemeral=True)


async def _cmd_jetzt(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    if not player.current:
        await interaction.response.send_message(locales.t(interaction.user.id, "jetzt_none"), ephemeral=True)
        return
    t = player.current
    emb = discord.Embed(title=t.title, color=0x57F287)
    if t.duration:
        emb.set_footer(text=f"{t.duration // 60}:{t.duration % 60:02d} Min.")
    if t.url:
        emb.url = t.url
    await interaction.response.send_message(embed=emb)


async def _cmd_autoplay(interaction: discord.Interaction):
    player = get_player(interaction.client, interaction.guild)
    player.autoplay = not player.autoplay
    await interaction.response.send_message(locales.t(interaction.user.id, "autoplay_on") if player.autoplay else locales.t(interaction.user.id, "autoplay_off"))


@app_commands.describe(name="Name des Sounds (z.B. 'bell', 'ping', 'alert')")
async def _cmd_ritual(interaction: discord.Interaction, name: str):
    bot = interaction.client
    user = interaction.user
    vc = user.voice.channel if user.voice else None
    player = get_player(bot, interaction.guild)
    if not vc:
        await interaction.response.send_message(locales.t(user.id, "tts_none"), ephemeral=True)
        return
    if player.vc is None or not player.vc.is_connected():
        try:
            player.vc = await vc.connect()
        except (discord.HTTPException, discord.ClientException) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
    sound = _sound_file(name)
    if not sound:
        await interaction.response.send_message(locales.t(user.id, "ritual_unknown", name=name), ephemeral=True)
        return
    try:
        player.vc.play(discord.FFmpegPCMAudio(sound))
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(user.id, "ritual_ok", name=name))


@app_commands.describe(user="Nutzer im Voice, der tätschelt wird", text="Zu sagen/tts zu sprechen")
async def _cmd_flüstern(interaction: discord.Interaction, user: discord.Member, text: str):
    bot = interaction.client
    vc = user.voice.channel if user.voice else None
    if not vc:
        await interaction.response.send_message(locales.t(interaction.user.id, "tts_none"), ephemeral=True)
        return
    player = get_player(bot, interaction.guild)
    if player.vc is None or not player.vc.is_connected():
        try:
            player.vc = await vc.connect()
        except (discord.HTTPException, discord.ClientException) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
    lang = locales._lang(user.id)
    voice = "de-DE-KatrinNeural" if lang == "de" else "en-US-JennyNeural"
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        await edge_tts.Communicate(text, voice=voice).save(tmp.name)
    except Exception as e:
        await interaction.response.send_message(f"❌ TTS fehlgeschlagen: {e}", ephemeral=True)
        return
    try:
        player.vc.play(discord.FFmpegPCMAudio(tmp.name))
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "tts_ok", user=user))


async def _cmd_voice_einladen(interaction: discord.Interaction):
    bot = interaction.client
    vc = interaction.user.voice.channel if interaction.user.voice else None
    if not vc:
        await interaction.response.send_message(locales.t(interaction.user.id, "tts_none"), ephemeral=True)
        return
    player = get_player(bot, interaction.guild)
    try:
        if player.vc is None or not player.vc.is_connected():
            player.vc = await vc.connect(self_deaf=not player.playing)
        elif player.vc.channel != vc:
            await player.vc.move_to(vc)
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        return
    await interaction.response.send_message(locales.t(interaction.user.id, "voice_invite_ok", channel=vc.mention))


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------
def register(bot):
    cmds = [
        ("play", "Songs abspielen (YouTube, yt-dlp)", _cmd_play),
        ("playliste", "Playlists ansehen/speichern", _cmd_playliste),
        ("stop", "Track stoppen", _cmd_stop),
        ("skip", "Track überspringen", _cmd_skip),
        ("queue", "Warteschlange anzeigen", _cmd_queue),
        ("loop", "Track/Warteschlange wiederholen", _cmd_loop),
        ("shuffle", "Warteschlange mischen", _cmd_shuffle),
        ("volume", "Lautstärke (0–200%)", _cmd_volume),
        ("seek", "Im Track springen", _cmd_seek),
        ("jetzt", "Aktuellen Track anzeigen", _cmd_jetzt),
        ("autoplay", "Ähnliche Tracks nachladen", _cmd_autoplay),
        ("ritual", "Befehlssounds", _cmd_ritual),
        ("flüstern", "TTS im Voice (Edge TTS)", _cmd_flüstern),
        ("voice_einladen", "Bot privat in Voice holen", _cmd_voice_einladen),
    ]
    for name, desc, func in cmds:
        bot.tree.add_command(app_commands.command(name=name, description=desc)(func))
