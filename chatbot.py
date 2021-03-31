"""
Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/apache2.0/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""
import os
import re
import signal
import sys

import dill
import irc.bot
from expiringdict import ExpiringDict

from twitch_api_client import TwitchAPIClient

TREND_WORDS_SUBSTRING = ["LUL"]
TREND_WORDS_MATCH = ["0", "4", "555", "666", "777", "888", "999"]
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=60)

SERVER = "irc.chat.twitch.tv"
PORT = 6667


def cooldown():
    if "_" not in GLOBAL_COOLDOWN:
        GLOBAL_COOLDOWN["_"] = True
        return False
    else:
        return True


uma_call_cache = ExpiringDict(max_len=1, max_age_seconds=600)


def uma_call(conn, channel, user_name):
    if channel not in uma_call_cache:
        talk(
            conn,
            channel,
            f"@{user_name} MrDestructoid SingsMic うまぴょい うまぴょい ShowOfHands",
        )
        uma_call_cache[channel] = True


say_hi_cache = ExpiringDict(max_len=1, max_age_seconds=1800)


def say_hi(conn, channel, user_name):
    if channel not in say_hi_cache:
        talk(
            conn,
            channel,
            f"@{user_name} PokPikachu",
        )
        say_hi_cache[channel] = True


def talk(conn, channel, msg):
    if cooldown():
        print("COOLDOWN...")
        return
    conn.privmsg(channel, msg)


class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, username, client_id, token, channel):
        self.client_id = client_id
        self.token = token.removeprefix("oauth:")
        self.channel = "#" + channel.lower()
        self.serialized_data_dir = "data"
        self.serialized_data_filename = os.path.join(
            self.serialized_data_dir, f"{self.channel[1:]}.bin"
        )
        self.push_trend_cache = ExpiringDict(max_len=100, max_age_seconds=5)

        self.api_client = TwitchAPIClient(channel, client_id)
        self.channel_id = self.api_client.channel_id

        # Create IRC bot connection
        print(f"Connecting to {SERVER} on port {PORT}...")
        irc.bot.SingleServerIRCBot.__init__(
            self, [(SERVER, PORT, "oauth:" + self.token)], username, username
        )
        # TODO: dynamically determine
        self.trend_threshold = 3

        self.gbf_code_re = re.compile(r"[A-Z0-9]{8}")

        # setup scheduler
        self.reactor.scheduler.execute_every(5 * 60, self.insertall)

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

    def insertall(self):
        if self.api_client.check_stream_online():
            print('channel is online! send chat: "!insertall"')
            talk(self.connection, self.channel, "!insertall")
        else:
            print("channel is offline, skip sending !insertall")

    def on_welcome(self, c, e):
        print("Joining " + self.channel)

        # You must request specific capabilities before you can use them
        c.cap("REQ", ":twitch.tv/membership")
        c.cap("REQ", ":twitch.tv/tags")
        c.cap("REQ", ":twitch.tv/commands")
        c.join(self.channel)
        print("Joined " + self.channel)

    def on_pubmsg(self, c, e):
        arg = e.arguments[0]
        user_id = e.source.split("!")[0]
        user_name = e.tags[4]["value"]
        is_mod = e.tags[8]["value"]
        is_subscriber = e.tags[10]["value"]
        timestamp_ms = e.tags[11]["value"]
        # say_hi(c, self.channel, user_name)
        print(f"{user_id:>20}: {arg}")
        if user_id == "f1yshadow" and arg == "莉芙溫 下午好~ KonCha":
            talk(c, self.channel, f"飛影飄泊 下午好~ KonCha")
        if user_id == "harnaisxsumire666" and self.gbf_code_re.fullmatch(arg):
            print(f"GBF room id detected: {arg}")
            self.data["gbf_room_id_cache"]["user_id"] = arg
            self.data["gbf_room_num"] += 1
        if self.channel == "#wow_tomato" and arg == "!insertall":
            pass
            # talk(c, self.channel, f"@{user_id}, you have successfully queued. You are 1st...騙你的QAQ")
            # talk(c, self.channel, f"@{user_id} successfully inserted 56 coins")
            # talk(c, self.channel, f"Successfully added 5 points to {user_name}. Points: 5566")

        # normalize chat. e.g. 77777777 -> 777
        if len(arg) >= 3 and len(set(arg)) == 1:
            arg = arg[:3]
        for word in TREND_WORDS_SUBSTRING:
            if word in arg:
                if word not in self.push_trend_cache:
                    self.push_trend_cache[word] = 1
                else:
                    self.push_trend_cache[word] += 1
                print(f"[COUNTER] {word}:{ self.push_trend_cache[word]}")
                if self.push_trend_cache[word] >= self.trend_threshold:
                    talk(c, self.channel, word)
        if arg in TREND_WORDS_MATCH:
            if arg not in self.push_trend_cache:
                self.push_trend_cache[arg] = 1
            else:
                self.push_trend_cache[arg] += 1
            print(f"[COUNTER] {arg}:{ self.push_trend_cache[arg]}")
            if self.push_trend_cache[arg] >= self.trend_threshold:
                talk(c, self.channel, arg)
        if arg.startswith("!"):
            cmd = arg.split(" ")[0][1:]
            print("Received command: " + cmd)
            self.do_command(e, cmd)
        if arg == "馬娘":
            uma_call(c, self.channel, user_name)
        return

    def do_command(self, user_id, cmd):
        c = self.connection
        if cmd == "code":
            gbf_room_id = self.data["gbf_room_id_cache"].get("user_id")
            if gbf_room_id:
                print(f"GBF room: {gbf_room_id}")
                talk(
                    c,
                    self.channel,
                    f"ㄇㄨ的房號 {gbf_room_id} 這是開台第{self.data['gbf_room_num']}間房 maoThinking",
                )


def main():
    if len(sys.argv) != 5:
        print("Usage: twitchbot <username> <client id> <token> <channel>")
        sys.exit(1)

    username = sys.argv[1]
    client_id = sys.argv[2]
    token = sys.argv[3]
    channel = sys.argv[4]

    bot = TwitchBot(username, client_id, token, channel)
    bot.start()


if __name__ == "__main__":
    main()
