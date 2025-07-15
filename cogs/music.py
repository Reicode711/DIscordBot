import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
from collections import deque
import config
import re
import requests
import json

def is_apple_music_url(url: str) -> bool:
    return "music.apple.com" in url

def get_apple_music_title_jsonld(url: str) -> str:
    """
    Apple Musicのページから<script type="application/ld+json">を抜き出して曲名＋アーティストを取得する方法。
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None

        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', res.text, re.DOTALL)
        for script in scripts:
            data = json.loads(script)
            if isinstance(data, dict) and data.get("@type") == "MusicRecording":
                name = data.get("name")
                by_artist = data.get("byArtist")
                if by_artist and isinstance(by_artist, dict):
                    artist_name = by_artist.get("name")
                else:
                    artist_name = None
                if name and artist_name:
                    return f"{name} {artist_name}"
        return None
    except Exception as e:
        print(f"[AppleMusic JSON-LD] Error: {e}")
        return None

def get_apple_music_title_html(url: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None
        m = re.search(r"<title>(.+?) - (.+?) - Apple Music</title>", res.text)
        if m:
            title = m.group(1).strip()
            artist = m.group(2).strip()
            return f"{title} {artist}"
    except Exception as e:
        print(f"[AppleMusic HTML] Error: {e}")
    return None

def get_youtube_url_by_keyword(keyword: str) -> str:
    """
    キーワードでYouTube検索し、最初の動画のURLを返す
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch1', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(keyword, download=False)
        if 'entries' in info and info['entries']:
            return info['entries'][0]['webpage_url']
        if 'webpage_url' in info:
            return info['webpage_url']
    return None

def is_youtube_playlist_url(url: str) -> bool:
    return "youtube.com/playlist?list=" in url or "youtu.be/playlist?list=" in url

def extract_youtube_playlist_video_urls(playlist_url: str) -> list:
    """
    YouTubeプレイリストURLから全動画のURLリストを返す
    存在しない場合は空リストを返す
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }
    urls = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            for entry in info.get('entries', []):
                if 'url' in entry:
                    video_id = entry['url']
                    urls.append(f"https://www.youtube.com/watch?v={video_id}")
    except Exception as e:
        print(f"[yt_dlp] プレイリスト取得失敗: {e}")
        # ここで空リストを返すことで、コマンド側で「取得失敗」と案内できる
        return []
    return urls

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.preparing_message = None
        self.current_embed_message = None
        self.voice_client = None
        self.queue = deque()
        self.now_playing = None
        self.now_playing_url = None
        self.now_playing_requester = None  # ★追加
        self.volume_level = 0.3
        self.is_paused = False
        self.is_looping = False

        if not hasattr(self.bot, "current_running_cog"):
            self.bot.current_running_cog = None

    def get_display_volume(self):
        return int(self.volume_level * 10)

    async def ensure_no_conflict(self, interaction):
        if self.bot.current_running_cog and self.bot.current_running_cog != "Music":
            await interaction.response.send_message("他の機能が実行中です。停止してから使ってください。", ephemeral=True)
            return False
        self.bot.current_running_cog = "Music"
        return True

    async def extract_info_async(self, url):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_info, url)

    def _extract_info(self, url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'default_search': 'ytsearch'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def update_now_playing_embed(self, channel):
        if not self.now_playing:
            return

        embed = discord.Embed(
            title="🎵 再生中",
            description=f"[{self.now_playing}]({self.now_playing_url})",
            color=discord.Color.green()
        )
        if self.now_playing_requester:
            embed.add_field(name="リクエスト者", value=self.now_playing_requester.mention, inline=False)
        else:
            embed.add_field(name="リクエスト者", value="不明", inline=False)
        embed.add_field(name="🔊 音量", value=f"{self.get_display_volume()}/10", inline=False)
        embed.add_field(name="🔁 ループ", value="有効" if self.is_looping else "無効", inline=True)
        embed.add_field(name="📜 キュー数", value=f"{len(self.queue)}曲", inline=True)

        if self.current_embed_message:
            try:
                await self.current_embed_message.edit(embed=embed)
            except discord.NotFound:
                self.current_embed_message = await channel.send(embed=embed, view=self.PlayerControls(channel, self))
        else:
            self.current_embed_message = await channel.send(embed=embed, view=self.PlayerControls(channel, self))

    async def play_next(self, channel):
        if not self.queue and not self.is_looping:
            if self.voice_client:
                await self.voice_client.disconnect()
                self.voice_client = None
            if self.current_embed_message:
                try:
                    await self.current_embed_message.delete()
                except discord.NotFound:
                    pass
                self.current_embed_message = None
            self.bot.current_running_cog = None
            return

        if not self.voice_client or not self.voice_client.is_connected():
            if channel.guild.voice_client:
                self.voice_client = channel.guild.voice_client
            else:
                voice_channel = None
                for member in channel.guild.members:
                    if member.voice and member.voice.channel:
                        voice_channel = member.voice.channel
                        break
                if voice_channel:
                    self.voice_client = await voice_channel.connect()
                else:
                    await channel.send("接続中のボイスチャンネルが見つかりません。")
                    self.bot.current_running_cog = None
                    return

        if self.voice_client.is_playing():
            return

        if self.is_looping and self.now_playing_url and self.now_playing_requester:
            url = self.now_playing_url
            user = self.now_playing_requester
        else:
            url, user = self.queue.popleft()
            self.now_playing_url = url
            self.now_playing_requester = user
        self.is_paused = False

        if self.preparing_message:
            try:
                await self.preparing_message.delete()
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"[preparing_message.delete] 予期しないエラー: {e}")
            self.preparing_message = None
        self.preparing_message = await channel.send("再生準備中...")

        try:
            info = await self.extract_info_async(url)
            title = info.get('title', 'Unknown Title')
            audio_url = info['url'] if 'url' in info else max(
                [f for f in info.get('formats', []) if f.get('acodec') != 'none' and f.get('url')],
                key=lambda f: f.get('abr') or 0)['url']
        except Exception as e:
            await channel.send(f"音源取得失敗: {str(e)}")
            if self.preparing_message:
                try:
                    await self.preparing_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    print(f"[preparing_message.delete] 予期しないエラー: {e}")
                self.preparing_message = None
                self.bot.current_running_cog = None
            return

        self.now_playing = title

        source = discord.FFmpegPCMAudio(
            audio_url,
            executable=config.FFMPEG_PATH,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn"
        )

        def after_play(error):
            coro = self.play_next(channel)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f"Error in after_play: {e}")

        self.voice_client.play(
            discord.PCMVolumeTransformer(source, volume=self.volume_level),
            after=after_play
        )

        if self.preparing_message:
            try:
                await self.preparing_message.delete()
            except discord.NotFound:
                pass

        await self.update_now_playing_embed(channel)

    @app_commands.command(name="music", description="YouTube URL（動画/プレイリスト）またはキーワードで再生")
    async def music_command(self, interaction: discord.Interaction, url: str):
        conflict = await self.ensure_no_conflict(interaction)
        if not conflict:
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("VCに参加してから実行してください。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)  # ここで1回だけ

        # 以降は followup.send を使う
        if is_youtube_playlist_url(url):
            video_urls = extract_youtube_playlist_video_urls(url)
            if not video_urls:
                await interaction.followup.send("プレイリストの動画取得に失敗しました。", ephemeral=True)
                return
            for vurl in video_urls:
                self.queue.append((vurl, interaction.user))
            await interaction.followup.send(f"プレイリストから{len(video_urls)}曲をキューに追加しました。", ephemeral=True)
        elif is_apple_music_url(url):
            keyword = get_apple_music_title_jsonld(url) or get_apple_music_title_html(url)
            if not keyword:
                await interaction.followup.send("Apple Musicの曲情報取得に失敗しました。", ephemeral=True)
                return
            youtube_url = get_youtube_url_by_keyword(keyword)
            if not youtube_url:
                await interaction.followup.send("YouTubeで該当曲が見つかりませんでした。", ephemeral=True)
                return
            self.queue.append((youtube_url, interaction.user))
            await interaction.followup.send(f"キューに追加しました（{len(self.queue)}曲）", ephemeral=True)
        else:
            self.queue.append((url, interaction.user))
            await interaction.followup.send(f"キューに追加しました（{len(self.queue)}曲）", ephemeral=True)

        if not self.voice_client:
            self.voice_client = await interaction.user.voice.channel.connect()
        else:
            if self.voice_client.channel != interaction.user.voice.channel:
                await self.voice_client.move_to(interaction.user.voice.channel)

        await self.play_next(interaction.channel)

    class PlayerControls(discord.ui.View):
        def __init__(self, channel, cog, queue_page=0):
            super().__init__(timeout=None)
            self.channel = channel
            self.cog = cog
            self.queue_page = queue_page  # 現在のページ番号

        PAGE_SIZE = 20

        @discord.ui.button(label="⏸️ / ▶️", style=discord.ButtonStyle.blurple)
        async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
            vc = self.cog.voice_client
            if not vc:
                await interaction.response.send_message("ボイスチャンネルに接続していません。", ephemeral=True)
                return
            if vc.is_playing():
                vc.pause()
            elif vc.is_paused():
                vc.resume()
            await interaction.response.defer()

        @discord.ui.button(label="🔉 音量－", style=discord.ButtonStyle.gray)
        async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.volume_level = max(0.0, self.cog.volume_level - 0.1)
            if self.cog.voice_client and self.cog.voice_client.source:
                self.cog.voice_client.source.volume = self.cog.volume_level
            await self.cog.update_now_playing_embed(self.channel)
            await interaction.response.defer()

        @discord.ui.button(label="🔊 音量＋", style=discord.ButtonStyle.gray)
        async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.volume_level = min(1.0, self.cog.volume_level + 0.1)
            if self.cog.voice_client and self.cog.voice_client.source:
                self.cog.voice_client.source.volume = self.cog.volume_level
            await self.cog.update_now_playing_embed(self.channel)
            await interaction.response.defer()

        @discord.ui.button(label="⏭️ スキップ", style=discord.ButtonStyle.green)
        async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
            vc = self.cog.voice_client
            if vc and vc.is_playing():
                vc.stop()
            await self.cog.update_now_playing_embed(self.channel)
            await interaction.response.defer()

        @discord.ui.button(label="📜 キュー表示", style=discord.ButtonStyle.green)
        async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.send_queue_page(interaction, 0)

        async def send_queue_page(self, interaction, page):
            queue = list(self.cog.queue)
            total = len(queue)
            if total == 0:
                if interaction.response.is_done():
                    await interaction.followup.send("キューは空です。", ephemeral=True)
                else:
                    await interaction.response.send_message("キューは空です。", ephemeral=True)
                return

            max_page = (total - 1) // self.PAGE_SIZE
            page = max(0, min(page, max_page))
            start = page * self.PAGE_SIZE
            end = start + self.PAGE_SIZE
            msg = "\n".join(f"{i+1}. {url}" for i, (url, user) in enumerate(queue[start:end], start=start))
            content = f"再生待ちキュー（{page+1}/{max_page+1}ページ）：\n{msg}"

            view = QueuePaginationView(self.channel, self.cog, page, max_page)
            if interaction.response.is_done():
                # 既存メッセージを編集
                await interaction.edit_original_response(content=content, view=view)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=True)

        @discord.ui.button(label="❌ キュークリア", style=discord.ButtonStyle.red)
        async def clear_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.queue.clear()
            await self.cog.update_now_playing_embed(self.channel)
            await interaction.response.defer()

        @discord.ui.button(label="⏹️ 停止", style=discord.ButtonStyle.red)
        async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
            vc = self.cog.voice_client
            if vc:
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                try:
                    await vc.disconnect()
                except Exception:
                    pass
            self.cog.voice_client = None
            self.cog.queue.clear()
            if self.cog.current_embed_message:
                try:
                    await self.cog.current_embed_message.delete()
                except discord.NotFound:
                    pass
                self.cog.current_embed_message = None
            self.bot.current_running_cog = None
            await interaction.response.defer()

        @discord.ui.button(label="🔁 ループ", style=discord.ButtonStyle.secondary)
        async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.cog.is_looping = not self.cog.is_looping
            await self.cog.update_now_playing_embed(self.channel)
            await interaction.response.defer()

    async def stop_all(self):
        if self.voice_client:
            # ffmpegプロセスの強制終了（必要なら）
            try:
                if hasattr(self.voice_client, '_player') and hasattr(self.voice_client._player, '_process'):
                    process = self.voice_client._player._process
                    if process and process.poll() is None:
                        process.kill()
            except Exception as e:
                print(f"[Music.stop_all] ffmpeg強制終了失敗: {e}")

            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            try:
                # タイムアウト付きで切断
                await asyncio.wait_for(self.voice_client.disconnect(), timeout=5)
            except Exception as e:
                print(f"[Music.stop_all] VC切断失敗: {e}")
            self.voice_client = None
        self.queue.clear()
        if self.current_embed_message:
            try:
                await self.current_embed_message.delete()
            except discord.NotFound:
                pass
            self.current_embed_message = None
        self.bot.current_running_cog = None

class QueuePaginationView(discord.ui.View):
    def __init__(self, channel, cog, page, max_page):
        super().__init__(timeout=60)
        self.channel = channel
        self.cog = cog
        self.page = page
        self.max_page = max_page

    @discord.ui.button(label="⬅️ 前", style=discord.ButtonStyle.gray)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            await self.cog.PlayerControls(self.channel, self.cog).send_queue_page(interaction, self.page - 1)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="➡️ 次", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            await self.cog.PlayerControls(self.channel, self.cog).send_queue_page(interaction, self.page + 1)
        else:
            await interaction.response.defer()

async def setup(bot):
    await bot.add_cog(Music(bot))
