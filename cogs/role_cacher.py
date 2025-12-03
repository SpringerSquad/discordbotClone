import discord
from discord.ext import commands, tasks
import json
import os

ROLE_CACHE_PATH = "utils/roles_cache.json"

class RoleCacher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_roles.start()

    def cog_unload(self):
        self.update_roles.cancel()

    @tasks.loop(minutes=10)
    async def update_roles(self):
        for guild in self.bot.guilds:
            await self.cache_roles(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.cache_roles(guild)

    async def cache_roles(self, guild):
        role_data = [{"id": role.id, "name": role.name} for role in guild.roles if not role.managed and role.name != "@everyone"]
        os.makedirs(os.path.dirname(ROLE_CACHE_PATH), exist_ok=True)
        with open(ROLE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(role_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Rollen aus {guild.name} gecached ({len(role_data)} Rollen)")

async def setup(bot):
    await bot.add_cog(RoleCacher(bot))
