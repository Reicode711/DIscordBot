import logging
import os
import time
import math
import discord
import psutil
import glob
import subprocess
from discord.ext import commands, tasks
from dotenv import load_dotenv
import config

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("discord").setLevel(logging.CRITICAL)


TOKEN = config.DISCORD_TOKEN
VOICEVOX_PATH = config.VOICEVOX_PATH
channel_id = config.CHANNEL_ID
cog_files = glob.glob(config.COGS_PATH)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

start_time = time.time()
status_message = None

@bot.event
async def on_ready():
    print(f"{bot.user} ログイン完了。稼働中。")

    # VOICEVOXサーバー
    if VOICEVOX_PATH and os.path.exists(VOICEVOX_PATH):
        try:
            subprocess.Popen(VOICEVOX_PATH)
            print(f"✅ VOICEVOXサーバー起動: {VOICEVOX_PATH}")
        except Exception as e:
            print(f"⚠️ VOICEVOXサーバー起動失敗: {e}")
    else:
        print("⚠️ VOICEVOX_PATHが設定されていないか、ファイルが存在しません")

    # cogsディレクトリ内のすべての.pyファイルを自動で読み込む
    cog_files = glob.glob(os.path.join("cogs", "*.py"))
    cog_list = [
        os.path.splitext(os.path.basename(f))[0]
        for f in cog_files if not f.endswith("__init__.py")
    ]
    loaded_cogs = []
    for cog in cog_list:
        try:
            await bot.load_extension(f"cogs.{cog}")
            loaded_cogs.append(cog)
        except Exception as e:
            print(f"⚠️ Cogロード失敗: {cog} ({e})")

    print(f"✅ Cogロード完了: {len(loaded_cogs)}個")

    try:
        synced = await bot.tree.sync()
        print(f"✅ スラッシュコマンド同期完了: {len(synced)}個")
    except Exception as e:
        print(f"⚠️ スラッシュコマンド同期失敗: {e}")

    channel = bot.get_channel(channel_id)
    if channel:
        try:
            await channel.purge(limit=None)
            print("✅ 起動時メッセージ削除完了")
        except Exception as e:
            print(f"⚠️ メッセージ削除失敗: {e}")

    if not update_status.is_running():
        update_status.start()
    if not post_system_status.is_running():
        post_system_status.start()

@tasks.loop(seconds=1)
async def update_status():
    latency = bot.latency
    if latency is None or math.isinf(latency) or math.isnan(latency):
        ping = -1
    else:
        ping = round(latency * 1000)

    guild_count = len(bot.guilds)
    activity = discord.Game(name=f"{guild_count}サーバーで稼働中 | {ping}msで応答中")
    await bot.change_presence(activity=activity)

@tasks.loop(seconds=5)
async def post_system_status():
    global status_message

    uptime_sec = int(time.time() - start_time)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}時間{minutes}分{seconds}秒"

    cpu = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory().percent

    content = (
        f"🟢 **Botステータス**\n"
        f"⏱ 稼働時間: `{uptime_str}`\n"
        f"🧠 CPU使用率: `{cpu:.1f}%`\n"
        f"💾 メモリ使用率: `{memory:.1f}%`"
    )

    channel = bot.get_channel(channel_id)
    if channel:
        try:
            if status_message is None:
                status_message = await channel.send(content)
            else:
                await status_message.edit(content=content)
        except Exception as e:
            print(f"⚠️ ステータスメッセージ送信失敗: {e}")

import asyncio

try:
    bot.run(TOKEN)
except asyncio.CancelledError:
    pass
