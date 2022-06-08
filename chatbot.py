"""
Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/apache2.0/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""
import logging
import math
import multiprocessing
import os
import random
import re
import signal
import sys
import time

import dill
import irc.bot
import yaml
from expiringdict import ExpiringDict

from logger import set_logger

# from twitch_api_client import TwitchAPIClient
from utils import (
    filter_feature_toggle,
    uma_call,
    talk,
    send,
    say_hi,
    normalize_duplicated_str,
)


with open("config/target_channels.yml") as f:
    TARGET_CHANNELS = yaml.full_load(f)

with open("config/trend_words.yml") as f:
    TREND_WORDS = yaml.full_load(f)
    TREND_WORDS_SUBSTRING = TREND_WORDS["substring"]
    TREND_WORDS_EXACT_MATCH = TREND_WORDS["exact_match"]

with open("config/channel_clips.yml", "r") as f:
    CHANNEL_CLIPS = yaml.full_load(f)
SERVER = "irc.chat.twitch.tv"
PORT = 6667

# !船來了 指令：BOARDING_PERIOD 為上船等待時間、BAN_PERIOD 為懲罰時間
BOARDING_PERIOD = 60
BAN_PERIOD = 300

# Trending tokens will be expired in TREND_EXPIRE_SEC seconds
TREND_EXPIRE_SEC = 15

set_logger()
logger = logging.getLogger(__name__)


class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, username, token, channel_id):
        self.user_id = username
        self.token = token.removeprefix("oauth:")
        self.irc_channel = "#" + channel_id.lower()
        self.channel_id = channel_id
        self.serialized_data_dir = "data"
        self.serialized_data_filename = os.path.join(
            self.serialized_data_dir, f"{self.channel_id}.bin"
        )
        self.push_trend_cache = ExpiringDict(
            max_len=100, max_age_seconds=TREND_EXPIRE_SEC
        )

        self.dizzy_users = []
        self.dizzy_start_ts = 0
        self.dizzy_ban_end_ts = 0
        self.ban_targets = []

        # self.api_client = TwitchAPIClient(self.channel_id, client_id)

        # Create IRC bot connection
        logger.info(f"Connecting to {self.irc_channel}...")
        irc.bot.SingleServerIRCBot.__init__(
            self,
            [(SERVER, PORT, "oauth:" + self.token)],
            username,
            username,
            # the default backoff config is min_interval=60, max_interval=300, which is too long.
            recon=irc.bot.ExponentialBackoff(min_interval=3, max_interval=10),
        )
        # TODO: dynamically determine
        self.trend_threshold = 3

        self.gbf_code_re = re.compile(r"[A-Z0-9]{8}")

        # setup scheduler
        self.reactor.scheduler.execute_every(1, self.dizzy)
        # self.reactor.scheduler.execute_every(5 * 60, self.insert_all)
        # self.reactor.scheduler.execute_every(60 * 60, self.share_clip)

        # load data in disk
        # try:
        #     with open(self.serialized_data_filename, "rb") as f:
        #         self.data = dill.loads(f.read())
        #         if "gbf_room_num" not in self.data:
        #             self.data["gbf_room_num"] = 0
        #         if "gbf_room_id_cache" not in self.data:
        #             self.data["gbf_room_id_cache"] = ExpiringDict(
        #                 max_len=1, max_age_seconds=600
        #             )
        # except FileNotFoundError:
        #     self.data = {
        #         "gbf_room_num": 0,
        #         "gbf_room_id_cache": ExpiringDict(max_len=1, max_age_seconds=600),
        #     }

        # register signal handler
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        # signal.signal(signal.SIGINT, handler=self.save_data)

    # def save_data(self, sig, frame):
    #     logger.info("pressed Ctrl+C! dumping variables...")
    #     try:
    #         with open(self.serialized_data_filename, "wb") as f:
    #             f.write(dill.dumps(self.data))
    #     except FileNotFoundError:
    #         os.makedirs(self.serialized_data_dir)
    #     sys.exit(0)

    def trend_talking(self, conn, msg):
        # partial matching
        for word in TREND_WORDS_SUBSTRING:
            if word in msg:
                if word not in self.push_trend_cache:
                    self.push_trend_cache[word] = 1
                else:
                    self.push_trend_cache[word] += 1
                logger.info(f"[COUNTER] {word}:{ self.push_trend_cache[word]}")
                if self.push_trend_cache[word] >= self.trend_threshold:
                    talk(conn, self.irc_channel, word)
                    self.push_trend_cache[word] = -10
        # full matching
        if msg in TREND_WORDS_EXACT_MATCH:
            if msg not in self.push_trend_cache:
                self.push_trend_cache[msg] = 1
            else:
                self.push_trend_cache[msg] += 1
            logger.info(f"[COUNTER] {msg}:{ self.push_trend_cache[msg]}")
            if self.push_trend_cache[msg] >= self.trend_threshold:
                talk(conn, self.irc_channel, msg)

    @filter_feature_toggle
    def dizzy(self):
        now = int(time.time())
        if self.dizzy_start_ts == 0:
            return
        if self.dizzy_ban_end_ts == 0 and self.dizzy_start_ts + BOARDING_PERIOD < now:
            if not self.dizzy_users:
                logger.info(f"沒人上船，開船失敗！")
                send(self.connection, self.irc_channel, f"沒人上船，開船失敗！")
                self.dizzy_users = []
                self.ban_targets = []
                self.dizzy_start_ts = 0
                self.dizzy_ban_end_ts = 0
            else:
                n_dizzy_users = (
                    1
                    if len(self.dizzy_users) < 20
                    else math.ceil(len(self.dizzy_users) * 0.05)
                )
                self.ban_targets = random.sample(self.dizzy_users, n_dizzy_users)
                ban_targets_str = ", ".join([f"@{t}" for t in self.ban_targets])
                logger.info(f"抓到了 {ban_targets_str} 你就是暈船仔！")
                send(
                    self.connection,
                    self.irc_channel,
                    f"抓到了 {ban_targets_str} 你就是暈船仔！我看你五分鐘內都會神智不清亂告白，只好幫你湮滅證據了。",
                )
                self.dizzy_ban_end_ts = (
                    self.dizzy_start_ts + BOARDING_PERIOD + BAN_PERIOD
                )
        elif now <= self.dizzy_ban_end_ts:
            ban_targets_str = ", ".join([f"@{t}" for t in self.ban_targets])
            logger.info(f"暈船仔 {ban_targets_str} 還在暈")
        elif now > self.dizzy_ban_end_ts > 0:
            ban_targets_str = ", ".join([f"@{t}" for t in self.ban_targets])
            logger.info(f"放 {ban_targets_str} 下船")
            send(self.connection, self.irc_channel, f"放 {ban_targets_str} 下船")
            self.dizzy_users = []
            self.ban_targets = []
            self.dizzy_start_ts = 0
            self.dizzy_ban_end_ts = 0
        else:
            logger.info(
                f"now: {now}, dizzy_start_ts: {self.dizzy_start_ts}, dizzy_ban_end_ts: {self.dizzy_ban_end_ts}"
            )

    # @filter_feature_toggle
    # def share_clip(self):
    #     if self.channel_id not in CHANNEL_CLIPS:
    #         logger.info(
    #             f"{self.channel_id} is not in {CHANNEL_CLIPS.keys()}, skip share clip"
    #         )
    #         return
    #     if not self.api_client.check_stream_online():
    #         logger.info("channel is offline, skip share clip")
    #         return
    #     clip = random.choice(CHANNEL_CLIPS[self.channel_id])
    #     talk(
    #         self.connection,
    #         self.irc_channel,
    #         f"{clip['title']} {clip['url']}",
    #     )

    # @filter_feature_toggle
    # def insert_all(self):
    #     if not self.api_client.check_stream_online():
    #         logger.info("channel is offline, skip sending !insertall")
    #         return
    #     logger.info('channel is online! send chat: "!insertall"')
    #     talk(self.connection, self.irc_channel, "!insertall")

    def on_welcome(self, conn, e):
        logger.info("Joining " + self.irc_channel)

        # You must request specific capabilities before you can use them
        conn.cap("REQ", ":twitch.tv/membership")
        conn.cap("REQ", ":twitch.tv/tags")
        conn.cap("REQ", ":twitch.tv/commands")
        conn.join(self.irc_channel)
        logger.info("Joined " + self.irc_channel)

    def on_pubmsg(self, conn, e):
        msg = normalize_duplicated_str(e.arguments[0])

        user_id = e.source.split("!")[0]
        user_name = e.tags[4]["value"]
        is_mod = e.tags[8]["value"]
        is_subscriber = e.tags[10]["value"]
        timestamp_ms = e.tags[11]["value"]

        # clock in
        if msg == "CLOCKIN":
            send(conn, user_id, "已經簽到！")

        # do not talk to myself
        if user_id != self.user_id:
            say_hi(conn, self.irc_channel, self.channel_id, user_id, user_name)
        logger.info(f"{self.channel_id} | {user_id:>14}: {msg}")
        if user_id in self.ban_targets:
            time.sleep(3)
            send(conn, self.irc_channel, f"/timeout {user_id} 1")
            logger.info(f"/timeout {user_id} 1")

        self.trend_talking(conn, msg=msg)

        if msg.startswith("!"):
            cmd = msg.split(" ")[0][1:]
            logger.info("Received command: " + cmd)
            self.do_command(cmd, user_id)
        if msg == "馬娘":
            uma_call(conn, self.irc_channel, self.channel_id, user_name)
        return

    def do_command(self, cmd, user_id):
        if cmd == "船來了":
            if user_id != self.channel_id:
                logger.info(f"沒有權限")
                return
            now = int(time.time())
            if now <= self.dizzy_ban_end_ts:
                logger.info(f"還在上一次暈船懲罰中喔")
                return
            send(
                self.connection,
                self.irc_channel,
                f"在一分鐘內輸入 !上船 讓溫泉蛋找出誰是暈船仔，被抓到的暈船仔會不斷在三秒後被消音，直到五分鐘結束為止",
            )
            self.dizzy_start_ts = now
            logger.info(f"開始登記上船時間為 {self.dizzy_start_ts}")
        if cmd == "上船":
            now = int(time.time())
            if self.dizzy_start_ts == 0:
                logger.info(f"船還沒來喔！")
                return
            if now > self.dizzy_start_ts + BOARDING_PERIOD:
                logger.info(
                    f"現在是 {now} 已經超過上船時間 {self.dizzy_start_ts + BOARDING_PERIOD}"
                )
                return
            if user_id in self.dizzy_users:
                logger.info(f"{user_id} 已經在船上了！")
                return
            self.dizzy_users.append(user_id)
            logger.info(f"乘客 {user_id} 成功上船！")
            send(self.connection, self.irc_channel, f"乘客 {user_id} 成功上船！")


def spawn_bot(channel_id):
    username = sys.argv[1]
    token = sys.argv[2]

    bot = TwitchBot(username, token, channel_id)
    bot.start()


def main():
    if len(sys.argv) != 3:
        logger.info("Usage: chatbot <username> <token>")
        sys.exit(1)

    for channel in TARGET_CHANNELS:
        p = multiprocessing.Process(target=spawn_bot, args=(channel["id"],))
        p.start()


if __name__ == "__main__":
    main()
