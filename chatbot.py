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
from cachetools import cached, TTLCache
from expiringdict import ExpiringDict

TREND_WORDS = ["LUL", "0", "4", "777", "888", "555"]
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=60)


def cooldown():
    if "_" not in GLOBAL_COOLDOWN:
        GLOBAL_COOLDOWN["_"] = True
        return False
    else:
        return True


CD_UMA = 3600
# 1hr cooldown for command
@cached(cache=TTLCache(maxsize=1024, ttl=CD_UMA))
def last_timestamp(arg):
    return int(time.time())


def uma_call(conn, channel, arg):
    if int(time.time()) - last_timestamp(arg) <= 1:
        print(f"{int(time.time()) - last_timestamp(arg)} <= 1")
        conn.privmsg(
            channel,
            f"@{user_id} MrDestructoid SingsMic うまぴょい うまぴょい ShowOfHands",
        )
    else:
        print(f"CD 等待中，還有 {CD_UMA - (int(time.time() - last_timestamp(arg)))} 秒")


say_hi_cache = ExpiringDict(max_len=1, max_age_seconds=1800)


def say_hi(conn, channel, user_name):
    if channel not in say_hi_cache:
        conn.privmsg(
            channel,
            f"@{user_name} PokPikachu",
        )
        say_hi_cache[channel] = True


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

    def talk(self, conn, msg):
        if cooldown():
            print("COOLDOWN...")
            return
        conn.privmsg(self.channel, msg)

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
        if len(arg) >= 3 and len(set(arg)) == 1:
            arg = arg[:3]
        if arg in TREND_WORDS:
            if arg not in self.push_trend_cache:
                self.push_trend_cache[arg] = 1
            else:
                self.push_trend_cache[arg] += 1
            print(f"[COUNTER] {arg}:{ self.push_trend_cache[arg]}")
            if self.push_trend_cache[arg] >= 3:
                self.talk(c, arg)
        # if arg.startswith("!"):
        #     cmd = e.arguments[0].split(" ")[0][1:]
        #     print("Received command: " + cmd)
        #     self.do_command(e, cmd)
        if arg == "馬娘":
            uma_call(arg)
        return

    def do_command(self, e, cmd):
        c = self.connection

        # Poll the API to get current game.
        if cmd == "game":
            url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
            headers = {
                "Client-ID": self.client_id,
                "Accept": "application/vnd.twitchtv.v5+json",
            }
            r = requests.get(url, headers=headers).json()
            c.privmsg(
                self.channel, r["display_name"] + " is currently playing " + r["game"]
            )

        # Poll the API the get the current status of the stream
        elif cmd == "title":
            url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
            headers = {
                "Client-ID": self.client_id,
                "Accept": "application/vnd.twitchtv.v5+json",
            }
            r = requests.get(url, headers=headers).json()
            c.privmsg(
                self.channel,
                r["display_name"] + " channel title is currently " + r["status"],
            )

        # Provide basic information to viewers for specific commands
        elif cmd == "raffle":
            message = "This is an example bot, replace this text with your raffle text."
            c.privmsg(self.channel, message)
        elif cmd == "schedule":
            message = (
                "This is an example bot, replace this text with your schedule text."
            )
            c.privmsg(self.channel, message)

        # The command was not recognized
        else:
            c.privmsg(self.channel, "Did not understand command: " + cmd)


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
