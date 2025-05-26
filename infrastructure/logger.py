import logging
import sys

_loggers = {}

def setup_logger(name="spurly", level=logging.INFO, toFile=False, fileName="spurly.log"):
    """
    Establish an instance of a logger to be used for logging in current context of app

    Args
        name: name of the logger
        level: level of logging info
        toFile: 

    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    numeric_level = getattr(logging, str(level).upper(), logging.INFO)
    logger.setLevel(numeric_level)
    formatter = logging.Formatter("[%(asctime)s] - %(name)s %(levelname)s %(message)s")

    if toFile:
        fileHandler = logging.FileHandler(fileName)
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)

    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(formatter)
    logger.addHandler(streamHandler)

    _loggers[name] = logger
    return logger

def get_logger(name="spurly"):
    return logging.getLogger(name)