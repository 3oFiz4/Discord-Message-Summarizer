from __future__ import annotations
"""How it works, goes like this. i tried a different method unlike anybody else when scraping a message """

"""
DiscordScraper  (Orchestrator)
──────────────────────────────
Top-level controller that:

    1. Discovers channels (or uses the explicit list from config)
    2. Spawns one ``ChannelScraper`` (producer) per channel,
       bounded by a concurrency semaphore
    3. Spawns a single ``Writer`` (consumer) that drains the
       shared queue and flushes to disk
    4. Waits for all producers to finish, then signals the
       consumer to do a final flush and exit

The entire pipeline runs on a single event loop (uvloop when
available) using only async I/O – no threads, no subprocesses.
"""


import asyncio
from typing import Any

import aiohttp

from config import config
from services.helper.error_logger import Panic
from .checkpoint_manager import CheckpointManager
from .channel_scraper import ChannelScraper
from .writer import Writer
from services.helper.console import console


class DiscordScraper:
    """
    Manages the full scraping lifecycle.

    Usage:
        scraper = DiscordScraper()
        asyncio.run(scraper.run())
    """

    def __init__(self) -> None:
        # ---- validate essential config ----
        if not config.DISCORD_TOKEN:
            Panic(
                ValueError,
                "DISCORD_TOKEN is empty",
                solutions=[
                    "Set config.DISCORD_TOKEN = 'your-token'",
                    "Or export DISCORD_TOKEN as an environment variable",
                ],
                note="DiscordScraper.__init__ token check failed",
            )

        # ---- shared async primitives (created in run()) ----
        self._queue: asyncio.Queue | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._stop_event: asyncio.Event | None = None

        # ---- checkpoint manager ----
        self._checkpoint = CheckpointManager()

    # ================================================================== #
    #  PUBLIC                                                              #
    # ================================================================== #
    async def run(self) -> None:
        """
        Entry point.  Call with ``asyncio.run(scraper.run())``.
        """
        # ---- build primitives on the running loop ----
        self._queue = asyncio.Queue(maxsize=config.QUEUE_MAX_BATCHES)
        self._semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_CHANNEL_WORKERS)
        self._stop_event = asyncio.Event()

        # ── Discover channels ──
        with console.status(
            "[info]Discovering channels...[/]",
            spinner="dots",
        ):
            channel_ids = await self._resolve_channels()

        # ---- resolve channel list ----
        channel_ids = await self._resolve_channels()
        if not channel_ids:
            Panic(
                ValueError,
                "No channels to scrape",
                solutions=[
                    "Set config.CHANNELS to a list of channel IDs",
                    'Or use ["all"] with a valid GUILD_ID',
                ],
                note="DiscordScraper.run empty channel list",
            )
            return  # unreachable after Panic, but satisfies linter

        console.print()
        console.print(
            f"[success]✓[/] [muted]Found[/] [count]{len(channel_ids)}[/] "
            f"[muted]channel(s) to scrape[/]"
        )
        for cid in channel_ids:
            console.print(f"  [muted]•[/] [channel]{cid}[/]")
        console.print()

        # ---- launch producers + consumer ----
        async with aiohttp.ClientSession() as session:
            # Consumer (Writer)
            writer = Writer(self._queue)
            consumer_task = asyncio.create_task(
                writer.run(self._stop_event),
                name="writer",
            )

            # Producers (one ChannelScraper per channel)
            producer_tasks = [
                asyncio.create_task(
                    ChannelScraper(
                        channel_id=cid,
                        session=session,
                        queue=self._queue,
                        semaphore=self._semaphore,
                        checkpoint_mgr=self._checkpoint,
                    ).run(),
                    name=f"channel-{cid}",
                )
                for cid in channel_ids
            ]

            console.print(
                f"[info]●[/] [muted]Launched[/] [count]{len(producer_tasks)}[/] "
                f"[muted]producer(s) +[/] [count]1[/] [muted]consumer[/]"
            )

            # ---- wait for all producers to finish ----
            await asyncio.gather(*producer_tasks, return_exceptions=True)

            # ---- signal consumer to drain remaining items and exit ----
            self._stop_event.set()
            await consumer_task

        console.print()
        console.print("[success]✓[/] [success]All done![/]")
        console.print()

    # ================================================================== #
    #  CHANNEL DISCOVERY                                                   #
    # ================================================================== #
    async def _resolve_channels(self) -> list[str]:
        """
        If ``config.CHANNELS`` is ``["all"]``, query the Discord API
        for every text channel in the guild.  Otherwise return the
        explicit list from config.
        """
        if config.CHANNELS != ["all"]:
            return config.CHANNELS

        # ---- discover from guild ----
        if not config.GUILD_ID:
            Panic(
                ValueError,
                "GUILD_ID is required when CHANNELS=['all']",
                solutions=[
                    "Set config.GUILD_ID = 'your-guild-id'",
                    "Or list channel IDs explicitly in config.CHANNELS",
                ],
                note="DiscordScraper._resolve_channels guild check failed",
            )
            return []

        url = f"{config.API_BASE}/guilds/{config.GUILD_ID}/channels"
        headers = {
            "Authorization": config.DISCORD_TOKEN,
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    Panic(
                        RuntimeError,
                        f"Failed to fetch guild channels: HTTP {resp.status} – {body}",
                        solutions=[
                            "Check DISCORD_TOKEN and GUILD_ID",
                            "Ensure the bot is in the guild",
                        ],
                        note="DiscordScraper._resolve_channels HTTP error",
                    )
                    return []

                data: list[dict[str, Any]] = await resp.json()

        # Type 0 = GUILD_TEXT channel
        text_channels = [
            str(ch["id"]) for ch in data if ch.get("type") == 0
        ]

        print(f"[orchestrator] Discovered {len(text_channels)} text channels")
        return text_channels
