import logging
import os
import sys
from datetime import datetime


def set_logger(log_level=20):
    # TODO: consider put "%(filename)s" in the custom format
    my_format = (
        "[%(levelname).4s] %(asctime)s | %(name)s | " "%(lineno)3s | %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"
    if not os.path.isdir("logs"):
        os.makedirs("logs", exist_ok=True)
    date_str = datetime.strftime(datetime.utcnow(), "%Y%m%d")
    # set basic config to file
    logging.basicConfig(
        level=log_level,
        format=my_format,
        datefmt=date_format,
        filename=os.path.join("logs", f"log.{date_str}"),
    )
    # add another handler for stdout
    formatter = logging.Formatter(my_format, date_format)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(formatter)
    logging.getLogger().addHandler(h)
