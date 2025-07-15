import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import pytz
import logging

# 日本時間
JST = pytz.timezone('Asia/Tokyo')

class GameEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_events = {}  # user_id: message_id
        self.scheduled_tasks = {}  # message_id: task

    @app_commands.command(name="game", description="ゲーム募集を開始します")
    async def game(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if user_id in self.active_events:
            await interaction.response.send_message("⚠️ すでにゲーム募集を開始しています。1人1件までです。", ephemeral=True)
            return

        modal = GameInputModal(self, interaction)
        await interaction.response.send_modal(modal)

    async def schedule_notification(self, time: datetime, message: discord.Message, view):
        try:
            now = datetime.now(JST)
            wait_time = (time - now).total_seconds()
            if wait_time > 0:
                try:
                    await asyncio.sleep(wait_time)
                except asyncio.CancelledError:
                    return  # 通知待機がキャンセルされた場合はそのまま終了

            mentions = ' '.join(member.mention for member in view.participants)
            if mentions:
                await message.channel.send(f"⏰ 時間になりました！ {mentions} そろそろゲームを始めましょう！ 🎮")
            else:
                await message.channel.send("⏰ 時間になりましたが、参加者がいませんでした。😭")

        except Exception as e:
            logging.exception("通知スケジュール中に予期せぬ例外が発生しました")
        finally:
            owner_id = view.owner_id
            self.active_events.pop(owner_id, None)
            self.scheduled_tasks.pop(message.id, None)

class GameInputModal(discord.ui.Modal, title="🎮 ゲーム募集入力"):
    game_name = discord.ui.TextInput(label="ゲーム名を入力してください", max_length=100)
    hour = discord.ui.TextInput(label="開始時刻（時 0-23）", max_length=2)
    minute = discord.ui.TextInput(label="開始時刻（分 0-59）", max_length=2)

    def __init__(self, cog, interaction):
        super().__init__()
        self.cog = cog
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        game_name = self.game_name.value.strip()
        try:
            hour = int(self.hour.value.strip())
            minute = int(self.minute.value.strip())
            if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                raise ValueError
        except ValueError:
            await interaction.response.send_message("⏰ 時刻の入力が正しくありません。0-23時、0-59分の数字で入力してください。", ephemeral=True)
            return

        now = datetime.now(JST)
        start_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start_time <= now:
            start_time += timedelta(days=1)

        embed = discord.Embed(
            title="🎮 ゲーム募集",
            description=f"**{interaction.user.display_name}** さんがゲーム募集しています！",
            color=discord.Color.blurple()
        )
        embed.add_field(name="ゲーム名", value=game_name, inline=False)
        embed.add_field(name="開始時刻", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=False)
        embed.add_field(name="参加者リスト", value="（まだ誰も参加していません）", inline=False)
        embed.set_footer(text="参加ボタンを押すと通知を受け取れます")

        view = JoinButtonView(self.cog, interaction.user.id, start_time)
        message = await interaction.channel.send(embed=embed, view=view)
        view.message = message

        task = self.cog.bot.loop.create_task(self.cog.schedule_notification(start_time, message, view))
        self.cog.scheduled_tasks[message.id] = task

        self.cog.active_events[interaction.user.id] = message.id

        await interaction.response.send_message("🎮 ゲーム募集を作成しました！", ephemeral=True)

class JoinButtonView(discord.ui.View):
    def __init__(self, cog, owner_id, start_time, message=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.owner_id = owner_id
        self.start_time = start_time
        self.participants = set()
        self.message = message

    def get_participants_display(self):
        if not self.participants:
            return "（まだ誰も参加していません）"
        return "\n".join(user.mention for user in self.participants)

    async def update_embed(self):
        if self.message:
            embed = self.message.embeds[0]
            embed.set_field_at(
                2,
                name="参加者リスト",
                value=self.get_participants_display(),
                inline=False
            )
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="✅ 参加", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return

        self.participants.add(interaction.user)
        await interaction.response.send_message(f"✅ {interaction.user.display_name} さんが参加しました！", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="❌ 辞退", style=discord.ButtonStyle.danger)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.participants:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return

        self.participants.remove(interaction.user)
        await interaction.response.send_message(f"❌ {interaction.user.display_name} さんが辞退しました。", ephemeral=True)
        await self.update_embed()

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("この操作は募集作成者のみ可能です。", ephemeral=True)
            return

        if self.message:
            mentions = " ".join(user.mention for user in self.participants)
            if mentions:
                await self.message.channel.send(f"⚠️ 募集がキャンセルされました。{mentions}")
            else:
                await self.message.channel.send("⚠️ 募集がキャンセルされました。")

        await interaction.response.send_message("募集をキャンセルしました。", ephemeral=True)
        if self.message:
            await self.message.delete()
        if self.owner_id in self.cog.active_events:
            del self.cog.active_events[self.owner_id]
        if self.message and self.message.id in self.cog.scheduled_tasks:
            task = self.cog.scheduled_tasks[self.message.id]
            task.cancel()
            del self.cog.scheduled_tasks[self.message.id]
        self.stop()

async def setup(bot):
    await bot.add_cog(GameEvent(bot))