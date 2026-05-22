"""
Writer  (Consumer)
──────────────────
Reads batches of raw message dicts from the async queue,
converts them into validated MessageDTO objects,
optionally filters by author, buffers them in memory,
and flushes to disk in bulk when either threshold is reached.
"""

from __future__ import annotations

import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from config import config
from models.message.message import MessageDTO
from services.helper.error_logger import Panic
from ..helper.formatting import format_timestamp_filesafe
from services.helper.console import console

class Writer:
    """
    Async consumer that drains the shared queue, validates each
    message through MessageDTO, and bulk-writes to CSV.
    """

    _CSV_COLUMNS = [
        "ID",
        "message_id",
        "channel_id",
        "guild_id",
        "author_id",
        "content",
        "created_at",
        "edited_at",
        "reply_to_message_id",
        "attachment_urls",
    ]

    def __init__(
        self,
        queue: asyncio.Queue,
        output_base: str | None = None,
    ) -> None:
        self._queue = queue
        self._output_base = output_base or config.OUTPUT_BASE_PATH

        # ---- internal buffer of validated MessageDTO objects ----
        self._buffer: list[MessageDTO] = []
        self._batch_count: int = 0
        self._total_written: int = 0
        self._total_skipped: int = 0  # messages filtered out by author
        self._last_flush_time: float = time.monotonic()

        # ---- track which files have had headers written ----
        # key = resolved file path string
        self._headers_written: set[str] = set()

        # ---- track channel → output path mapping ----
        # key = channel_id, value = resolved Path
        self._channel_paths: dict[str, Path] = {}

        # ---- precompute author filter set for O(1) lookup ----
        self._author_filter: set[str] | None = None
        if config.FROM_AUTHORS is not None:
            self._author_filter = set(config.FROM_AUTHORS)

    # ================================================================== #
    #  PUBLIC ENTRY POINT                                                  #
    # ================================================================== #
    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Main consumer loop.

        Runs until *stop_event* is set AND the queue is drained.
        """
        console.print("[info]●[/] [muted]Writer started[/]")
        
        while True:
            try:
                item = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0,
                )
                self._ingest(item)
                self._queue.task_done()

            except asyncio.TimeoutError:
                pass

            self._maybe_flush()

            if stop_event.is_set() and self._queue.empty():
                self._flush()
                console.print()
                console.print(
                    f"[success]✓[/] [success]Writer complete[/] [muted]—[/] "
                    f"[count]{self._total_written}[/] [muted]written,[/] "
                    f"[count]{self._total_skipped}[/] [muted]skipped[/]"
                )
                break

    
    # ================================================================== #
    #  OUTPUT PATH BUILDER                                                 #
    # ================================================================== #
    def _resolve_output_path(
        self,
        channel_id: str,
        guild_id: str,
        author_name: str,
    ) -> Path:
        """
        Build the dynamic output path:
            <base>_<username>_ON_<guild_id>-<channel_id>_<timestamp>.csv

        The timestamp is captured once per channel at the moment
        the first batch arrives.

        Example:
            output/log_alice_ON_999-10_1-12-26@6-45-20_PM.csv
        """
        # ---- return cached path if already resolved ----
        if channel_id in self._channel_paths:
            return self._channel_paths[channel_id]

        # ---- build filename ----
        now = datetime.now()
        ts = format_timestamp_filesafe(now)

        # Clean username for filesystem safety
        safe_name = (
            author_name.lower()
            .replace("#", "")
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        filename = f"{self._output_base}_{safe_name}_ON_{guild_id}-{channel_id}_{ts}.csv"
        path = Path(filename)

        # ---- ensure parent directory exists ----
        path.parent.mkdir(parents=True, exist_ok=True)

        # ---- cache ----
        self._channel_paths[channel_id] = path
        console.print(
            f"[success]✓[/] [muted]Output file created:[/] [path]{path}[/]"
        )

        return path

    # ================================================================== #
    #  INGEST                                                              #
    # ================================================================== #
    def _ingest(self, item: dict[str, Any]) -> None:
        """
        Accept a queue item, filter by author, convert to MessageDTO,
        and resolve the output path on first encounter.
        """
        channel_id = item["channel_id"]
        raw_messages: list[dict] = item["messages"]

        for msg in raw_messages:
            author = msg.get("author", {})
            author_id_str = str(author.get("id", ""))

            # ---- author filter ----
            if self._author_filter is not None:
                if author_id_str not in self._author_filter:
                    self._total_skipped += 1
                    continue

            # ---- resolve output path on first message per channel ----
            if channel_id not in self._channel_paths:
                # Use the actual Discord username (not display_name)
                username = author.get("username", "unknown")
                guild_id = str(msg.get("guild_id", "DM"))
                self._resolve_output_path(channel_id, guild_id, username)

            # ---- convert to MessageDTO ----
            dto = self._to_dto(msg, channel_id)
            if dto is not None:
                self._buffer.append(dto)

        self._batch_count += 1

    # ================================================================== #
    #  RAW DICT → MessageDTO                                               #
    # ================================================================== #
    @staticmethod
    def _to_dto(msg: dict[str, Any], channel_id: str) -> Optional[MessageDTO]:
        """
        Convert a raw Discord message JSON object into a
        validated MessageDTO instance.

        Returns None if the message cannot be parsed (malformed).
        """
        try:
            author = msg.get("author", {})
            attachments = msg.get("attachments", [])

            # ---- parse attachment URLs ----
            attachment_urls = [
                a["url"] for a in attachments
                if a.get("url", "").startswith(("http://", "https://"))
            ]

            # ---- parse reply reference ----
            ref = msg.get("message_reference", {})
            reply_to_raw = ref.get("message_id") if ref else None
            reply_to = int(reply_to_raw) if reply_to_raw else None

            # ---- parse timestamps ----
            created_at_str = msg.get("timestamp", "")
            # Discord ISO format: 2026-05-22T10:00:00.000000+00:00
            created_at = datetime.fromisoformat(created_at_str)

            edited_at_str = msg.get("edited_timestamp")
            edited_at = (
                datetime.fromisoformat(edited_at_str)
                if edited_at_str
                else None
            )

            # ---- parse guild_id (may be missing in DMs) ----
            guild_id_raw = msg.get("guild_id")
            guild_id = int(guild_id_raw) if guild_id_raw else None

            return MessageDTO(
                ID=None,  # auto-assigned by DB if using MessageCollection
                message_id=int(msg["id"]),
                channel_id=int(channel_id),
                guild_id=guild_id,
                author_id=int(author.get("id", 0)),
                content=msg.get("content", ""),
                created_at=created_at,
                edited_at=edited_at,
                reply_to_message_id=reply_to,
                attachment_urls=attachment_urls,
            )

        except (KeyError, ValueError, TypeError) as exc:
            # Malformed message – log and skip rather than crash
            msg_id = msg.get("id", "unknown")
            console.print(
                f"  [warning]![/] [muted]Skipping malformed msg[/] "
                f"[highlight]{msg_id}[/] [muted]—[/] [warning]{exc}[/]"
            )
            return None
    
    # ================================================================== #
    #  RAW DICT → MessageDTO                                               #
    # ================================================================== #
    @staticmethod
    def _to_dto(msg: dict[str, Any], channel_id: str) -> Optional[MessageDTO]:
        """
        Convert a raw Discord message JSON into a validated MessageDTO.
        Returns None if the message is malformed.
        """
        try:
            author = msg.get("author", {})
            attachments = msg.get("attachments", [])

            attachment_urls = [
                a["url"] for a in attachments
                if a.get("url", "").startswith(("http://", "https://"))
            ]

            ref = msg.get("message_reference", {})
            reply_to_raw = ref.get("message_id") if ref else None
            reply_to = int(reply_to_raw) if reply_to_raw else None

            created_at_str = msg.get("timestamp", "")
            created_at = datetime.fromisoformat(created_at_str)

            edited_at_str = msg.get("edited_timestamp")
            edited_at = (
                datetime.fromisoformat(edited_at_str)
                if edited_at_str
                else None
            )

            guild_id_raw = msg.get("guild_id")
            guild_id = int(guild_id_raw) if guild_id_raw else None

            return MessageDTO(
                ID=None,
                message_id=int(msg["id"]),
                channel_id=int(channel_id),
                guild_id=guild_id,
                author_id=int(author.get("id", 0)),
                content=msg.get("content", ""),
                created_at=created_at,
                edited_at=edited_at,
                reply_to_message_id=reply_to,
                attachment_urls=attachment_urls,
            )

        except (KeyError, ValueError, TypeError) as exc:
            msg_id = msg.get("id", "unknown")
            print(f"[writer] Skipping malformed message {msg_id}: {exc}")
            return None

    # ================================================================== #
    #  FLUSH LOGIC                                                         #
    # ================================================================== #
    def _maybe_flush(self) -> None:
        """Check both thresholds and flush if either is exceeded."""
        if not self._buffer:
            return

        elapsed = time.monotonic() - self._last_flush_time
        batch_threshold = self._batch_count >= config.WRITER_FLUSH_BATCH_SIZE
        time_threshold = elapsed >= config.WRITER_FLUSH_INTERVAL_SECONDS

        if batch_threshold or time_threshold:
            self._flush()

    def _flush(self) -> None:
        """
        Bulk-write the buffer to the appropriate per-channel CSV file(s).

        Groups buffered DTOs by channel_id so each goes to its own file.
        """
        if not self._buffer:
            return

        # ---- group by channel ----
        by_channel: dict[str, list[MessageDTO]] = {}
        for dto in self._buffer:
            cid = str(dto.channel_id)
            by_channel.setdefault(cid, []).append(dto)

        # ---- write each channel's chunk ----
        for channel_id, dtos in by_channel.items():
            path = self._channel_paths.get(channel_id)
            if path is None:
                # Shouldn't happen, but guard anyway
                console.print(
                    f"  [warning]![/] [muted]No path for[/] "
                    f"[channel]ch:{channel_id}[/] [warning]skipping flush[/]"
                )
                continue

            try:
                path_str = str(path)
                with open(path, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=self._CSV_COLUMNS)

                    # ---- header only once per file ----
                    if path_str not in self._headers_written:
                        writer.writeheader()
                        self._headers_written.add(path_str)

                    for dto in dtos:
                        row = dto.to_dict
                        filtered_row = {k: row.get(k, "") for k in self._CSV_COLUMNS}
                        writer.writerow(filtered_row)

            except OSError as exc:
                Panic(
                    IOError,
                    f"Failed to write to {path}: {exc}",
                    solutions=[
                        "Check file permissions",
                        "Check available disk space",
                        f"Verify path: {path.resolve()}",
                    ],
                    note="Writer._flush failed",
                )

        count = len(self._buffer)
        self._total_written += count
        console.print(
            f"  [success]↑[/] [muted]Flushed[/] [count]{count}[/] [muted]msgs[/] "
            f"[muted]([/][count]{self._total_written}[/] [muted]total)[/]"
        )

        # ---- reset ----
        self._buffer.clear()
        self._batch_count = 0
        self._last_flush_time = time.monotonic()
