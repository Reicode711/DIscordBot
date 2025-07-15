import discord
from discord.ext import commands
from discord import app_commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="使えるコマンドの一覧を表示します。")
    async def help_command(self, interaction: discord.Interaction):
        message = (
            "📚 **使えるコマンド一覧**\n"
            "🎉 コマンド名をクリックすると入力欄に自動で挿入されます！\n"
            "🔮 [/fortune](</fortune>) - 占い機能。今日の運勢を占えます。\n"
            "🎵 [/music](</music>) - 音楽再生機能。YouTubeやApple Music対応、ボタンで操作も可能！\n"
            "🕹️ [/game](</game>) - ゲーム募集機能。ゲームの募集を作成し、参加・辞退・キャンセルができます。\n"
            "♻️ [/reload](</reload>) - Botの再起動（開発者専用）。Botを再起動し、最新状態に更新します。\n"
            "📊 [/status](</status>) - Botの状態表示。稼働時間、CPU・メモリ使用率、PINGを確認できます。\n"
            "🧹 [/clear](</clear>) - メッセージ一括削除。チャンネルのメッセージをまとめて削除します。\n"
            "🗣️ [/join](</join>) / [/leave](</leave>) / [/voice_settings](</voice_settings>) - VC参加・退出・話者/音量設定。\n"
            "📌 [/keep](</keep>) / [/keep_cancel](</keep_cancel>) - チャンネルの最新メッセージ固定・解除。\n"
            "🛌 [/afk](</afk>) / [/back](</back>) - AFK（離席中）状態の設定・解除。\n"
            "質問や要望はいつでもどうぞ！"
        )
        await interaction.response.send_message(message, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Help(bot))
