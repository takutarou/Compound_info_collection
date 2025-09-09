"""
Configuration settings for eye drop screening project
"""

# PubChem API settings
TIMEOUT = 12
MAX_RETRY = 4
CID_LIMIT = 5
CHUNK_SIZE = 25
MAX_SYNONYM = 4

# Sleep intervals (seconds)
SLEEP_PROP = 2.0
SLEEP_CAS = 3.0
SLEEP_CID = 2.0

# HTTP headers
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Eye Drop Screening PubChem API)"}

# File extensions and patterns
SUPPORTED_INPUT_FORMATS = [".json"]
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_LEVEL = "DEBUG"