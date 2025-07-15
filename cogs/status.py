import discord
from discord import app_commands
from discord.ext import commands, tasks
import psutil
import time

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message = None
        self.start_time = time.time()
        self.update_task = None

    @app_commands.command(name="status", description="Botの状態を表示")
    async def status_slash(self, interaction: discord.Interaction):
        """スラッシュコマンド版 /status"""
        if self.update_task and self.update_task.is_running():
            await interaction.response.send_message("すでにステータス更新中です！", ephemeral=True)
            return

        embed = self.create_embed()
        await interaction.response.send_message(embed=embed)
        self.status_message = await interaction.original_response()
        self.update_task = self.update_status.start(interaction.channel)

    def create_embed(self):
        elapsed = int(time.time() - self.start_time)
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}時間{minutes}分{seconds}秒"

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        ping = round(self.bot.latency * 1000)

        embed = discord.Embed(title="🤖 Bot ステータス", color=0x00ff00)
        embed.add_field(name="稼働時間", value=uptime_str, inline=False)
        embed.add_field(name="CPU使用率", value=f"{cpu}%", inline=True)
        embed.add_field(name="メモリ", value=f"{mem.used // (1024 * 1024)}MB / {mem.total // (1024 * 1024)}MB", inline=True)
        embed.add_field(name="PING", value=f"{ping}ms", inline=True)
        return embed

    @tasks.loop(seconds=3)
    async def update_status(self, channel):
        if self.status_message:
            embed = self.create_embed()
            try:
                await self.status_message.edit(embed=embed)
            except discord.NotFound:
                self.update_task.cancel()

    @update_status.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Status(bot))
