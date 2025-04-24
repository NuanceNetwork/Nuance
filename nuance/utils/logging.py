import logging
from logging.handlers import QueueHandler, QueueListener
import queue
import threading

import requests
from loguru import logger

import nuance.constants as constants

class LoguruHTTPHandler(logging.Handler):
    """HTTP log handler that works with standard QueueListener"""
    def __init__(self, url, headers=None, timeout=5, level=logging.INFO):
        super().__init__(level=level)
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def emit(self, record: logging.LogRecord):  # Use emit instead of handle for Handler subclass
        """Process individual log records"""
        try:
            # Get the formatted message from Loguru's record
            formatted_message = record.getMessage()
            
            # Create minimal but useful log payload
            log_data = {
                "timestamp": record.created,
                "level": record.levelname,
                "message": formatted_message,
                "source": f"{record.pathname}:{record.lineno}",
                "thread": record.threadName,
                "extra": getattr(record, "extra", {})  # Loguru's extra context
            }
            
            response = requests.post(
                self.url,
                json=log_data,  # Send the dict directly
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as e:
            print(f"HTTP log failed: {e}")

# Create the queue and configure handlers
log_queue = queue.Queue(-1)  # Unlimited queue size
http_handler = LoguruHTTPHandler(
    url=constants.LOG_URL,
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)

# Set up queue listener with the actual handler
queue_listener = QueueListener(
    log_queue,
    http_handler,
    respect_handler_level=True
)

# Configure the logger (commented out for now, uncomment when we have the logging server setup)
# logger.add(
#     QueueHandler(log_queue),
#     format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
#     level="INFO"
# )

# Start the listener when module is imported
# This is a hack to start the listener in a separate named thread, check this code in QueueListener class 's start() method
# queue_listener._thread = log_queue_listener_thread = threading.Thread(target=queue_listener._monitor, name="HTTP Log Queue Listener", daemon=True)
# log_queue_listener_thread.start()

# Ensure proper cleanup
def stop_listener():
    queue_listener.stop()
    if queue_listener._thread:  # Wait for thread to finish
        queue_listener._thread.join()

import atexit
atexit.register(stop_listener)

# Export the configured logger
__all__ = ['logger']