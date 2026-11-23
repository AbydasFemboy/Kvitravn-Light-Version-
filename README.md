# Kvitravn Light Version – Discord-Bot

Discord-Bot (discord.py) aus einer Zusammenstellung von Moderation, Musik & Audio,
Level/XP, Tickets, AutoMod, Mod-Team-Dashboard, Alias-Manager.

## Dateien

| Datei | Inhalt |
| --- | --- |
| `bot.py` | Main: MyBot (Listener, Auto-Setup), `main()` |
| `moderation.py` | Timeout/Mute/Purge/Slowmode/Restrict-All/Rolle/Rolle-löschen/Warn(+Eskalation)/Warns/Unwarn/Report, Shadow Ledger (`modlog.json`), Spam/Mention/Invite-Blocker, Alias-Manager |
| `music.py` | 14 Musik-Befehle, Player (yt-dlp → FFmpeg), Playlists, Voice-Hilfen (Temp-Voice, Voice-Count, Auto-Join), TTS, `/ritual` |
| `levels.py` | XP pro Nachricht/Voice, Meilensteine (Bronze→Legend), `/level` |
| `tickets.py` | `#ticket-panel` mit Buttons, Private-Kanäle (Moderation/Admin), `/verify18` (18+-Rolle) |
| `dashboard.py` | `/modlog`, `/modreview`, `/whisperlist`, `/whisper` |
| `data.py` / `locales.py` | JSON-Storage + DE/EN-Text-Bibliothek |
| `config.json` | Konfiguration (u.a. Rollennamen, Kanal-IDs) |
| `data/` | Laufzeitdaten (xp.json, modlog.json, warns.json, playlists.json, whisper.json, …) |

## Setup

1. **Token:** `config.json` → `token: "<Bot-Token aus dem Developer Portal>"` (Bot → Token kopieren).
2. **Developer Portal:** *Message Content Intent* aktivieren; *Members Intent* für Nickname-Detektor/Join-Gate.
3. **ffmpeg** im PATH (erforderlich für Musik, Seek, Temp-Sounds).
4. **Starten:** `python bot.py` (im `discord_bot/`-Ordner).
5. **Bot zum Server einladen:** OAuth2-Link mit `scope=applications.commands` (App ID aus Developer Portal).

Beim ersten Start werden automatisch: `mod-log` (Shadow-Ledger-Kanal), `Verified` (Rolle, farblos),
`#ticket-panel` (Ticket-Buttons), `🎙️ Voice` (Voice-Count-Kanal) angelegt und die IDs in `config.json` gespeichert.

## Verfügbare Befehle (Slash-Commands)

### Moderation & Admin
`/timeout` (1 Min – 28 Tage), `/mute`, `/purge` (1–200), `/slowmode` (0–21600 s), `/restrict_all`,
`/rolle` (vergeben/entziehen), `/rolle_loeschen`, `/warn` (Eskalation: 3→10 Min, 5→60 Min, 7→24 h),
`/warns`, `/unwarn`, `/report` (an Mod-Team), `/alias` (Alias-Manager).

### Musik & Audio
`/play` (YouTube, yt-dlp), `/playliste`, `/stop`, `/skip`, `/queue`, `/loop`, `/shuffle`, `/volume` (0–200%),
`/seek`, `/jetzt`, `/autoplay`, `/ritual` (Befehlssounds), `/flüstern` (TTS im Voice), `/voice_einladen`.
Technik: yt-dlp Streaming (stdout→FFmpeg), temporäre Voice-Channels beim Betreten, Voice-Count-Kanal, Auto-Join.

### Level & XP
XP pro Nachricht (15–25 XP + Bonus für Länge), Voice-XP (5 XP alle 2 Min. bei aktivem Voice, ≥2 Personen),
`/level`. Meilensteine: Bronze(5) → Silver(10) → Gold(15) → Platinum(20) → Verified(25) → Master(30) →
Grandmaster(40) → Legend(50).

### Tickets
Panel-Button „🎟️ Support-Ticket erstellen“, Private Kanäle in Kategorie `kvitravn-support-tickets`,
`/verify18` (18+-Verifizierung – Rolle „Verified 18+“, hier selbstbestätigend).

### Mod-Team-Dashboard
`/modlog` (Shadow Ledger), `/modreview` (Top-Verstöße, Banns, Reporter, Whisper), `/whisperlist @user`,
`/whisper`.

### AutoMod (automatisch)
Spam-Blocker, Mention-Flut-Blocker, Invite-Link-Blocker (24 h-Timeout), Join-Gate (Unverified-Rolle),
NSFW-Zugang (18+-Rolle), Mod-Log-Kanal, Command-Throttling (5/30 s), Nickname-Detektor, Whisper-Archiv.

## Mehrsprachig
`/sprache` (Deutsch/Englisch per Nutzer), vollständige DE/EN-Text-Bibliothek (`locales.py`, ~50 Keys).
