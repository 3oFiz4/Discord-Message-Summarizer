from models.message.message import MessageDTO
from models.message.message_collection import MessageCollection
from datetime import datetime
from config import config

"""
config.DISCORD_TOKE: env
"""

import discord as dc

class Client(dc.Client):
    async def on_ready(self):
        close = False
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        # only respond to ourselves
        if message.author != self.user:
            return

        if message.content == '&test':
            await message.channel.send('Hello World!')
        
        if message.content == '&close':
            close = True

        if close:
            await self.close()


Client().run(config.DISCORD_TOKEN)
