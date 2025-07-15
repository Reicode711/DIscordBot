import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import config  # 追加

PINNED_FILE = config.PINNED_MESSAGES_PATH  # config.pyからパス取得

def load_pinned():
    if os.path.exists(PINNED_FILE):
        try:
            with open(PINNED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[keep] PINNED_FILE読み込みエラー: {e}")
    return {}  # {guild_id: {channel_id: {"content": str, "message_id": int}}}

def save_pinned(data):
    try:
        with open(PINNED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[keep] PINNED_FILE保存エラー: {e}")

class Keep(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pinned = load_pinned()  # {guild_id: {channel_id: {"content": str, "message_id": int}}}
        self.keep_watcher.start()

    @app_commands.command(name="keep", description="このチャンネルに最新メッセージとして固定します")
    @app_commands.describe(message="送信したいテキストメッセージ")
    async def keep(self, interaction: discord.Interaction, message: str):
        try:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            channel_id = str(interaction.channel.id)
            # 既存の固定メッセージがあれば削除
            if guild_id and guild_id in self.pinned and channel_id in self.pinned[guild_id]:
                try:
                    msg_id = self.pinned[guild_id][channel_id]["message_id"]
                    msg = await interaction.channel.fetch_message(msg_id)
                    await msg.delete()
                except Exception as e:
                    print(f"[keep] 既存メッセージ削除失敗: {e}")
            # 新しいメッセージを送信して保存
            try:
                sent_msg = await interaction.channel.send(message)
            except Exception as e:
                print(f"[keep] メッセージ送信失敗: {e}")
                await interaction.response.send_message(f"メッセージ送信に失敗しました: {e}", ephemeral=True)
                return
            if guild_id not in self.pinned:
                self.pinned[guild_id] = {}
            self.pinned[guild_id][channel_id] = {"content": message, "message_id": sent_msg.id}
            save_pinned(self.pinned)
            await interaction.response.send_message("メッセージを送信・固定しました。", ephemeral=True)
        except Exception as e:
            print(f"[keep] コマンド実行エラー: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)
            except Exception as ee:
                print(f"[keep] エラー通知失敗: {ee}")

    @app_commands.command(name="keep_cancel", description="このチャンネルの固定メッセージを解除します")
    async def keep_cancel(self, interaction: discord.Interaction):
        try:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            channel_id = str(interaction.channel.id)
            if guild_id and guild_id in self.pinned and channel_id in self.pinned[guild_id]:
                try:
                    msg_id = self.pinned[guild_id][channel_id]["message_id"]
                    try:
                        msg = await interaction.channel.fetch_message(msg_id)
                        await msg.delete()
                    except Exception as e:
                        print(f"[keep_cancel] メッセージ削除失敗: {e}")
                    del self.pinned[guild_id][channel_id]
                    save_pinned(self.pinned)
                    await interaction.response.send_message("固定メッセージを解除しました。", ephemeral=True)
                except Exception as e:
                    print(f"[keep_cancel] コマンド処理エラー: {e}")
                    await interaction.response.send_message(f"解除処理中にエラーが発生しました: {e}", ephemeral=True)
            else:
                await interaction.response.send_message("固定メッセージはありません。", ephemeral=True)
        except Exception as e:
            print(f"[keep_cancel] コマンド実行エラー: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)
            except Exception as ee:
                print(f"[keep_cancel] エラー通知失敗: {ee}")

    @tasks.loop(seconds=5)
    async def keep_watcher(self):
        # 10秒ごとに全ての固定メッセージを監視・最新化
        for guild_id, channels in self.pinned.items():
            for channel_id, info in channels.items():
                try:
                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        continue
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        continue
                    # メッセージが最新でなければ再送信
                    last_msg = None
                    try:
                        async for msg in channel.history(limit=1):
                            last_msg = msg
                            break
                    except Exception as e:
                        print(f"[keep_watcher] チャンネル履歴取得失敗: {e}")
                        continue
                    if not last_msg or last_msg.id != info.get("message_id"):
                        # 以前の固定メッセージを削除
                        try:
                            old_msg = await channel.fetch_message(info.get("message_id"))
                            await old_msg.delete()
                        except Exception as e:
                            print(f"[keep_watcher] 旧メッセージ削除失敗: {e}")
                        # 新しいメッセージを送信
                        try:
                            new_msg = await channel.send(info.get("content", ""))
                            info["message_id"] = new_msg.id
                            save_pinned(self.pinned)
                        except Exception as e:
                            print(f"[keep_watcher] 新メッセージ送信失敗: {e}")
                except Exception as e:
                    print(f"[keep_watcher] 監視ループ例外: {e}")

    @keep_watcher.before_loop
    async def before_keep_watcher(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Keep(bot))