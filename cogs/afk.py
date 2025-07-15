import discord
from discord.ext import commands
from discord import app_commands

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # user_id: 元のニックネーム

    @app_commands.command(name="afk", description="自分のニックネームに（離席中）を付与し、サーバーミュートします")
    async def afk(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                await interaction.response.send_message("メンバー情報の取得に失敗しました。", ephemeral=True)
                return

            # すでにAFKなら何もしない
            if member.id in self.afk_users:
                await interaction.response.send_message("すでに（離席中）です。", ephemeral=True)
                return

            # 権限チェック
            if not interaction.guild.me.guild_permissions.manage_nicknames:
                await interaction.response.send_message("Botにニックネーム変更権限がありません。", ephemeral=True)
                return
            if not interaction.guild.me.guild_permissions.mute_members:
                await interaction.response.send_message("Botにサーバーミュート権限がありません。", ephemeral=True)
                return

            # 元のニックネーム保存
            self.afk_users[member.id] = member.display_name

            # ニックネーム変更とサーバーミュート
            new_nick = member.display_name
            if "（離席中）" not in new_nick:
                new_nick += "（離席中）"
            try:
                await member.edit(nick=new_nick, mute=True)
            except Exception as e:
                await interaction.response.send_message(
                    f"ニックネームまたはミュートの変更に失敗しました。Botのロール・権限を確認してください。\n{e}",
                    ephemeral=True
                )
                return

            # 全ユーザーに見えるメッセージ（ephemeral=False）＋ボタン
            view = AFKBackView(self, member.id)
            await interaction.response.send_message(
                f"🔕 {member.mention} が（離席中）になりました（サーバーミュート）。\n"
                "解除したい場合は下のボタンを押すか、`/back` コマンドを実行してください。",
                view=view,
                ephemeral=False
            )
        except Exception as e:
            await interaction.response.send_message(f"予期せぬエラーが発生しました: {e}", ephemeral=True)

    @app_commands.command(name="back", description="AFK状態を解除し、ミュート解除・名前復元します")
    async def back(self, interaction: discord.Interaction):
        await self._afk_back(interaction, manual=True)

    async def _afk_back(self, interaction, manual=False):
        try:
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                await interaction.response.send_message("メンバー情報の取得に失敗しました。", ephemeral=True)
                return

            if member.id not in self.afk_users:
                await interaction.response.send_message("AFK状態ではありません。", ephemeral=True)
                return

            # 権限チェック
            if not interaction.guild.me.guild_permissions.manage_nicknames:
                await interaction.response.send_message("Botにニックネーム変更権限がありません。", ephemeral=True)
                return
            if not interaction.guild.me.guild_permissions.mute_members:
                await interaction.response.send_message("Botにサーバーミュート権限がありません。", ephemeral=True)
                return

            # 元のニックネーム取得・復元
            original_nick = self.afk_users.pop(member.id)
            try:
                await member.edit(nick=original_nick, mute=False)
            except Exception as e:
                await interaction.response.send_message(
                    f"ニックネームまたはミュート解除に失敗しました。Botのロール・権限を確認してください。\n{e}",
                    ephemeral=True
                )
                return

            msg = f"{member.mention} のAFK状態を解除し、ミュート解除・名前を元に戻しました。"
            if manual:
                await interaction.response.send_message(msg, ephemeral=False)
            else:
                # ボタンの場合は followup
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=False)
                else:
                    await interaction.response.send_message(msg, ephemeral=False)
        except Exception as e:
            await interaction.response.send_message(f"予期せぬエラーが発生しました: {e}", ephemeral=True)

class AFKBackView(discord.ui.View):
    def __init__(self, afk_cog, user_id):
        super().__init__(timeout=300)
        self.afk_cog = afk_cog
        self.user_id = user_id

    @discord.ui.button(label="AFK解除（ミュート解除・名前復元）", style=discord.ButtonStyle.primary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("このボタンはあなた専用です。", ephemeral=True)
            return
        await self.afk_cog._afk_back(interaction)

async def setup(bot):
    await bot.add_cog(AFK(bot))