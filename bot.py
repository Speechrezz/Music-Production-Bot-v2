import os
import numpy as np
from dotenv import load_dotenv
from typing import Optional, cast
import io

from audio import discord_bytes_to_numpy, generate_waveform, get_loudness_info

import discord
from discord import app_commands

from database import Database

load_dotenv()

COLORS = np.array(((0.95294118, 0.48235294, 0.40784314),  # salmon/orange
                   (0.60784314, 0.51764706, 0.9254902),   # indigo/purple
                   (0.03529412, 0.69019608, 0.94901961))) # aqua/blue


class MyClient(discord.Client):
    user: discord.ClientUser
    db: Database

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    # Copy over global commands to test server, so don't have to wait an hour for them to show up
    async def setup_hook(self):
        self.tree.add_command(ActiveChannels())

        TEST_GUILD = discord.Object(id=int(cast(str, os.getenv("TEST_GUILD_ID")))) # Test server
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

intents = discord.Intents.default()
intents.message_content = True
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    client.db = await Database.new()

    # Update guilds table
    print('\n------\nUpdating guilds...')
    for guild in client.guilds:
        print(f"    {guild.name}")
        await client.db.upsert_guild(guild)

    await client.tree.sync()

    print('\n------\nReady!\n------')


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.guild is None:
        return

    # Checks if user sent a audio file
    if message.attachments:
        if message.attachments[0].content_type and "audio" in message.attachments[0].content_type:
            await handle_audio_file_sent(client, message)


async def handle_audio_file_sent(client: MyClient, message: discord.Message):
    if not isinstance(message.channel, discord.TextChannel):
        return
    
    if not await client.db.is_active_channel(message.channel):
        return

    # React to the file
    await message.add_reaction("\U0001F525")

    # Read the file
    data = await message.attachments[0].read()
    audio = discord_bytes_to_numpy(data, message.attachments[0].filename)

    # Get color
    color_index = await client.db.get_next_channel_color_index(cast(discord.TextChannel, message.channel), len(COLORS))
    color = COLORS[color_index]

    # Generate waveform image
    data_stream = io.BytesIO()
    generate_waveform(audio, data_stream, color=color)
    waveform_image = discord.File(data_stream, filename="audio-waveform.png")

    # Compute loudness
    loudness_str, loudness_lufs = get_loudness_info(audio)

    # Update database
    if loudness_lufs is not None:
        await client.db.upsert_loudness_leaderboard(message, loudness_lufs)

    await message.reply(loudness_str, file=waveform_image, mention_author=False)

@client.event
async def on_guild_join(guild: discord.Guild):
    await client.db.upsert_guild(guild)
    
@client.event
async def on_guild_remove(guild: discord.Guild):
    await client.db.delete_guild(guild)

@client.tree.command()
@app_commands.guild_only()
async def leaderboard(interaction: discord.Interaction):
    """View the loudness leaderboard."""
    if interaction.guild is None:
        return
    
    raw_leaderboard_list = await client.db.get_loudness_leaderboard(interaction.guild)
    leaderboard_list: list[list[str]] = []
    for i, raw_entry in enumerate(raw_leaderboard_list):
        try:
            member = await interaction.guild.fetch_member(raw_entry.user_id)
        except discord.NotFound:
            member = None

        username = member.display_name if member else ""
        entry = [str(i + 1), username, f"{raw_entry.loudness_lufs:.2f}", raw_entry.message_url]
        leaderboard_list.append(entry)

    output_str = "Loudness leaderboard:"
    for entry in leaderboard_list:
        output_str += f"\n{entry[0]} - {entry[1]}: {entry[2]} LUFS ({entry[3]})"

    await interaction.response.send_message(output_str)

# Active channels command group (`/active-channels`)
@app_commands.guild_only()
class ActiveChannels(app_commands.Group):
    def __init__(self):
        super().__init__(name="active-channels", description="Manage active channels")

    @app_commands.command(name="add", description="Add a channel to the active list")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, channel: discord.TextChannel | None):
        if not interaction.permissions.administrator:
            await interaction.response.send_message(f"You must be an administrator to use this command.")

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(f"Error: Channel is not a TextChannel ({type(interaction.channel)=}).")
                return
            channel = interaction.channel

        await client.db.upsert_active_channel(channel)
        await interaction.response.send_message(f"Added {channel.mention} to active channels.")

    @app_commands.command(name="remove", description="Remove a channel from the active list")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, channel: discord.TextChannel | None):
        if not interaction.permissions.administrator:
            await interaction.response.send_message(f"You must be an administrator to use this command.")

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(f"Error: Channel is not a TextChannel ({type(interaction.channel)=}).")
                return
            channel = interaction.channel

        await client.db.delete_active_channel(channel.id)
        await interaction.response.send_message(f"Removed {channel.mention} from active channels.")

    @app_commands.command(name="clear", description="Remove all channels from the active list")
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction):
        if not interaction.permissions.administrator:
            await interaction.response.send_message(f"You must be an administrator to use this command.")

        await client.db.clear_active_channels(cast(discord.Guild, interaction.guild))
        await interaction.response.send_message("Cleared all active channels.")

    @app_commands.command(name="list", description="List all channels from the active list")
    @app_commands.guild_only()
    async def list(self, interaction: discord.Interaction):
        channel_id_list = await client.db.list_active_channels(cast(discord.Guild, interaction.guild))
        channel_list: list[str] = []
        for channel_id in channel_id_list:
            channel = cast(discord.Guild, interaction.guild).get_channel(channel_id)
            if channel is None:
                await client.db.delete_active_channel(channel_id)
            else:
                channel_list.append(channel.jump_url)

        if not channel_list: # List is empty
            await interaction.response.send_message("This server has no active channels.")
        else:
            output_str = '\n'.join(channel_list)
            await interaction.response.send_message(f"Active channels:\n{output_str}")

if __name__ == "__main__":
    # if platform.system().lower() == 'windows':
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    client.run(cast(str, os.getenv("BOT_TOKEN")))