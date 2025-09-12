import os
import numpy as np
from dotenv import load_dotenv
from typing import Optional, cast
import io

from audio import discord_bytes_to_numpy, generate_waveform, get_loudness_str

import discord
from discord import app_commands

load_dotenv()

class MyClient(discord.Client):
    # Suppress error on the User attribute being None since it fills up later
    user: discord.ClientUser

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        TEST_GUILD = discord.Object(id=int(cast(str, os.getenv("TEST_GUILD_ID")))) # Test server

        # This copies the global commands over to your guild.
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)


intents = discord.Intents.default()
intents.message_content = True
client = MyClient(intents=intents)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Checks if user sent a audio file
    if message.attachments:
        if message.attachments[0].content_type and "audio" in message.attachments[0].content_type:
            await handle_audio_file_sent(message)


async def handle_audio_file_sent(message: discord.Message):
    # React to the file
    await message.add_reaction("\U0001F525")

    # Read the file
    data = await message.attachments[0].read()
    audio = discord_bytes_to_numpy(data, message.attachments[0].filename)

    # Generate waveform image
    color = (0.95294118, 0.48235294, 0.40784314)
    data_stream = io.BytesIO()
    generate_waveform(audio, data_stream, color=color)
    waveform_image = discord.File(data_stream, filename="audio-waveform.png")

    # Generate message
    loudness = get_loudness_str(audio)

    await message.reply(loudness, file=waveform_image, mention_author=False)


@client.tree.command()
async def hello(interaction: discord.Interaction):
    """Says hello!"""
    await interaction.response.send_message(f'Hi, {interaction.user.mention}')


client.run(cast(str, os.getenv("BOT_TOKEN")))