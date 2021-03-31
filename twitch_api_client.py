from typing import Dict

import requests
from cachetools import cached, TTLCache


class TwitchAPIClient:
    def __init__(self, channel_id, client_id):
        self.api_url = "https://api.twitch.tv/kraken/users?login=" + channel_id
        self.api_headers = {
            "Client-ID": client_id,
            "Accept": "application/vnd.twitchtv.v5+json",
        }
        # Get the channel serial number, we will need this for v5 API calls
        r = requests.get(self.api_url, headers=self.api_headers).json()
        self.serial_number = r["users"][0]["_id"]

    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def check_stream_online(self) -> bool:
        """
        Poll the API to know if a channel is live or not
        :return:
        """
        url = "https://api.twitch.tv/kraken/streams/" + self.serial_number
        r = requests.get(url, headers=self.api_headers).json()
        return True if r["stream"] else False

    @cached(cache=TTLCache(maxsize=1, ttl=300))
    def get_channel_info(self) -> Dict:
        """
        Poll the API to get channel information
        :return:
        r["display_name"]
        r["game"]
        r["status"]
        """
        url = "https://api.twitch.tv/kraken/channels/" + self.serial_number
        r = requests.get(url, headers=self.api_headers).json()
        return r
