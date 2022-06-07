import functools
import inspect
import logging
import time
import yaml
from expiringdict import ExpiringDict

logging.basicConfig(level=logging.INFO)

FEATURE_TOGGLE_FILE = "config/feature_toggle.yml"
with open(FEATURE_TOGGLE_FILE, "r") as f:
    FEATURE_TOGGLE = yaml.full_load(f)
GLOBAL_COOLDOWN = ExpiringDict(max_len=1, max_age_seconds=1)

UMA_CALL_CACHE_CHANNEL_ID = ExpiringDict(max_len=1, max_age_seconds=600)

# remember 10 channels for say hi
SAY_HI_CACHE_CHANNEL_ID = ExpiringDict(max_len=10, max_age_seconds=1800)
# remember 4096 users for say hi
SAY_HI_CACHE_USER = ExpiringDict(max_len=4096, max_age_seconds=86400)


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
        logging.info("COOLDOWN...")
        return
    conn.privmsg(channel, msg)


def filter_feature_toggle(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        if func_name not in FEATURE_TOGGLE:
            logging.error(f"ERROR!! cannot found {func_name} in {FEATURE_TOGGLE_FILE}")
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
            return

    return wrapper


@filter_feature_toggle
def uma_call(conn, irc_channel, channel_id, user_name):
    if channel_id not in UMA_CALL_CACHE_CHANNEL_ID:
        talk(
            conn,
            irc_channel,
            f"@{user_name} MrDestructoid SingsMic うまぴょい うまぴょい ShowOfHands",
        )
        UMA_CALL_CACHE_CHANNEL_ID[channel_id] = True


@filter_feature_toggle
def say_hi(conn, irc_channel, channel_id, user_id, user_name):
    if channel_id in SAY_HI_CACHE_CHANNEL_ID:
        return
    if user_id in SAY_HI_CACHE_USER:
        logging.info(f"already said hi to {user_id}, cool down..")
        return
    time.sleep(2)
    talk(
        conn,
        irc_channel,
        f"@{user_name} 安安 PokPikachu",
    )
    SAY_HI_CACHE_CHANNEL_ID[channel_id] = True
    SAY_HI_CACHE_USER[user_id] = True
