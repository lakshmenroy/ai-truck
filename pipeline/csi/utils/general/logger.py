import logging
from datetime import datetime
from pathlib import Path

def setup_logger(level: int = logging.INFO,
                 enable_file_handler: bool = False,
                 logs_path: Path = Path("./logs")) -> None:
    """
    Set up the logger.

    :param level: The level of the logger. 
        Default 'INFO'. 
    :param enable_file_handler: Boolean value to enable/disable the file handler.
        Default 'False'.
    :param logs_path: Path to the directory containing script logs.

    :return: None.
    """
    # Create the logger
    logger = logging.getLogger()
    logger.setLevel(level=level)

    # Formatter for all handlers
    formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s")

    # Console handler (stream to stdout)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt=formatter)

    # Add handler to the logger
    logger.addHandler(hdlr=console_handler)

    if enable_file_handler:
        logs_path.mkdir(parents=True, exist_ok=True)

        # File handler
        now = datetime.now()
        timestamp = now.strftime(format="%Y-%m-%d-%H-%M-%S")
        file_handler = logging.FileHandler(filename=logs_path / f"{timestamp}.log")
        file_handler.setFormatter(fmt=formatter)

        # Add handler to the logger
        logger.addHandler(hdlr=file_handler)
