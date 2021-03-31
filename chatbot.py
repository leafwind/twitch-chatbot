"""
Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/apache2.0/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""
import os
import random
import re
import signal
import sys

import dill
import irc.bot
import yaml
from expiringdict import ExpiringDict

from twitch_api_client import TwitchAPIClient
from utils import filter_feature_toggle, uma_call, talk, say_hi, normalize_message

TREND_WORDS_SUBSTRING = ["LUL"]
TREND_WORDS_MATCH = ["0", "4", "555", "666", "777", "888", "999"]
CHANNEL_CLIPS_FILE = "channel_clips.yml"
with open(CHANNEL_CLIPS_FILE, "r") as f:
    CHANNEL_CLIPS = yaml.full_load(f)
SERVER = "irc.chat.twitch.tv"
PORT = 6667


class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, username, client_id, token, channel_id):
        self.user_id = username
        self.client_id = client_id
        self.token = token.removeprefix("oauth:")
        self.irc_channel = "#" + channel_id.lower()
        self.channel_id = channel_id
        self.serialized_data_dir = "data"
        self.serialized_data_filename = os.path.join(
            self.serialized_data_dir, f"{self.channel_id}.bin"
        )
        self.push_trend_cache = ExpiringDict(max_len=100, max_age_seconds=5)

        self.api_client = TwitchAPIClient(self.channel_id, client_id)

        # Create IRC bot connection
        print(f"Connecting to {SERVER} on port {PORT}...")
        irc.bot.SingleServerIRCBot.__init__(
            self, [(SERVER, PORT, "oauth:" + self.token)], username, username
        )
        # TODO: dynamically determine
        self.trend_threshold = 3

        self.gbf_code_re = re.compile(r"[A-Z0-9]{8}")

        # setup scheduler
        self.reactor.scheduler.execute_every(5 * 60, self.insert_all)
        self.reactor.scheduler.execute_every(60 * 60, self.share_clip)

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
        print("pressed Ctrl+C! dumping variables...")
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
                print(f"[COUNTER] {word}:{ self.push_trend_cache[word]}")
                if self.push_trend_cache[word] >= self.trend_threshold:
                    talk(conn, self.irc_channel, word)
        # full matching
        if msg in TREND_WORDS_MATCH:
            if msg not in self.push_trend_cache:
                self.push_trend_cache[msg] = 1
            else:
                self.push_trend_cache[msg] += 1
            print(f"[COUNTER] {msg}:{ self.push_trend_cache[msg]}")
            if self.push_trend_cache[msg] >= self.trend_threshold:
                talk(conn, self.irc_channel, msg)

    @filter_feature_toggle
    def share_clip(self):
        if self.channel_id not in CHANNEL_CLIPS:
            print(
                f"{self.channel_id} is not in {CHANNEL_CLIPS.keys()}, skip share clip"
            )
            return
        if not self.api_client.check_stream_online():
            print("channel is offline, skip share clip")
            return
        clip = random.choice(CHANNEL_CLIPS[self.channel_id])
        talk(
            self.connection,
            self.irc_channel,
            f"{clip['title']} {clip['url']}",
        )

    @filter_feature_toggle
    def insert_all(self):
        if not self.api_client.check_stream_online():
            print("channel is offline, skip sending !insertall")
            return
        print('channel is online! send chat: "!insertall"')
        talk(self.connection, self.irc_channel, "!insertall")

    def on_welcome(self, conn, e):
        print("Joining " + self.irc_channel)

        # You must request specific capabilities before you can use them
        conn.cap("REQ", ":twitch.tv/membership")
        conn.cap("REQ", ":twitch.tv/tags")
        conn.cap("REQ", ":twitch.tv/commands")
        conn.join(self.irc_channel)
        print("Joined " + self.irc_channel)

    def on_pubmsg(self, conn, e):
        msg = normalize_message(e.arguments[0])

        user_id = e.source.split("!")[0]
        user_name = e.tags[4]["value"]
        is_mod = e.tags[8]["value"]
        is_subscriber = e.tags[10]["value"]
        timestamp_ms = e.tags[11]["value"]

        # do not talk to myself
        if user_id != self.user_id:
            say_hi(conn, self.channel_id, user_name)
        print(f"{user_id:>20}: {msg}")
        if user_id == "f1yshadow" and msg == "莉芙溫 下午好~ KonCha":
            talk(conn, self.irc_channel, f"飛影飄泊 下午好~ KonCha")
        if user_id == "harnaisxsumire666" and self.gbf_code_re.fullmatch(msg):
            print(f"GBF room id detected: {msg}")
            self.data["gbf_room_id_cache"]["user_id"] = msg
            self.data["gbf_room_num"] += 1

        self.trend_talking(conn, msg=msg)

        if msg.startswith("!"):
            cmd = msg.split(" ")[0][1:]
            print("Received command: " + cmd)
            self.do_command(cmd)
        if msg == "馬娘":
            uma_call(conn, self.channel_id, user_name)
        return

    def do_command(self, cmd):
        if cmd == "code":
            gbf_room_id = self.data["gbf_room_id_cache"].get("user_id")
            if gbf_room_id:
                print(f"GBF room: {gbf_room_id}")
                talk(
                    self.connection,
                    self.irc_channel,
                    f"ㄇㄨ的房號 {gbf_room_id} 這是開台第{self.data['gbf_room_num']}間房 maoThinking",
                )


def main():
    if len(sys.argv) != 5:
        print("Usage: twitchbot <username> <client id> <token> <channel>")
        sys.exit(1)

    username = sys.argv[1]
    client_id = sys.argv[2]
    token = sys.argv[3]
    channel_id = sys.argv[4]

    bot = TwitchBot(username, client_id, token, channel_id)
    bot.start()


if __name__ == "__main__":
    main()
