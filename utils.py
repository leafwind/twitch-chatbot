import functools
import inspect

import yaml
from expiringdict import ExpiringDict

FEATURE_TOGGLE_FILE = "feature_toggle.yml"
with open(FEATURE_TOGGLE_FILE, "r") as f:
    toggle_dict = yaml.full_load(f)
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=60)

uma_call_cache = ExpiringDict(max_len=1, max_age_seconds=600)

say_hi_cache = ExpiringDict(max_len=1, max_age_seconds=1800)


def normalize_message(text):
    # normalize chat. e.g. 77777777 -> 777
    if len(text) >= 3 and len(set(text)) == 1:
        return text[:3]
    else:
        return text


def cooldown():
    if "_" not in GLOBAL_COOLDOWN:
        GLOBAL_COOLDOWN["_"] = True
        return False
    else:
        return True


def talk(conn, channel, msg):
    if cooldown():
        print("COOLDOWN...")
        return
    conn.privmsg(channel, msg)


def filter_feature_toggle(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        if func_name not in toggle_dict:
            print(f"ERROR!! cannot found {func_name} in {FEATURE_TOGGLE_FILE}")
            return None
        try:
            channel = kwargs["channel"]
        except KeyError:
            try:
                channel_arg_index = inspect.getfullargspec(func).args.index("channel")
                channel = args[channel_arg_index]
            except ValueError:
                channel = args[0].channel
        channel = channel[1:]
        if channel in toggle_dict[func_name]:
            return func(*args, **kwargs)
        else:
            print(f"{channel} is not in {toggle_dict[func_name]}, skip")
            return

    return wrapper


@filter_feature_toggle
def uma_call(conn, channel, user_name):
    if channel not in uma_call_cache:
        talk(
            conn,
            channel,
            f"@{user_name} MrDestructoid SingsMic うまぴょい うまぴょい ShowOfHands",
        )
        uma_call_cache[channel] = True


@filter_feature_toggle
def say_hi(conn, channel, user_name, bot_username):
    # do not talk to myself
    if bot_username == user_name:
        return
    if channel not in say_hi_cache:
        talk(
            conn,
            channel,
            f"@{user_name} PokPikachu",
        )
        say_hi_cache[channel] = True
