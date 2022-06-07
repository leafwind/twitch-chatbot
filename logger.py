import logging


def set_logger(log_level=20):
    # TODO: consider put "%(filename)s" in the custom format
    my_format = (
        "[%(levelname).4s] %(asctime)s | %(name)s | " "%(lineno)3s | %(message)s"
    )
    date_format = "%m-%d %H:%M:%S"
    logging.basicConfig(
        level=log_level,
        format=my_format,
        datefmt=date_format,
        force=True,
    )
