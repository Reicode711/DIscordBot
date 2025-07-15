import random
import datetime
import json
import os
import discord
from discord import app_commands
from discord.ext import commands
import config  # 追加

USAGE_FILE = config.FORTUNE_USAGE_PATH
ITEMS_FILE = config.LUCKY_ITEMS_PATH
MESSAGES_FILE = config.FORTUNE_MESSAGES_PATH

class Fortune(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.usage_log = self.load_usage_log()
        self.lucky_items = self.load_json(ITEMS_FILE)
        self.fortune_messages = self.load_json(MESSAGES_FILE)

    def load_usage_log(self):
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_usage_log(self):
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.usage_log, f, ensure_ascii=False, indent=2)

    def load_json(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            print(f"⚠️ {path} が見つかりません")
            return []

    @app_commands.command(name="fortune", description="今日の運勢を占います（1日1回）")
    async def fortune(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        today_str = str(datetime.date.today())

        if user_id in self.usage_log and self.usage_log[user_id] == today_str:
            await interaction.response.send_message("⚠️ 今日の運勢はもう引きました！明日また試してみてね。", ephemeral=True)
            return

        self.usage_log[user_id] = today_str
        self.save_usage_log()

        fortunes = [
            ("超大吉", 0.001),
            ("大吉", 0.1),
            ("中吉", 0.22),
            ("小吉", 0.2),
            ("吉", 0.2),
            ("凶", 0.15),
            ("大凶", 0.129),
        ]

        r = random.random()
        cum_prob = 0
        for fortune, prob in fortunes:
            cum_prob += prob
            if r <= cum_prob:
                chosen = fortune
                break

        lucky_item = random.choice(self.lucky_items) if self.lucky_items else "ラッキーアイテムなし"
        message = random.choice(self.fortune_messages) if self.fortune_messages else "良い一日を！"

        await interaction.response.send_message(
            f"🎯 今日の運勢は **{chosen}** です！\n"
            f"🍀 ラッキーアイテム: **{lucky_item}**\n"
            f"💡 一言メッセージ: {message}"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Fortune(bot))
