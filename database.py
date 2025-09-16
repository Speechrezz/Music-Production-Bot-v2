import aiosqlite
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import discord

@dataclass
class LeaderboardEntry:
    guild_id: int
    user_id: int
    loudness_lufs: float
    message_url: str
    timestamp: str

@dataclass
class Database:
    sql: aiosqlite.Connection
    scripts_path = Path("sql")

    @staticmethod
    async def new(path=Path("bot.db")):
        needs_initialization = not path.exists()

        sql = await aiosqlite.connect(path)
        database = Database(sql=sql)

        if needs_initialization:
            await database.initialize()

        return database
    
    async def execute_script_from_path(self, script_path: Path):
        with open(script_path, "r") as f:
            sql_script = f.read()

        statement_list = sql_script.strip().split(";")
        for statement in statement_list:
            statement = statement.strip()
            if statement:  # Skip empty statements
                await self.sql.execute(statement)

        await self.sql.commit()

    async def initialize(self):
        init_script_path = self.scripts_path / "init_db.sql"
        await self.execute_script_from_path(init_script_path)

        print(f"Database initialized ({init_script_path})")


    # ---Guild---

    async def upsert_guild(self, guild: discord.Guild):
        await self.sql.execute("""
            INSERT INTO guilds (guild_id, guild_name)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                guild_name = excluded.guild_name
        """, (guild.id, guild.name))
        await self.sql.commit()

    async def delete_guild(self, guild: discord.Guild):
        await self.sql.execute("DELETE FROM guilds WHERE guild_id = ?", (guild.id,))
        await self.sql.commit()


    # ---Channel---

    async def upsert_channel(self, channel: discord.TextChannel):
        await self.sql.execute("""
            INSERT INTO channels (channel_id, guild_id, channel_name)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_name = excluded.channel_name
        """, (channel.id, channel.guild.id, channel.name))
        await self.sql.commit()

    async def delete_channel(self, channel: discord.TextChannel):
        await self.sql.execute("DELETE FROM channels WHERE channel_id = ?", (channel.id,))
        await self.sql.commit()

    async def get_next_channel_color_index(self, channel: discord.TextChannel, max_index: int):
        await self.upsert_channel(channel)
        cursor = await self.sql.execute("SELECT color_index FROM channels WHERE channel_id = ?", (channel.id,))
        row = await cursor.fetchone()
        if row is None:
            return 0
        
        current_index: int = row[0]
        new_index = (current_index + 1) % max_index

        await self.sql.execute("UPDATE channels SET color_index = ? WHERE channel_id = ?", (new_index, channel.id))
        await self.sql.commit()

        return current_index
    

    # ---Active Channel---

    async def upsert_active_channel(self, channel: discord.TextChannel):
        await self.upsert_channel(channel)
        await self.sql.execute("""
            INSERT INTO active_channels (channel_id)
            VALUES (?)
            ON CONFLICT(channel_id) DO NOTHING
        """, (channel.id,))
        await self.sql.commit()

    async def delete_active_channel(self, channel_id: int):
        await self.sql.execute("DELETE FROM active_channels WHERE channel_id = ?", (channel_id,))
        await self.sql.commit()

    async def list_active_channels(self, guild: discord.Guild) -> list[int]:
        async with self.sql.execute("""
            SELECT ac.channel_id
            FROM active_channels ac
            JOIN channels c ON ac.channel_id = c.channel_id
            WHERE c.guild_id = ?
        """, (guild.id,)) as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def clear_active_channels(self, guild: discord.Guild):
        await self.sql.execute("""
            DELETE FROM active_channels
            WHERE channel_id IN (
                SELECT c.channel_id
                FROM channels c
                WHERE c.guild_id = ?
            )
        """, (guild.id,))
        await self.sql.commit()

    # Will return True if guild does not have any active channels
    async def is_active_channel(self, channel: discord.TextChannel):
        # Step 1: Check if the guild has any active channels
        cursor = await self.sql.execute("""
            SELECT 1 FROM active_channels
            JOIN channels USING (channel_id)
            WHERE channels.guild_id = ?
            LIMIT 1
        """, (channel.guild.id,))
        has_any_active = await cursor.fetchone()

        if not has_any_active:
            return True

        # Step 2: Check if the given channel is active
        cursor = await self.sql.execute("""
            SELECT 1 FROM active_channels WHERE channel_id = ?
        """, (channel.id,))
        result = await cursor.fetchone()
        return result is not None
    

    # ---Users---

    async def upsert_user(self, user: discord.User):
        await self.sql.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username
        """, (user.id, user.name))
        await self.sql.commit()

    async def delete_user(self, user: discord.User):
        await self.sql.execute("DELETE FROM users WHERE user_id = ?", (user.id,))
        await self.sql.commit()


    # ---Loudness Leaderboard---
    
    async def upsert_loudness_leaderboard(self, message: discord.Message, loudness_lufs: float):
        if message.guild is None:
            raise TypeError("Message does not have a Guild")

        await self.upsert_user(cast(discord.User, message.author))

        await self.sql.execute("""
            INSERT INTO loudness_leaderboard (guild_id, user_id, loudness_lufs, message_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE
            SET loudness_lufs = excluded.loudness_lufs,
                message_url = excluded.message_url,
                timestamp = CURRENT_TIMESTAMP
            WHERE excluded.loudness_lufs > loudness_leaderboard.loudness_lufs
        """, (message.guild.id, message.author.id, loudness_lufs, message.jump_url))
        await self.sql.commit()

    async def get_loudness_leaderboard(self, guild: discord.Guild, limit: int = 10, offset: int = 0):
        cursor = await self.sql.execute("""
            SELECT guild_id, user_id, loudness_lufs, message_url, timestamp
            FROM loudness_leaderboard
            WHERE guild_id = ?
            ORDER BY loudness_lufs DESC
            LIMIT ? OFFSET ?
        """, (guild.id, limit, offset))
        data = await cursor.fetchall()
        return [LeaderboardEntry(*row) for row in data]
    
    async def get_user_rank(self, guild: discord.Guild, user: discord.User):
        cursor = await self.sql.execute("""
            SELECT rank, guild_id, user_id, loudness_lufs, message_url, timestamp
            FROM (
                SELECT
                    guild_id,
                    user_id,
                    loudness_lufs,
                    message_url,
                    timestamp,
                    RANK() OVER (
                        PARTITION BY guild_id
                        ORDER BY loudness_lufs DESC
                    ) AS rank
                FROM loudness_leaderboard
            )
            WHERE guild_id = ? AND user_id = ?
        """, (guild.id, user.id))
        return await cursor.fetchone()



if __name__ == "__main__":
    import sqlite3

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    print("SELECT * FROM guilds:")
    cursor.execute("SELECT * FROM guilds")
    for row in cursor.fetchall():
        print(row)

    print("\nSELECT * FROM channels:")
    cursor.execute("SELECT * FROM channels")
    for row in cursor.fetchall():
        print(row)

    print("\nSELECT * FROM active_channels:")
    cursor.execute("SELECT * FROM active_channels")
    for row in cursor.fetchall():
        print(row)

    print("\nSELECT * FROM users:")
    cursor.execute("SELECT * FROM users")
    for row in cursor.fetchall():
        print(row)

    print("\nSELECT * FROM loudness_leaderboard:")
    cursor.execute("SELECT * FROM loudness_leaderboard")
    for row in cursor.fetchall():
        print(row)