import aiosqlite
from dataclasses import dataclass

@dataclass
class Database:
    sql: aiosqlite.Connection

    async def new(path="bot.db"):
        sql = await aiosqlite.connect(path)
        return Database(sql=sql)