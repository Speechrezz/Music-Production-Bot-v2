-- Servers/guilds
CREATE TABLE IF NOT EXISTS guilds (
  guild_id INTEGER PRIMARY KEY,
  guild_name TEXT NOT NULL
);

-- All channels that audio files have been sent in
CREATE TABLE IF NOT EXISTS channels (
  channel_id INTEGER PRIMARY KEY,
  guild_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  color_index INTEGER DEFAULT 0,
  FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);

-- Whitelisted active channels
CREATE TABLE IF NOT EXISTS active_channels (
  channel_id INTEGER PRIMARY KEY,
  FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
);

-- Unique users (across all guilds)
CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL
);

-- Loudness leaderboard (unique per guilds)
CREATE TABLE IF NOT EXISTS loudness_leaderboard (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  loudness_lufs REAL NOT NULL,
  message_url TEXT NOT NULL,     -- Link to the message
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (guild_id, user_id),
  FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);