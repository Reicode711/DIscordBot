import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import yt_dlp
import config
from datetime import timedelta
import random

PLAYLIST_DIR = "playlists"
MUSIC_DIR = "music"
os.makedirs(PLAYLIST_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)

class PlaylistCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_clients = {}
        self.volume_level = 0.05
        self.active_message = {}  # コントロール埋め込みのメッセージID管理

    def get_playlist_path(self, user_id):
        return os.path.join(PLAYLIST_DIR, f"{user_id}.json")

    def load_playlist(self, user_id):
        path = self.get_playlist_path(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_playlist(self, user_id, playlist):
        path = self.get_playlist_path(user_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)

    def is_vc_in_use(self, guild_id):
        running_cog = getattr(self.bot, "current_running_cog", None)
        if running_cog and running_cog != "Playlist":
            return True
        vc = self.voice_clients.get(guild_id)
        return vc is not None and vc.is_connected()

    @app_commands.command(name="playlist", description="YouTubeのURLから音楽をダウンロードしてプレイリストに追加")
    @app_commands.describe(url="YouTubeの音楽URL")
    async def playlist(self, interaction: discord.Interaction, url: str):
        user_id = str(interaction.user.id)
        await interaction.response.send_message("ダウンロード中...", ephemeral=True)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(MUSIC_DIR, f"{user_id}_%(title)s.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'ffmpeg_location': config.FFMPEG_PATH,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'unknown')
                filename = f"{user_id}_{title}.mp3"
                filepath = os.path.join(MUSIC_DIR, filename)
                playlist = self.load_playlist(user_id)
                playlist.append(filepath)
                self.save_playlist(user_id, playlist)
            await interaction.followup.send(f"{title} をプレイリストに追加しました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"ダウンロード失敗: {e}", ephemeral=True)

    @app_commands.command(name="playliststart", description="VCに参加してプレイリストを再生")
    async def playliststart(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = interaction.guild.id
        playlist = self.load_playlist(user_id)
        if not playlist:
            await interaction.response.send_message("プレイリストが空です。", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("VCに入ってから実行してください。", ephemeral=True)
            return

        if self.is_vc_in_use(guild_id):
            await interaction.response.send_message("他の機能がVCを使用中です。再生できません。", ephemeral=True)
            return

        self.bot.current_running_cog = "Playlist"

        channel = interaction.user.voice.channel
        try:
            vc = await channel.connect()
            self.voice_clients[guild_id] = vc
        except Exception as e:
            await interaction.response.send_message(f"VC接続失敗: {e}", ephemeral=True)
            self.bot.current_running_cog = None
            return

        first_title = os.path.basename(playlist[0]).replace(f"{user_id}_", "").replace(".mp3", "") if playlist else "なし"
        embed = discord.Embed(
            title="🎵 プレイリスト再生中",
            description=f"再生中: **{first_title}**\n全{len(playlist)}曲",
            color=discord.Color.green()
        )
        view = self.PlaylistPlayerControls(vc, self, playlist, interaction)
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        sent_msg = await interaction.original_response()
        self.active_message[guild_id] = sent_msg

        try:
            for idx, music_path in enumerate(playlist):
                if not os.path.exists(music_path):
                    continue
                title = os.path.basename(music_path).replace(f"{user_id}_", "").replace(".mp3", "")
                embed.description = f"再生中: **{title}**\n全{len(playlist)}曲"
                embed.set_field_at(0, name="音量", value=self.get_volume_meter(), inline=False) if embed.fields else embed.add_field(name="音量", value=self.get_volume_meter(), inline=False)
                await interaction.edit_original_response(embed=embed, view=view)
                source = discord.FFmpegPCMAudio(music_path, executable=config.FFMPEG_PATH)
                vc.play(discord.PCMVolumeTransformer(source, volume=self.volume_level))
                while vc.is_playing() or vc.is_paused():
                    await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=1))
        except Exception as e:
            await interaction.followup.send(f"再生中にエラー: {e}", ephemeral=True)
        finally:
            try:
                await vc.disconnect()
            except Exception:
                pass
            self.voice_clients.pop(guild_id, None)
            self.bot.current_running_cog = None
            await self.delete_active_message(guild_id)

    @app_commands.command(name="playlistshuffle", description="VCに参加してプレイリストをシャッフル再生")
    async def playlistshuffle(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = interaction.guild.id
        playlist = self.load_playlist(user_id)
        if not playlist:
            await interaction.response.send_message("プレイリストが空です。", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("VCに入ってから実行してください。", ephemeral=True)
            return

        if self.is_vc_in_use(guild_id):
            await interaction.response.send_message("他の機能がVCを使用中です。再生できません。", ephemeral=True)
            return

        self.bot.current_running_cog = "Playlist"

        channel = interaction.user.voice.channel
        try:
            vc = await channel.connect()
            self.voice_clients[guild_id] = vc
        except Exception as e:
            await interaction.response.send_message(f"VC接続失敗: {e}", ephemeral=True)
            self.bot.current_running_cog = None
            return

        shuffled_playlist = playlist.copy()
        random.shuffle(shuffled_playlist)

        first_title = os.path.basename(shuffled_playlist[0]).replace(f"{user_id}_", "").replace(".mp3", "") if shuffled_playlist else "なし"
        embed = discord.Embed(
            title="🎵 プレイリスト（シャッフル）再生中",
            description=f"再生中: **{first_title}**\n全{len(shuffled_playlist)}曲",
            color=discord.Color.blue()
        )
        view = self.PlaylistPlayerControls(vc, self, shuffled_playlist, interaction)
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        sent_msg = await interaction.original_response()
        self.active_message[guild_id] = sent_msg

        try:
            for idx, music_path in enumerate(shuffled_playlist):
                if not os.path.exists(music_path):
                    continue
                title = os.path.basename(music_path).replace(f"{user_id}_", "").replace(".mp3", "")
                embed.description = f"再生中: **{title}**\n全{len(shuffled_playlist)}曲"
                embed.set_field_at(0, name="音量", value=self.get_volume_meter(), inline=False) if embed.fields else embed.add_field(name="音量", value=self.get_volume_meter(), inline=False)
                await interaction.edit_original_response(embed=embed, view=view)
                source = discord.FFmpegPCMAudio(music_path, executable=config.FFMPEG_PATH)
                vc.play(discord.PCMVolumeTransformer(source, volume=self.volume_level))
                while vc.is_playing() or vc.is_paused():
                    await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=1))
        except Exception as e:
            await interaction.followup.send(f"再生中にエラー: {e}", ephemeral=True)
        finally:
            try:
                await vc.disconnect()
            except Exception:
                pass
            self.voice_clients.pop(guild_id, None)
            self.bot.current_running_cog = None
            await self.delete_active_message(guild_id)

    async def delete_active_message(self, guild_id):
        msg = self.active_message.pop(guild_id, None)
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # VCから強制切断された場合にもコントロール埋め込みを削除
        if member.bot and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            await self.delete_active_message(guild_id)

    class PlaylistPlayerControls(discord.ui.View):
        def __init__(self, vc, cog, playlist=None, interaction=None):
            super().__init__(timeout=None)
            self.vc = vc
            self.cog = cog
            self.playlist = playlist if playlist is not None else []
            self.interaction = interaction
            self.current_index = 0

        @discord.ui.button(label="⏸️ / ▶️", style=discord.ButtonStyle.blurple)
        async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.vc.is_playing():
                self.vc.pause()
            elif self.vc.is_paused():
                self.vc.resume()
            await interaction.response.defer()

        @discord.ui.button(label="🔉 音量－", style=discord.ButtonStyle.gray)
        async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.volume_level = max(0.0, self.cog.volume_level - 0.1)
            if self.vc.source:
                self.vc.source.volume = self.cog.volume_level
            await interaction.response.defer()

        @discord.ui.button(label="🔊 音量＋", style=discord.ButtonStyle.gray)
        async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.volume_level = min(1.0, self.cog.volume_level + 0.1)
            if self.vc.source:
                self.vc.source.volume = self.cog.volume_level
            await interaction.response.defer()

        @discord.ui.button(label="⏭️ スキップ", style=discord.ButtonStyle.green)
        async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.vc.is_playing():
                self.vc.stop()
            await interaction.response.defer()

        @discord.ui.button(label="⏹️ 停止", style=discord.ButtonStyle.red)
        async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                if self.vc.is_playing() or self.vc.is_paused():
                    self.vc.stop()
                try:
                    await self.vc.disconnect()
                except (asyncio.CancelledError, asyncio.TimeoutError) as e:
                    # ログ出力や通知（必要なら）
                    print(f"VC切断例外: {type(e).__name__}: {e}")
                except Exception as e:
                    print(f"VC切断その他例外: {e}")
                guild_id = interaction.guild.id
                await self.cog.delete_active_message(guild_id)
                self.cog.bot.current_running_cog = None
            except Exception as e:
                print(f"停止ボタン例外: {e}")
            finally:
                await interaction.response.defer()

        @discord.ui.button(label="🔄 プレイリストリセット", style=discord.ButtonStyle.gray)
        async def reset_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
            user_id = str(interaction.user.id)
            self.cog.save_playlist(user_id, [])
            await interaction.response.send_message("プレイリストをリセットしました。", ephemeral=True)

        @discord.ui.button(label="🗑️ 曲を削除", style=discord.ButtonStyle.red)
        async def delete_song(self, interaction: discord.Interaction, button: discord.ui.Button):
            user_id = str(interaction.user.id)
            playlist = self.cog.load_playlist(user_id)
            if not playlist:
                await interaction.response.send_message("プレイリストが空です。", ephemeral=True)
                return

            options = [
                discord.SelectOption(
                    label=os.path.basename(path).replace(f"{user_id}_", "").replace(".mp3", ""),
                    value=str(idx)
                )
                for idx, path in enumerate(playlist)
            ]

            class SongSelect(discord.ui.Select):
                def __init__(self, options, parent_view):
                    super().__init__(placeholder="削除する曲を選択", min_values=1, max_values=1, options=options)
                    self.parent_view = parent_view

                async def callback(self, select_interaction: discord.Interaction):
                    idx = int(self.values[0])
                    removed = playlist.pop(idx)
                    self.parent_view.cog.save_playlist(user_id, playlist)
                    await select_interaction.response.send_message(
                        f"曲「{os.path.basename(removed).replace(f'{user_id}_', '').replace('.mp3', '')}」を削除しました。",
                        ephemeral=True
                    )

            select = SongSelect(options, self)
            view = discord.ui.View()
            view.add_item(select)
            await interaction.response.send_message("削除する曲を選択してください。", view=view, ephemeral=True)

        @discord.ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.blurple)
        async def shuffle_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.playlist or len(self.playlist) < 2:
                await interaction.response.send_message("シャッフルする曲がありません。", ephemeral=True)
                return
            random.shuffle(self.playlist)
            self.current_index = 0
            await interaction.response.send_message("プレイリストをシャッフルしました。", ephemeral=True)

    @app_commands.command(name="playlistmanage", description="プレイリスト管理（削除・リセット）ボタンを表示")
    async def playlistmanage(self, interaction: discord.Interaction):
        view = self.PlaylistPlayerControls(None, self)
        await interaction.response.send_message("プレイリスト管理", view=view, ephemeral=True)

    def get_volume_meter(self):
        meter_length = 10
        filled = int(self.volume_level * meter_length)
        empty = meter_length - filled
        return "🔊" * filled + "🔈" * empty + f" ({int(self.volume_level * 100)}%)"

async def setup(bot: commands.Bot):
    await bot.add_cog(PlaylistCog(bot))