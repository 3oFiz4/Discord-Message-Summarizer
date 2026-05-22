"""
ChannelScraper  (Producer)
──────────────────────────
Fetches messages from a single Discord channel using the
``GET /channels/{id}/messages`` endpoint.

Key behaviours:
    • Paginates backwards using ``?before=<oldest_id>``
    • Respects Discord rate-limits via semaphore + delays
    • Optionally imitates human copy-paste timing
    • Pushes raw message dicts onto an ``asyncio.Queue``
      for the consumer (Writer) to process
    • Saves checkpoint every ``CHECKPOINT_SAVE_INTERVAL`` msgs
    • Retries transient failures with exponential back-off
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import aiohttp

from .checkpoint_manager import CheckpointManager
from config import config
from services.helper.error_logger import Panic
from models.message.message import MessageDTO
from services.helper.console import console

class ChannelScraper:
    """
    Asynchronous producer that scrapes one channel and feeds
    batches of raw dicts into a shared ``asyncio.Queue``.
    """

    def __init__(
        self,
        channel_id: str,
        session: aiohttp.ClientSession,
        queue: asyncio.Queue,
        semaphore: asyncio.Semaphore,
        checkpoint_mgr: CheckpointManager,
    ) -> None:
        # ---- identity ----
        self._channel_id = channel_id
        # ---- networking ----
        self._session = session
        self._url = f"{config.API_BASE}/channels/{channel_id}/messages"
        self._headers = {
            "Authorization": config.DISCORD_TOKEN,
            "Content-Type": "application/json",
        }
        # ---- pipeline ----
        self._queue = queue                # shared async queue → Writer consumes
        self._semaphore = semaphore        # limits concurrent HTTP work
        # ---- checkpoint ----
        self._checkpoint = checkpoint_mgr
        self._total_scraped: int = 0
        self._last_message_id: Optional[str] = None

    # ================================================================== #
    #  PUBLIC ENTRY POINT                                                  #
    # ================================================================== #
    async def run(self) -> None:
        """
        Start scraping the channel backwards from newest to oldest.
        Resumes from checkpoint if available.
        """
        # ---- precompute author filter ----
        self._author_filter: set[str] | None = None
        if config.FROM_AUTHORS is not None:
            self._author_filter = set(config.FROM_AUTHORS)

        # ---- resume from checkpoint ----
        saved = self._checkpoint.load(self._channel_id)
        if saved:
            self._last_message_id = saved["last_message_id"]
            self._total_scraped = saved["total_scraped"]
            console.print(
                f"[info]●[/] [muted]Starting[/] [channel]ch:{self._channel_id}[/]"
            )

        while True:
            raw_batch = await self._fetch_batch()

            if raw_batch is None or len(raw_batch) == 0:
                console.print(
                    f"[success]✓[/] [channel]ch:{self._channel_id}[/] "
                    f"[success]complete[/] [muted]—[/] "
                    f"[count]{self._total_scraped}[/] [muted]messages[/]"
                )
                self._checkpoint.clear(self._channel_id)
                break

            # ---- pagination cursor ALWAYS uses the full unfiltered batch ----
            self._last_message_id = str(raw_batch[-1]["id"])
            self._total_scraped += len(raw_batch)

            # ---- filter by author before pushing to queue ----
            if self._author_filter is not None:
                filtered = [
                    msg for msg in raw_batch
                    if str(msg.get("author", {}).get("id", "")) in self._author_filter
                ]
            else:
                filtered = raw_batch

            # Only enqueue if anything survived the filter
            if filtered:
                await self._queue.put({
                    "channel_id": self._channel_id,
                    "messages": filtered,
                })

            # ── Progress update ──
            if self._total_scraped % 500 < len(raw_batch):
                console.print(
                    f"  [muted]↓[/] [channel]ch:{self._channel_id}[/] "
                    f"[count]{self._total_scraped}[/] [muted]messages fetched[/]"
                )

            # ── Checkpoint ──
            if self._total_scraped % config.CHECKPOINT_SAVE_INTERVAL < len(raw_batch):
                self._checkpoint.save(
                    self._channel_id,
                    self._last_message_id,
                    self._total_scraped,
                )

            await self._maybe_human_delay()
            await asyncio.sleep(config.REQUEST_DELAY_SECONDS)

    # ================================================================== #
    #  HTTP FETCH WITH RETRY                                               #
    # ================================================================== #
    async def _fetch_batch(self) -> Optional[list[dict[str, Any]]]:
        """
        Fetch up to ``MAX_DISCORD_MESSAGE`` messages from the channel.

        Uses exponential back-off on transient failures.
        Returns ``None`` only on unrecoverable errors.
        """
        params: dict[str, Any] = {"limit": config.MAX_DISCORD_MESSAGE}
        if self._last_message_id:
            params["before"] = self._last_message_id

        attempt = 0
        backoff = config.REQUEST_DELAY_SECONDS

        while attempt < config.RETRY_MAX:
            # Semaphore ensures we never exceed MAX_CONCURRENT_CHANNEL_WORKERS
            # active HTTP requests across all channel scrapers.
            async with self._semaphore:
                try:
                    async with self._session.get(
                        self._url,
                        headers=self._headers,
                        params=params,
                    ) as resp:
                        # ---- rate-limited ----
                        if resp.status == 429:
                            retry_after = (await resp.json()).get("retry_after", backoff)
                            with console.status(
                                f"[warning]Rate limited[/] [channel]ch:{self._channel_id}[/] "
                                f"[muted]waiting[/] [count]{retry_after:.1f}s[/]",
                                spinner="dots",
                            ):
                                await asyncio.sleep(float(retry_after))
                            attempt += 1
                            continue

                        # ---- success ----
                        if resp.status == 200:
                            data = await resp.json()
                            return data  # list[dict]

                        # ---- client error (4xx) → unrecoverable ----
                        if 400 <= resp.status < 500:
                            body = await resp.text()
                            Panic(
                                RuntimeError,
                                f"HTTP {resp.status} on channel {self._channel_id}: {body}",
                                solutions=[
                                    "Check your DISCORD_TOKEN",
                                    "Check the channel ID is correct",
                                    "Ensure the bot/user has READ_MESSAGE_HISTORY",
                                ],
                                note="ChannelScraper._fetch_batch client error",
                            )
                            return None
                        
                        # ── Server error ──
                        console.print(
                            f"  [warning]![/] [channel]ch:{self._channel_id}[/] "
                            f"[warning]HTTP {resp.status}[/] [muted]retry[/] "
                            f"[count]{attempt + 1}[/][muted]/[/][count]{config.RETRY_MAX}[/] "
                            f"[muted]in[/] [count]{backoff:.1f}s[/]"
                        )

                        # ---- server error (5xx) → retry ----
                        print(
                            f"[channel {self._channel_id}] HTTP {resp.status}. "
                            f"Retry {attempt + 1}/{config.RETRY_MAX} in {backoff:.1f}s …"
                        )

                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    console.print(
                        f"  [warning]![/] [channel]ch:{self._channel_id}[/] "
                        f"[warning]Network error[/] [muted]{exc}[/] "
                        f"[muted]retry[/] [count]{attempt + 1}[/][muted]/[/][count]{config.RETRY_MAX}[/]"
                    )

            # ---- exponential back-off ----
            await asyncio.sleep(backoff)
            backoff *= config.RETRY_BACKOFF_MULTIPLIER
            attempt += 1

        # ---- exhausted retries ----
        Panic(
            RuntimeError,
            f"Channel {self._channel_id}: max retries ({config.RETRY_MAX}) exceeded",
            solutions=[
                "Check your network connection",
                "Increase RETRY_MAX in config",
                "Try again later",
            ],
            note="ChannelScraper._fetch_batch retry exhaustion",
        )
        return None

    # ================================================================== #
    #  HUMAN IMITATION                                                     #
    # ================================================================== #
    async def _maybe_human_delay(self) -> None:
        """
        If human-imitation mode is enabled, sleep for a randomised
        duration that mimics a person scrolling and reading.
        """
        if not config.HUMAN_IMITATION_ENABLED:
            return

        # ---- occasional long "reading" pause ----
        if random.random() < config.HUMAN_IMITATION_LONG_PAUSE_CHANCE:
            pause = random.uniform(
                config.HUMAN_IMITATION_LONG_PAUSE_MIN,
                config.HUMAN_IMITATION_LONG_PAUSE_MAX,
            )
            with console.status(
                f"[muted]Human pause[/] [channel]ch:{self._channel_id}[/] "
                f"[count]{pause:.1f}s[/]",
                spinner="dots",
            ):
                await asyncio.sleep(pause)
            return

        # ---- normal jittered delay ----
        jitter = random.uniform(
            config.HUMAN_IMITATION_JITTER_MIN,
            config.HUMAN_IMITATION_JITTER_MAX,
        )
        await asyncio.sleep(config.HUMAN_IMITATION_BASE_DELAY + jitter)
