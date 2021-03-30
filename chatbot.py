"""
Copyright 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at

    http://aws.amazon.com/apache2.0/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
"""
import sys
import irc.bot
import requests
import time
import re
from cachetools import cached, TTLCache
from expiringdict import ExpiringDict

TREND_WORDS_SUBSTRING = ["LUL"]
TREND_WORDS_MATCH = ["0", "4", "555", "666", "777", "888", "999"]
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=60)


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
        self.push_trend_cache = ExpiringDict(max_len=100, max_age_seconds=5)

        # Get the channel id, we will need this for v5 API calls
        url = "https://api.twitch.tv/kraken/users?login=" + channel
        headers = {"Client-ID": client_id, "Accept": "application/vnd.twitchtv.v5+json"}
        r = requests.get(url, headers=headers).json()
        self.channel_id = r["users"][0]["_id"]

        # Create IRC bot connection
        server = "irc.chat.twitch.tv"
        port = 6667
        print("Connecting to " + server + " on port " + str(port) + "...")
        irc.bot.SingleServerIRCBot.__init__(
            self, [(server, port, "oauth:" + self.token)], username, username
        )
        # TODO: dynamically determine
        self.trend_threshold = 3

        self.gbf_code_re = re.compile(r"[A-Z0-9]{8}")
        self.gbf_room_id_cache = ExpiringDict(max_len=1, max_age_seconds=600)
        self.gbf_room_num = 0
        self.api_headers = {
            "Client-ID": self.client_id,
            "Accept": "application/vnd.twitchtv.v5+json",
        }
        self.reactor.scheduler.execute_every(5 * 60, self.insertall)

    def check_onlilne(self):
        # Poll the API to know if a channel is live or not
        url = "https://api.twitch.tv/kraken/streams/" + self.channel_id
        r = requests.get(url, headers=self.api_headers).json()
        return True if r["stream"] else False

    def insertall(self):
        if self.check_onlilne():
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
        # c.privmsg(self.channel, "Connected!")

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
            self.gbf_room_id_cache["user_id"] = arg
            self.gbf_room_num += 1
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
            gbf_room_id = self.gbf_room_id_cache.get("user_id")
            if gbf_room_id:
                print(f"GBF room: {gbf_room_id}")
                talk(
                    c,
                    self.channel,
                    f"ㄇㄨ的房號 {gbf_room_id} 這是開台第{self.gbf_room_num}間房 maoThinking",
                )
        # Poll the API to get current game.
        # if cmd == "game":
        #    url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
        #    headers = {
        #        "Client-ID": self.client_id,
        #        "Accept": "application/vnd.twitchtv.v5+json",
        #    }
        #    r = requests.get(url, headers=headers).json()
        #    c.privmsg(
        #        self.channel, r["display_name"] + " is currently playing " + r["game"]
        #    )

        ## Poll the API the get the current status of the stream
        # elif cmd == "title":
        #    url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
        #    headers = {
        #        "Client-ID": self.client_id,
        #        "Accept": "application/vnd.twitchtv.v5+json",
        #    }
        #    r = requests.get(url, headers=headers).json()
        #    c.privmsg(
        #        self.channel,
        #        r["display_name"] + " channel title is currently " + r["status"],
        #    )

        ## Provide basic information to viewers for specific commands
        # elif cmd == "raffle":
        #    message = "This is an example bot, replace this text with your raffle text."
        #    c.privmsg(self.channel, message)
        # elif cmd == "schedule":
        #    message = (
        #        "This is an example bot, replace this text with your schedule text."
        #    )
        #    c.privmsg(self.channel, message)

        ## The command was not recognized
        # else:
        #    c.privmsg(self.channel, "Did not understand command: " + cmd)


def main():
    if len(sys.argv) != 5:
        print("Usage: twitchbot <username> <client id> <token> <channel>")
        sys.exit(1)

    username = sys.argv[1]
    client_id = sys.argv[2]
    token = sys.argv[3]
    channel = sys.argv[4]

    # import dill
    # from expiringdict import ExpiringDict
    # cache = ExpiringDict(max_len=100, max_age_seconds=10)
    # cache['test'] = 1
    # pickled_cache = dill.dumps(cache)
    # unpickled_cache = dill.loads(pickled_cache)

    # import signal
    # import sys
    #
    # def signal_handler(sig, frame):
    #     print("You pressed Ctrl+C!")
    #     sys.exit(0)
    # signal.signal(signal.SIGINT, signal_handler)

    bot = TwitchBot(username, client_id, token, channel)
    bot.start()


if __name__ == "__main__":
    main()
