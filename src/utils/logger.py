import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logging(log_level='INFO', log_dir='logs'):
    os.makedirs(log_dir, exist_ok=True)
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(console_handler)
    
    today = datetime.now().strftime('%Y%m%d')
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, f'fund_pool_{today}.log'),
        maxBytes=100*1024*1024,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(file_handler)
    
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, f'error_{today}.log'),
        maxBytes=50*1024*1024,
        backupCount=30,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(error_handler)
    
    return root_logger
