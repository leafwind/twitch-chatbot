import functools
import inspect

import yaml
from expiringdict import ExpiringDict

FEATURE_TOGGLE_FILE = "feature_toggle.yml"
with open(FEATURE_TOGGLE_FILE, "r") as f:
    FEATURE_TOGGLE = yaml.full_load(f)
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=60)

uma_call_cache = ExpiringDict(max_len=1, max_age_seconds=600)

# remember 4096 users for say hi
say_hi_cache = ExpiringDict(max_len=4096, max_age_seconds=1800)


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
        if func_name not in FEATURE_TOGGLE:
            print(f"ERROR!! cannot found {func_name} in {FEATURE_TOGGLE_FILE}")
            return None
        try:
            channel_id = kwargs["channel_id"]
        except KeyError:
            try:
                channel_id_arg_index = inspect.getfullargspec(func).args.index(
                    "channel_id"
                )
                channel_id = args[channel_id_arg_index]
            except ValueError:
                channel_id = args[0].channel_id
        if channel_id in FEATURE_TOGGLE[func_name]:
            return func(*args, **kwargs)
        else:
            print(f"{channel_id} is not in {FEATURE_TOGGLE[func_name]}, skip")
            return

    return wrapper


@filter_feature_toggle
def uma_call(conn, channel_id, user_name):
    if channel_id not in uma_call_cache:
        talk(
            conn,
            channel_id,
            f"@{user_name} MrDestructoid SingsMic うまぴょい うまぴょい ShowOfHands",
        )
        uma_call_cache[channel_id] = True


@filter_feature_toggle
def say_hi(conn, channel_id, user_id, user_name):
    if user_id not in say_hi_cache:
        talk(
            conn,
            channel_id,
            f"@{user_name} 安安 PokPikachu",
        )
        say_hi_cache[user_id] = True
    else:
        print(f"already said hi to {user_id}, cool down..")
