import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import requests
import json
import os
import aiohttp
import re
import mimetypes
import config

VOICEVOX_PATH = config.VOICEVOX_PATH
FFMPEG_PATH = config.FFMPEG_PATH
VOICEVOX_PORT = 50021
SETTINGS_FILE = config.SETTINGS_PATH

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"設定ファイル読み込みエラー: {e}")
    return {"user_profiles": {}, "volume": 0.5}

def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"設定ファイル保存エラー: {e}")

settings = load_settings()

with open("memory/SPEAKER_DATA.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)
    SPEAKER_DATA = {
        item["name"]: {
            "styles": item["styles"]
        }
        for item in raw_data
    }

class StyleSelect(discord.ui.Select):
    def __init__(self, speaker_name):
        options = [
            discord.SelectOption(label=style["name"], value=str(style["id"]))
            for style in SPEAKER_DATA[speaker_name]["styles"]
        ]
        super().__init__(placeholder="スタイルを選択してください", min_values=1, max_values=1, options=options)
        self.speaker_name = speaker_name

    async def callback(self, interaction: discord.Interaction):
        style_id = int(self.values[0])
        style_name = None
        
        for style in SPEAKER_DATA[self.speaker_name]["styles"]:
            if style["id"] == style_id:
                style_name = style["name"]
                break
        
        uid = str(interaction.user.id)
        profile = settings.setdefault("user_profiles", {}).setdefault(uid, {})
        profile["speaker_name"] = self.speaker_name
        profile["style_id"] = style_id
        save_settings(settings)
        
        if style_name:
            await interaction.response.send_message(
                f"話者「{self.speaker_name}」のスタイル「{style_name}」に設定しました。", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"話者「{self.speaker_name}」のスタイルを設定しました。", ephemeral=True
            )
class SpeakerSelect(discord.ui.Select):
    def __init__(self, page=0, per_page=25):
        self.page = page
        self.per_page = per_page
        names = list(SPEAKER_DATA.keys())
        start = page * per_page
        end = start + per_page
        options = [
            discord.SelectOption(label=name, value=name)
            for name in names[start:end]
        ]
        super().__init__(placeholder="話者を選択してください", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        speaker_name = self.values[0]
        view = discord.ui.View()
        view.add_item(StyleSelect(speaker_name))
        await interaction.response.send_message(
            f"話者「{speaker_name}」のスタイルを選択してください。", view=view, ephemeral=True
        )

class SpeakerPageView(discord.ui.View):
    def __init__(self, page=0, per_page=25):
        super().__init__(timeout=None)
        self.page = page
        self.per_page = per_page
        self.add_item(SpeakerSelect(page=page, per_page=per_page))
        names = list(SPEAKER_DATA.keys())
        max_page = (len(names) - 1) // per_page
        if page > 0:
            self.add_item(self.PrevButton(page, per_page))
        if page < max_page:
            self.add_item(self.NextButton(page, per_page))

    class PrevButton(discord.ui.Button):
        def __init__(self, page, per_page):
            super().__init__(label="前へ", style=discord.ButtonStyle.secondary)
            self.page = page
            self.per_page = per_page

        async def callback(self, interaction: discord.Interaction):
            view = SpeakerPageView(page=self.page - 1, per_page=self.per_page)
            await interaction.response.send_message("話者を選択してください。", view=view, ephemeral=True)

    class NextButton(discord.ui.Button):
        def __init__(self, page, per_page):
            super().__init__(label="次へ", style=discord.ButtonStyle.secondary)
            self.page = page
            self.per_page = per_page

        async def callback(self, interaction: discord.Interaction):
            view = SpeakerPageView(page=self.page + 1, per_page=self.per_page)
            await interaction.response.send_message("話者を選択してください。", view=view, ephemeral=True)

class VoiceSettingsView(discord.ui.View):
    def __init__(self, parent_cog=None, message=None):
        super().__init__(timeout=None)
        self.parent_cog = parent_cog
        self.message = message

    @discord.ui.button(label="話者変更", style=discord.ButtonStyle.primary)
    async def change_speaker(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SpeakerPageView(page=0, per_page=25)
        await interaction.response.send_message("話者を選択してください。", view=view, ephemeral=True)

    @discord.ui.button(label="🔊音量↑", style=discord.ButtonStyle.success)
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            settings["volume"] = min(settings.get("volume", 0.5) + 0.1, 1.0)
            save_settings(settings)
            await self.parent_cog.send_panel(interaction.channel, self)
            await interaction.response.send_message(f"音量を {int(settings['volume']*100)}% に上げました", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"音量変更エラー: {e}", ephemeral=True)

    @discord.ui.button(label="🔉音量↓", style=discord.ButtonStyle.danger)
    async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            settings["volume"] = max(settings.get("volume", 0.5) - 0.1, 0.0)
            save_settings(settings)
            await self.parent_cog.send_panel(interaction.channel, self)
            await interaction.response.send_message(f"音量を {int(settings['volume']*100)}% に下げました", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"音量変更エラー: {e}", ephemeral=True)

    @discord.ui.button(label="❌切断", style=discord.ButtonStyle.secondary)
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if self.parent_cog and interaction.guild.voice_client:
                await interaction.guild.voice_client.disconnect()
                self.parent_cog.tts_task = None
                self.parent_cog.bot.current_running_cog = None
                if self.message:
                    try:
                        await self.message.delete()
                    except Exception:
                        pass
                guild_id = str(interaction.guild.id)
                channel_id = str(interaction.channel.id)
                if guild_id in self.parent_cog.panel_info and channel_id in self.parent_cog.panel_info[guild_id]:
                    del self.parent_cog.panel_info[guild_id][channel_id]
                    if not self.parent_cog.panel_info[guild_id]:
                        del self.parent_cog.panel_info[guild_id]
                self.parent_cog.panel_view = None
                await interaction.response.send_message("❌ 読み上げを終了しました", ephemeral=True)
            else:
                await interaction.response.send_message("BotはVCに参加していません", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"切断エラー: {e}", ephemeral=True)

    async def refresh_panel(self, interaction, status_text):
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass
        new_msg = await interaction.channel.send(status_text, view=self)
        self.message = new_msg
        await interaction.response.defer()

class Join(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tts_queue = asyncio.Queue()
        self.tts_task = None
        self.cancel_event = asyncio.Event()
        self.last_message_id = None
        self.panel_info = {}
        self.panel_content = "✅ VCに接続しました。設定はこちら:"
        self.panel_view = None
        self.panel_watcher.start()

        if not hasattr(self.bot, "current_running_cog"):
            self.bot.current_running_cog = None

    async def ensure_no_conflict(self, interaction):
        if self.bot.current_running_cog and self.bot.current_running_cog != "Join":
            await interaction.response.send_message("他の機能（Music）が実行中です。停止してから使ってください。", ephemeral=True)
            return False
        self.bot.current_running_cog = "Join"
        return True

    async def send_panel(self, channel, view):
        guild_id = str(channel.guild.id)
        channel_id = str(channel.id)
        if guild_id in self.panel_info and channel_id in self.panel_info[guild_id]:
            try:
                msg_id = self.panel_info[guild_id][channel_id]["message_id"]
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
            except Exception:
                pass
        sent_msg = await channel.send(self.panel_content, view=view)
        if guild_id not in self.panel_info:
            self.panel_info[guild_id] = {}
        self.panel_info[guild_id][channel_id] = {"message_id": sent_msg.id}
        self.panel_view = view
        view.message = sent_msg

    @app_commands.command(name="join", description="VCにBotを参加させます")
    async def join_slash(self, interaction: discord.Interaction):
        try:
            if not await self.ensure_no_conflict(interaction):
                return
            if not interaction.user.voice:
                await interaction.response.send_message("❌ VCに参加してから実行してください", ephemeral=True)
                return
            try:
                if interaction.guild.voice_client:
                    await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
                else:
                    await interaction.user.voice.channel.connect()
            except Exception as e:
                await interaction.response.send_message(f"VC接続エラー: {e}", ephemeral=True)
                return
            uid = str(interaction.user.id)
            profile = settings.setdefault("user_profiles", {}).setdefault(uid, {})
            if "speaker_name" not in profile:
                profile["speaker_name"] = "四国めたん"
            if "style_id" not in profile:
                profile["style_id"] = 2
            save_settings(settings)

            view = VoiceSettingsView(parent_cog=self)
            await self.send_panel(interaction.channel, view)
            await interaction.response.send_message("接続しました。", ephemeral=True)

            if not self.tts_task or self.tts_task.done():
                self.tts_task = asyncio.create_task(self.tts_worker(interaction.guild))
        except Exception as e:
            await interaction.response.send_message(f"コマンド実行エラー: {e}", ephemeral=True)

    @app_commands.command(name="voice_settings", description="自分の話者・音量設定を変更します")
    async def voice_settings_slash(self, interaction: discord.Interaction):
        view = VoiceSettingsView(parent_cog=self)
        await self.send_panel(interaction.channel, view)
        await interaction.response.send_message("接続しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            running_cog = getattr(self.bot, "current_running_cog", None)
            if running_cog and running_cog != "Join":
                return
            if message.author.bot:
                return
            if self.last_message_id == message.id:
                return
            self.last_message_id = message.id

            voice_client = message.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                return
            if message.content.strip() == "ｓ":
                if voice_client.is_playing():
                    voice_client.stop()
                    self.cancel_event.set()
                return

            uid = str(message.author.id)
            profile = settings.get("user_profiles", {}).get(uid, {})
            speaker_name = profile.get("speaker_name", "四国めたん")
            style_id = profile.get("style_id", 2)

            if "speaker_name" not in profile and "speaker_id" in profile:
                speaker_name = "四国めたん"
                style_id = 2

            text = message.content
            url_pattern = r'https?://[^\s]+'
            if re.search(url_pattern, text):
                text = re.sub(url_pattern, 'ユーアールエル', text)
            if message.attachments:
                for attachment in message.attachments:
                    mime, _ = mimetypes.guess_type(attachment.filename)
                    if mime:
                        if mime.startswith("image/"):
                            text += " 画像が送信されました"
                        elif mime.startswith("video/"):
                            text += " 動画が送信されました"
                        elif mime.startswith("audio/"):
                            text += " 音声ファイルが送信されました"
                        else:
                            text += " ファイルが送信されました"
                    else:
                        text += " ファイルが送信されました"
            if message.mentions:
                text += " メンションがありました"
            if message.stickers:
                text += " スタンプが送信されました"

            await self.tts_queue.put((message.guild, style_id, text))

            if not self.tts_task or self.tts_task.done():
                self.tts_task = asyncio.create_task(self.tts_worker(message.guild))
        except Exception as e:
            print(f"on_message例外: {e}")

    async def tts_worker(self, guild):
        self.bot.current_running_cog = "Join"
        try:
            while True:
                try:
                    try:
                        guild_obj, style_id, text = await self.tts_queue.get()
                    except asyncio.CancelledError:
                        print("TTSワーカーがキャンセルされました（Bot停止/再起動/手動キャンセル）。安全に終了します。")
                        break
                    voice_client = guild_obj.voice_client
                    if not voice_client or not voice_client.is_connected():
                        continue

                    self.cancel_event.clear()

                    async with aiohttp.ClientSession() as session:
                        try:
                            async with session.post(
                                f"http://localhost:{VOICEVOX_PORT}/audio_query",
                                params={"text": text, "speaker": style_id}
                            ) as query_resp:
                                query_resp.raise_for_status()
                                query = await query_resp.json()
                        except Exception as exc:
                            print(f"VOICEVOX audio_queryエラー: {exc}")
                            continue

                        query["volumeScale"] = settings.get("volume", 0.5)

                        try:
                            async with session.post(
                                f"http://localhost:{VOICEVOX_PORT}/synthesis",
                                params={"speaker": style_id},
                                json=query
                            ) as synth_resp:
                                synth_resp.raise_for_status()
                                audio = await synth_resp.read()
                        except Exception as exc:
                            print(f"VOICEVOX synthesisエラー: {exc}")
                            continue

                    try:
                        with open("output.wav", "wb") as f:
                            f.write(audio)
                    except Exception as exc:
                        print(f"音声ファイル保存エラー: {exc}")
                        continue

                    try:
                        source = discord.FFmpegPCMAudio("output.wav", executable=FFMPEG_PATH)
                    except Exception as exc:
                        print(f"FFmpeg音源生成エラー: {exc}")
                        continue

                    finished = asyncio.Event()

                    def after_playing(error):
                        finished.set()

                    try:
                        if voice_client.is_playing():
                            voice_client.stop()
                        voice_client.play(source, after=after_playing)
                    except Exception as exc:
                        print(f"音声再生エラー: {exc}")
                        continue
                    try:
                        done, _ = await asyncio.wait(
                            [finished.wait(), self.cancel_event.wait()],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                    except Exception as exc:
                        print(f"再生待機エラー: {exc}")
                except Exception as exc:
                    print(f"読み上げエラー: {exc}")
                finally:
                    self.tts_queue.task_done()
        finally:
            self.bot.current_running_cog = None

    @tasks.loop(seconds=5)
    async def panel_watcher(self):
        for guild_id, channels in self.panel_info.items():
            for channel_id, info in channels.items():
                try:
                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        continue
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        continue
                    last_msg = None
                    async for msg in channel.history(limit=1):
                        last_msg = msg
                        break
                    if not last_msg or last_msg.id != info.get("message_id"):
                        try:
                            old_msg = await channel.fetch_message(info.get("message_id"))
                            await old_msg.delete()
                        except Exception:
                            pass
                        if self.panel_view:
                            sent_msg = await channel.send(self.panel_content, view=self.panel_view)
                            info["message_id"] = sent_msg.id
                            self.panel_view.message = sent_msg
                except Exception as e:
                    print(f"[panel_watcher] 監視ループ例外: {e}")

    @panel_watcher.before_loop
    async def before_panel_watcher(self):        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Join(bot))