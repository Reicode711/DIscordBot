import discord
import os
import sys
import asyncio
from discord.ext import commands
from discord import app_commands

OWNER_IDS = [907254481371144243,813649464187158548,1227748698101121104]
# rei mugi nura
class Reload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="reload", description="Botを再起動して最新状態に更新します")
    async def reload(self, interaction: discord.Interaction):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("このコマンドはBotの開発者のみ使用できます。", ephemeral=True)
            return

        await interaction.response.send_message("♻️ Botを再起動しています...", ephemeral=True)

        await asyncio.sleep(1)

        python = sys.executable
        os.execl(python, python, *sys.argv)

async def setup(bot):
    await bot.add_cog(Reload(bot))
