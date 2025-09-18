# Production Bot v2

Discord bot for music production servers.

## Running Guide

Install the necessary dependencies:

```sh
pip3 install numpy dotenv pydub discord.py matplotlib aiosqlite
sudo apt-get install ffmpeg libavcodec-extra
```

Next, create a `.env` file with the following format:
```sh
BOT_TOKEN="DISCORD BOT TOKEN GOES HERE"
```

Finally, run the `bot.py` script:

```sh
python3 bot.py
```