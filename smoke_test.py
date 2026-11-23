import discord

import bot
import moderation, music, levels, tickets, dashboard

b = bot.MyBot(bot.load_config())
for mod in (moderation, music, levels, tickets, dashboard):
    mod.register(b)
moderation.register_aliases(b)

names = sorted(c.name for c in b.tree.get_commands())
print("Commands:", len(names))
print(names)
print("get_command('timeout'):", b.tree.get_command("timeout") is not None)
print("get_command('flüstern'):", b.tree.get_command("flüstern") is not None)
print("has process_commands:", hasattr(b, "process_commands"))
print("Member.edit nick:", "nick" in discord.Member.edit.__wrapped__.__code__.co_varnames if hasattr(discord.Member.edit, "__wrapped__") else "nick" in str(discord.Member.edit))
print("Guild.voice_client:", hasattr(discord.Guild, "voice_client"))
print("Client.voice_clients:", hasattr(b, "voice_clients"))
import edge_tts
print("Communicate.save:", hasattr(edge_tts.Communicate, "save"))
print("PermissionOverwrite:", discord.PermissionOverwrite(read_messages=False, send_messages=True))
print("tree.interaction_check is ours:", b.tree.interaction_check.__func__ is bot.MyBot._tree_interaction_check)
print("import ok")
