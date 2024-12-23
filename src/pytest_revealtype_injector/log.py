import logging

LOGGER_NAME = "revealtype-injector"

_logger = logging.getLogger(LOGGER_NAME)

# Mapping of pytest.Config.VERBOSITY_TEST_CASES to logging levels
_verbosity_map = {
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}


def get_logger() -> logging.Logger:
    return _logger


def set_verbosity(verbosity: int) -> None:
    _logger.setLevel(_verbosity_map.get(verbosity, logging.DEBUG))
