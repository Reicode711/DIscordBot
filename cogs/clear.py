import discord
from discord import app_commands
from discord.ext import commands

class Clear(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # スラッシュコマンド定義
    @app_commands.command(name="clear", description="指定した数のメッセージを削除します")
    @app_commands.describe(amount="削除したいメッセージ数（1以上）")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount < 1:
            await interaction.response.send_message("削除するメッセージ数は1以上で指定してください。", ephemeral=True)
            return

        # interaction.response は一度しか使えないため、最初は response で応答する
        await interaction.response.defer(ephemeral=True)  # 処理時間かかる時の応答遅延対策

        deleted = await interaction.channel.purge(limit=amount)

        # defer してるので followup で送信
        await interaction.followup.send(f"{len(deleted)}件のメッセージを削除しました。", ephemeral=True)

    # パーミッションがない場合のハンドリング
    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            # 応答済みなら followup、未応答なら response を使う必要あり
            if interaction.response.is_done():
                await interaction.followup.send("このコマンドを使用するには、メッセージの管理権限が必要です。", ephemeral=True)
            else:
                await interaction.response.send_message("このコマンドを使用するには、メッセージの管理権限が必要です。", ephemeral=True)
        else:
            if interaction.response.is_done():
                await interaction.followup.send(f"エラーが発生しました: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"エラーが発生しました: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Clear(bot))
