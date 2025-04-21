import orjson as json
import queue
from logging.handlers import QueueHandler, QueueListener
from loguru import logger
import requests
import nuance.constants as constants

class LoguruHTTPHandler:
    """HTTP log handler that works with standard QueueListener"""
    def __init__(self, url, headers=None, timeout=5):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def handle(self, record):
        """Process individual log records"""
        try:
            response = requests.post(
                self.url,
                json=json.loads(record),
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
    http_handler.handle,
    respect_handler_level=True
)

# Configure the logger
logger.add(
    QueueHandler(log_queue),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO"
)

# Start the listener when module is imported
queue_listener.start()

# Ensure proper cleanup
def stop_listener():
    queue_listener.stop()
    if queue_listener._thread:  # Wait for thread to finish
        queue_listener._thread.join()

import atexit
atexit.register(stop_listener)

# Export the configured logger
__all__ = ['logger']