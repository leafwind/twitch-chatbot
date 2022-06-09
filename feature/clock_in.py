import logging
import os

import mysql.connector
from dotenv import load_dotenv

from utils import filter_feature_toggle, whisper

load_dotenv()


@filter_feature_toggle
def clock_in(bot, user_id, user_name):
    config = {
        "user": os.environ.get("MYSQL_USER"),
        "password": os.environ.get("MYSQL_PASSWORD"),
    }
    cnx = mysql.connector.connect(**config)
    cur = cnx.cursor(buffered=True)
    cur.execute(
        f"INSERT INTO twitch.clock_in (channel, user_id) VALUES (%s, %s)",
        (bot.channel_id, user_id),
    )
    cur.close()
    cnx.commit()
    cnx.close()
    whisper(
        bot.connection,
        bot.irc_channel,
        user_id,
        f"{user_name} 簽到 {bot.channel_id} 成功",
    )
    logging.info(f"{user_id} 簽到 {bot.channel_id} 成功")
