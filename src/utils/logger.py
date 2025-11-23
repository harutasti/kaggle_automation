import logging
import sys

def setup_logger(log_file='app.log', level=logging.INFO):
    """Configure the project logger."""
    logger = logging.getLogger('AutoKaggle')
    logger.setLevel(level)
    logger.handlers.clear()  # Avoid duplicate handlers

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)

    # Formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    detailed_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    fh.setFormatter(detailed_formatter)
    ch.setFormatter(formatter)

    # Attach handlers
    logger.addHandler(fh)
    logger.addHandler(ch)

    # Adjust other library log levels (optional)
    logging.getLogger('git').setLevel(logging.WARNING)

    return logger

# Global logger instance (optional)
# logger = setup_logger()
