"""
Global configuration for the Discord scraper.

All tunable knobs live here. Import this module anywhere
you need access to settings.

Sections:
    HUMAN IMITATION    – Simulates natural copy-paste behavior
    WRITER             – Controls how/when scraped data is flushed to disk
    DISCORD API        – Rate-limit / retry / batch sizes
    PIPELINE           – Async queue and concurrency settings
    CHECKPOINT         – Resume support after crash / restart
    CHANNELS           – Which channels to scrape
    AUTH               – Bot / user token
"""

from __future__ import annotations

from pathlib import Path


# =============================================================
# HUMAN IMITATION
# Adds randomised micro-delays between requests so the access
# pattern looks like a person manually copying messages.
# Set ENABLED = False to disable entirely (bot accounts).
# =============================================================
HUMAN_IMITATION_ENABLED: bool = True
HUMAN_IMITATION_BASE_DELAY: float = 0.4          # seconds – base pause between requests
HUMAN_IMITATION_JITTER_MIN: float = 0.1          # seconds – minimum random addition
HUMAN_IMITATION_JITTER_MAX: float = 0.9          # seconds – maximum random addition
HUMAN_IMITATION_LONG_PAUSE_CHANCE: float = 0.05  # 5 % chance of a longer "reading" pause
HUMAN_IMITATION_LONG_PAUSE_MIN: float = 2.0      # seconds
HUMAN_IMITATION_LONG_PAUSE_MAX: float = 5.0      # seconds

# =============================================================
# WRITER
# Messages are buffered in-memory and flushed in bulk.
# A flush is triggered when EITHER threshold is reached.
# =============================================================
WRITER_FLUSH_BATCH_SIZE: int = 5           # flush after this many *batches* in the buffer
WRITER_FLUSH_INTERVAL_SECONDS: float = 10  # flush at least every N seconds
OUTPUT_BASE_PATH: str = "output/log" # where output is

# =============================================================
# DISCORD API
# =============================================================
MAX_DISCORD_MESSAGE: int = 100             # max messages per GET (Discord hard-cap)
REQUEST_DELAY_SECONDS: float = 0.25        # minimum delay between API calls
RETRY_MAX: int = 5                         # how many times to retry a failed request
RETRY_BACKOFF_MULTIPLIER: float = 2.0      # exponential back-off multiplier

# =============================================================
# PIPELINE  (Producer-Consumer)
# =============================================================
QUEUE_MAX_BATCHES: int = 10_000            # max items the async queue will hold
MAX_CONCURRENT_CHANNEL_WORKERS: int = 5    # semaphore width for channel scrapers

# =============================================================
# CHECKPOINT
# Saves progress so scraping can resume after a crash.
# =============================================================
CHECKPOINT_SAVE_INTERVAL: int = 1_000      # save checkpoint every N messages
CHECKPOINT_DIR: Path = Path("output/.checkpoints")

# =============================================================
# CHANNELS
# Pass a list of channel-ID strings, or ["all"] to discover
# every text channel in the guild automatically.
# =============================================================
CHANNELS: list[str] = ["1454124341263339642", "1447424083846369390"]
FROM_AUTHORS: list[str] | None = ["1414349180578697316"]

# =============================================================
# AUTH
# =============================================================
GUILD_ID: str = "1454124341263339642"                         # target guild
API_BASE: str = "https://discord.com/api/v10"
