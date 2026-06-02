"""
Logging module for HourBoostr
Based on Log.cs
"""
import os
import threading
from datetime import datetime
from enum import Enum
from typing import List, Optional


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARN = "WARN"
    TEXT = "TEXT"
    ERROR = "ERROR"


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"


class Logger:
    """Logger class for writing messages to console and file"""
    
    _lock = threading.Lock()
    
    def __init__(self, name: str, log_path: str, queue_size: int = 1):
        self.name = name
        self.log_path = log_path
        self.queue_size = queue_size
        self._log_queue: List[str] = []
        
        # Create log file if it doesn't exist
        if not os.path.exists(log_path):
            with open(log_path, 'w') as f:
                pass
            print(f"Log file '{self.name}' created for path '{self.log_path}'")
    
    def _get_timestamp(self) -> str:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    def _get_color(self, level: LogLevel) -> str:
        color_map = {
            LogLevel.ERROR: Colors.RED,
            LogLevel.INFO: Colors.CYAN,
            LogLevel.SUCCESS: Colors.GREEN,
            LogLevel.WARN: Colors.YELLOW,
            LogLevel.TEXT: Colors.MAGENTA,
        }
        return color_map.get(level, Colors.WHITE)
    
    def write(self, level: LogLevel, message: str, log_to_file: bool = True, 
              write_to_console: bool = True, raw_message: bool = False):
        """Write a log message"""
        color = self._get_color(level)
        timestamp = self._get_timestamp()
        
        formatted_message = f"[{timestamp}] {level.value}: {message}"
        
        if write_to_console:
            print(f"{self.name} {color}{formatted_message}{Colors.RESET}")
        
        if log_to_file:
            if raw_message:
                self._log_queue.append(message)
            else:
                self._log_queue.append(formatted_message)
            
            self._flush_log()
    
    def _flush_log(self):
        """Flush log queue to file"""
        if len(self._log_queue) < self.queue_size:
            return
        
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w') as f:
                pass
        
        with self._lock:
            try:
                with open(self.log_path, 'a', encoding='utf-8') as f:
                    for msg in self._log_queue:
                        f.write(msg + '\n')
                    self._log_queue.clear()
            except Exception as e:
                self.write(LogLevel.ERROR, f"Unable to flush log - {e}")
    
    # Convenience methods
    def debug(self, msg: str): self.write(LogLevel.DEBUG, msg)
    def info(self, msg: str): self.write(LogLevel.INFO, msg)
    def success(self, msg: str): self.write(LogLevel.SUCCESS, msg)
    def warn(self, msg: str): self.write(LogLevel.WARN, msg)
    def text(self, msg: str): self.write(LogLevel.TEXT, msg)
    def error(self, msg: str): self.write(LogLevel.ERROR, msg)


def create_logger(name: str, log_path: str, queue_size: int = 1) -> Logger:
    """Factory function to create a logger"""
    return Logger(name, log_path, queue_size)