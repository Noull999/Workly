#!/usr/bin/env python3
"""
Bot de Twitch para YANGLEE
Este script se ejecuta como proceso separado y conecta al chat de Twitch.
"""

import os
import asyncio
import aiohttp
from twitchio.ext import commands

API_BASE_URL = os.environ.get('REPLIT_DEV_DOMAIN', 'http://localhost:5000')
if API_BASE_URL and not API_BASE_URL.startswith('http'):
    API_BASE_URL = f'https://{API_BASE_URL}'

TWITCH_TOKEN = os.environ.get('TWITCH_OAUTH_TOKEN', '')
TWITCH_CHANNEL = os.environ.get('TWITCH_CHANNEL', 'yanglee')


class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TWITCH_TOKEN,
            prefix='!',
            initial_channels=[TWITCH_CHANNEL]
        )

    async def event_ready(self):
        print(f'Bot conectado como: {self.nick}')
        print(f'Canal: {TWITCH_CHANNEL}')

    async def event_message(self, message):
        if message.echo:
            return

        if message.content.startswith('!'):
            await self.handle_commands(message)

    async def handle_commands(self, message):
        content = message.content.strip()
        parts = content.split(' ', 1)
        command = parts[0].lower()
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'channel': TWITCH_CHANNEL,
                    'command': command,
                    'username': message.author.name
                }
                
                async with session.post(
                    f'{API_BASE_URL}/twitch-bot/api/bot-response',
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get('response')
                        if response:
                            await message.channel.send(response)
        except Exception as e:
            print(f'Error processing command: {e}')


def main():
    if not TWITCH_TOKEN:
        print('Error: TWITCH_OAUTH_TOKEN no configurado')
        print('Obtén tu token en https://twitchapps.com/tmi/')
        return
    
    bot = Bot()
    bot.run()


if __name__ == '__main__':
    main()
