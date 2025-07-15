import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class Stop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stop", description="再生中の音楽・プレイリストを停止してVCから切断")
    async def stop_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        stopped_services = []
        
        # Music機能の停止
        music_cog = self.bot.get_cog('Music')
        if music_cog:
            try:
                await music_cog.stop_all()
                stopped_services.append("Music")
            except Exception as e:
                print(f"Music停止エラー: {e}")
        
        # PlaylistCog機能の停止
        playlist_cog = self.bot.get_cog('PlaylistCog')
        if playlist_cog:
            try:
                guild_id = interaction.guild.id
                vc = playlist_cog.voice_clients.get(guild_id)
                if vc:
                    if vc.is_playing() or vc.is_paused():
                        vc.stop()
                    try:
                        await asyncio.wait_for(vc.disconnect(), timeout=5)
                    except Exception as e:
                        print(f"Playlist VC切断エラー: {e}")
                    playlist_cog.voice_clients.pop(guild_id, None)
                    stopped_services.append("Playlist")
                
                # アクティブメッセージの削除
                await playlist_cog.delete_active_message(guild_id)
                
            except Exception as e:
                print(f"Playlist停止エラー: {e}")
        
        # Join機能の停止
        join_cog = self.bot.get_cog('Join')
        if join_cog:
            try:
                guild_vc = interaction.guild.voice_client
                if guild_vc:
                    if guild_vc.is_playing():
                        guild_vc.stop()
                    try:
                        await asyncio.wait_for(guild_vc.disconnect(), timeout=5)
                    except Exception as e:
                        print(f"Join VC切断エラー: {e}")
                    stopped_services.append("Join")
                
                # TTSタスクの停止
                if join_cog.tts_task and not join_cog.tts_task.done():
                    join_cog.tts_task.cancel()
                    join_cog.tts_task = None
                
                # キャンセルイベントの設定
                join_cog.cancel_event.set()
                
                # パネル情報のクリア
                guild_id = str(interaction.guild.id)
                if guild_id in join_cog.panel_info:
                    for channel_id, info in join_cog.panel_info[guild_id].items():
                        try:
                            channel = interaction.guild.get_channel(int(channel_id))
                            if channel:
                                msg = await channel.fetch_message(info.get("message_id"))
                                await msg.delete()
                        except Exception:
                            pass
                    del join_cog.panel_info[guild_id]
                
                join_cog.panel_view = None
                
            except Exception as e:
                print(f"Join停止エラー: {e}")
        

        if hasattr(self.bot, 'current_running_cog'):
            self.bot.current_running_cog = None
        
        # 結果メッセージ
        if stopped_services:
            message = f"⏹️ 以下の機能を停止しました: {', '.join(stopped_services)}"
        else:
            message = "❌ 停止する機能が見つかりませんでした"
        
        await interaction.followup.send(message, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Stop(bot))