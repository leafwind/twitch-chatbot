"""
Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/apache2.0/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""
import dill
import irc.bot
import logging
import os
import random
import re
import signal
import sys
import time
import yaml
from expiringdict import ExpiringDict

# from twitch_api_client import TwitchAPIClient
from utils import filter_feature_toggle, uma_call, talk, say_hi, normalize_message

logging.basicConfig(level=logging.INFO)

with open("trend_words.yml") as f:
    TREND_WORDS = yaml.full_load(f)
    TREND_WORDS_SUBSTRING = TREND_WORDS["substring"]
    TREND_WORDS_EXACT_MATCH = TREND_WORDS["exact_match"]

with open("channel_clips.yml", "r") as f:
    CHANNEL_CLIPS = yaml.full_load(f)
SERVER = "irc.chat.twitch.tv"
PORT = 6667

ONBOARDING_PERIOD = 60
BAN_PERIOD = 300


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
        self.push_trend_cache = ExpiringDict(max_len=100, max_age_seconds=5)

        self.dizzy_users = []
        self.dizzy_start_ts = 0
        self.dizzy_ban_end_ts = 0
        self.ban_target = ""

        # self.api_client = TwitchAPIClient(self.channel_id, client_id)

        # Create IRC bot connection
        logging.info(f"Connecting to {SERVER} on port {PORT}...")
        irc.bot.SingleServerIRCBot.__init__(
            self, [(SERVER, PORT, "oauth:" + self.token)], username, username
        )
        # TODO: dynamically determine
        self.trend_threshold = 3

        self.gbf_code_re = re.compile(r"[A-Z0-9]{8}")

        # setup scheduler
        self.reactor.scheduler.execute_every(1, self.dizzy)
        # self.reactor.scheduler.execute_every(5 * 60, self.insert_all)
        # self.reactor.scheduler.execute_every(60 * 60, self.share_clip)

        # load data in disk
        try:
            with open(self.serialized_data_filename, "rb") as f:
                self.data = dill.loads(f.read())
                if "gbf_room_num" not in self.data:
                    self.data["gbf_room_num"] = 0
                if "gbf_room_id_cache" not in self.data:
                    self.data["gbf_room_id_cache"] = ExpiringDict(
                        max_len=1, max_age_seconds=600
                    )
        except FileNotFoundError:
            self.data = {
                "gbf_room_num": 0,
                "gbf_room_id_cache": ExpiringDict(max_len=1, max_age_seconds=600),
            }

        # register signal handler
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        signal.signal(signal.SIGINT, handler=self.save_data)

    def save_data(self, sig, frame):
        logging.info("pressed Ctrl+C! dumping variables...")
        try:
            with open(self.serialized_data_filename, "wb") as f:
                f.write(dill.dumps(self.data))
        except FileNotFoundError:
            os.makedirs(self.serialized_data_dir)
        sys.exit(0)

    def trend_talking(self, conn, msg):
        # partial matching
        for word in TREND_WORDS_SUBSTRING:
            if word in msg:
                if word not in self.push_trend_cache:
                    self.push_trend_cache[word] = 1
                else:
                    self.push_trend_cache[word] += 1
                logging.info(f"[COUNTER] {word}:{ self.push_trend_cache[word]}")
                if self.push_trend_cache[word] >= self.trend_threshold:
                    talk(conn, self.irc_channel, word)
        # full matching
        if msg in TREND_WORDS_EXACT_MATCH:
            if msg not in self.push_trend_cache:
                self.push_trend_cache[msg] = 1
            else:
                self.push_trend_cache[msg] += 1
            logging.info(f"[COUNTER] {msg}:{ self.push_trend_cache[msg]}")
            if self.push_trend_cache[msg] >= self.trend_threshold:
                talk(conn, self.irc_channel, msg)

    @filter_feature_toggle
    def dizzy(self):
        now = int(time.time())
        if self.dizzy_start_ts == 0:
            return
        if self.dizzy_ban_end_ts == 0 and self.dizzy_start_ts + ONBOARDING_PERIOD < now:
            if not self.dizzy_users:
                logging.info(f"沒人上船，開船失敗！")
                talk(self.connection, self.irc_channel, f"沒人上船，開船失敗！")
                self.dizzy_users = []
                self.ban_target = ""
                self.dizzy_start_ts = 0
                self.dizzy_ban_end_ts = 0
            else:
                self.ban_target = random.choice(self.dizzy_users)
                logging.info(f"抓到了 @{self.ban_target} 你就是暈船仔！")
                talk(
                    self.connection,
                    self.irc_channel,
                    f"抓到了 @{self.ban_target} 你就是暈船仔！我看你五分鐘內都會神智不清亂告白，只好幫你湮滅證據了。",
                )
                self.dizzy_ban_end_ts = (
                    self.dizzy_start_ts + ONBOARDING_PERIOD + BAN_PERIOD
                )
        elif now <= self.dizzy_ban_end_ts:
            logging.info(f"暈船仔 {self.ban_target} 還在暈")
        elif now > self.dizzy_ban_end_ts > 0:
            logging.info(f"放 {self.ban_target} 下船")
            talk(self.connection, self.irc_channel, f"放 {self.ban_target} 下船")
            self.dizzy_users = []
            self.ban_target = ""
            self.dizzy_start_ts = 0
            self.dizzy_ban_end_ts = 0
        else:
            logging.info(
                f"now: {now}, dizzy_start_ts: {self.dizzy_start_ts}, dizzy_ban_end_ts: {self.dizzy_ban_end_ts}"
            )

    # @filter_feature_toggle
    # def share_clip(self):
    #     if self.channel_id not in CHANNEL_CLIPS:
    #         logging.info(
    #             f"{self.channel_id} is not in {CHANNEL_CLIPS.keys()}, skip share clip"
    #         )
    #         return
    #     if not self.api_client.check_stream_online():
    #         logging.info("channel is offline, skip share clip")
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
    #         logging.info("channel is offline, skip sending !insertall")
    #         return
    #     logging.info('channel is online! send chat: "!insertall"')
    #     talk(self.connection, self.irc_channel, "!insertall")

    def on_welcome(self, conn, e):
        logging.info("Joining " + self.irc_channel)

        # You must request specific capabilities before you can use them
        conn.cap("REQ", ":twitch.tv/membership")
        conn.cap("REQ", ":twitch.tv/tags")
        conn.cap("REQ", ":twitch.tv/commands")
        conn.join(self.irc_channel)
        logging.info("Joined " + self.irc_channel)

    def on_pubmsg(self, conn, e):
        msg = normalize_message(e.arguments[0])

        user_id = e.source.split("!")[0]
        user_name = e.tags[4]["value"]
        is_mod = e.tags[8]["value"]
        is_subscriber = e.tags[10]["value"]
        timestamp_ms = e.tags[11]["value"]

        # do not talk to myself
        if user_id != self.user_id:
            say_hi(conn, self.irc_channel, self.channel_id, user_id, user_name)
        logging.info(f"{user_id:>20}: {msg}")
        logging.info(f"checking if {user_id} == {self.ban_target}...")
        if user_id == self.ban_target:
            time.sleep(3)
            talk(conn, self.irc_channel, f"/timeout {self.ban_target} 1")
            logging.info(f"/timeout {self.ban_target} 1")
            # talk(conn, self.irc_channel, f"/unban {self.ban_target}")
            # logging.info(f"/unban {self.ban_target}")
        if user_id == "f1yshadow" and msg == "莉芙溫 下午好~ KonCha":
            talk(conn, self.irc_channel, f"飛影飄泊 下午好~ KonCha")
        if user_id == "harnaisxsumire666" and self.gbf_code_re.fullmatch(msg):
            logging.info(f"GBF room id detected: {msg}")
            self.data["gbf_room_id_cache"]["user_id"] = msg
            self.data["gbf_room_num"] += 1

        self.trend_talking(conn, msg=msg)

        if msg.startswith("!"):
            cmd = msg.split(" ")[0][1:]
            logging.info("Received command: " + cmd)
            self.do_command(cmd, user_id)
        if msg == "馬娘":
            uma_call(conn, self.irc_channel, self.channel_id, user_name)
        return

    def do_command(self, cmd, user_id):
        if cmd == "code":
            gbf_room_id = self.data["gbf_room_id_cache"].get("user_id")
            if gbf_room_id:
                logging.info(f"GBF room: {gbf_room_id}")
                talk(
                    self.connection,
                    self.irc_channel,
                    f"ㄇㄨ的房號 {gbf_room_id} 這是開台第{self.data['gbf_room_num']}間房 maoThinking",
                )
        if cmd == "船來了":
            if user_id != self.channel_id:
                logging.info(f"沒有權限")
                return
            now = int(time.time())
            if now <= self.dizzy_ban_end_ts:
                logging.info(f"還在上一次暈船懲罰中喔")
                return
            talk(
                self.connection,
                self.irc_channel,
                f"在一分鐘內輸入 !上船 讓溫泉蛋找出誰是暈船仔，被抓到的暈船仔會不斷在三秒後被消音，直到五分鐘結束為止",
            )
            self.dizzy_start_ts = now
            logging.info(f"開始登記上船時間為 {self.dizzy_start_ts}")
        if cmd == "上船":
            now = int(time.time())
            if self.dizzy_start_ts == 0:
                logging.info(f"船還沒來喔！")
                return
            if now > self.dizzy_start_ts + ONBOARDING_PERIOD:
                logging.info(
                    f"現在是 {now} 已經超過開船時間 {self.dizzy_start_ts + ONBOARDING_PERIOD}"
                )
                return
            if user_id in self.dizzy_users:
                logging.info(f"{user_id} 已經在船上了！")
                return
            self.dizzy_users.append(user_id)
            logging.info(f"乘客 {user_id} 成功上船！")
            talk(self.connection, self.irc_channel, f"乘客 {user_id} 成功上船！")


def main():
    if len(sys.argv) != 4:
        logging.info("Usage: twitchbot <username> <token> <channel>")
        sys.exit(1)

    username = sys.argv[1]
    token = sys.argv[2]
    channel_id = sys.argv[3]

    bot = TwitchBot(username, token, channel_id)
    bot.start()


if __name__ == "__main__":
    main()
