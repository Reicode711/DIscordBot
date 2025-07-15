import discord
import time
import platform
import psutil
import math
from discord.ext import commands
from discord import app_commands

start_time = time.time()

class Insight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_uptime(self):
        uptime_sec = int(time.time() - start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}時間{minutes}分{seconds}秒"

    @app_commands.command(name="insight", description="Botの稼働状況とサーバー情報を表示します")
    async def insight(self, interaction: discord.Interaction):
        guild = interaction.guild
        latency = self.bot.latency
        ping = round(latency * 1000) if latency and not math.isinf(latency) else -1

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        uptime = self.get_uptime()

        embed = discord.Embed(title="📊 サーバーとBotのインサイト", color=discord.Color.blurple())
        embed.add_field(name="🖥 サーバー名", value=guild.name, inline=True)
        embed.add_field(name="🆔 サーバーID", value=guild.id, inline=True)
        embed.add_field(name="👥 メンバー数", value=guild.member_count, inline=True)
        embed.add_field(name="🗂 チャンネル数", value=len(guild.channels), inline=True)
        embed.add_field(name="🤖 参加サーバー数", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="🏓 Ping", value=f"{ping}ms", inline=True)
        embed.add_field(name="⏱ 稼働時間", value=uptime, inline=True)
        embed.add_field(name="🧠 CPU使用率", value=f"{cpu:.1f}%", inline=True)
        embed.add_field(name="💾 メモリ使用率", value=f"{mem:.1f}%", inline=True)
        embed.add_field(name="⚙️ Python", value=platform.python_version(), inline=True)
        embed.add_field(name="📚 discord.py", value=discord.__version__, inline=True)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Insight(bot))
