
"""
Checkpoint Manager
──────────────────
Persists per-channel scraping progress to disk as tiny JSON files.

Each checkpoint stores:
    • channel_id  – which channel this progress belongs to
    • last_message_id – the oldest message ID already fetched
    • total_scraped – running count of messages fetched so far

On restart the scraper reads these files and resumes from
where it left off instead of re-fetching everything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from config import config
from services.helper.error_logger import Panic
from services.helper.console import console

class CheckpointManager:
    """
    Thread-/task-safe checkpoint writer and reader.

    File layout:
        <CHECKPOINT_DIR>/<channel_id>.json
    """

    def __init__(self, checkpoint_dir: Path | None = None) -> None:
        self._dir = checkpoint_dir or config.CHECKPOINT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  PATH HELPER                                                        #
    # ------------------------------------------------------------------ #
    def _path_for(self, channel_id: str) -> Path:
        """Return the checkpoint file path for a given channel."""
        return self._dir / f"{channel_id}.json"

    # ------------------------------------------------------------------ #
    #  SAVE                                                                #
    # ------------------------------------------------------------------ #
    def save(
        self,
        channel_id: str,
        last_message_id: str,
        total_scraped: int,
    ) -> None:
        """
        Persist current scraping progress for *channel_id*.

        Called every ``CHECKPOINT_SAVE_INTERVAL`` messages.
        """
        payload = {
            "channel_id": channel_id,
            "last_message_id": last_message_id,
            "total_scraped": total_scraped,
        }
        path = self._path_for(channel_id)
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            console.print(
                f"  [muted]checkpoint[/] [channel]ch:{channel_id}[/] "
                f"[muted]saved at msg[/] [highlight]{last_message_id}[/] "
                f"[muted]([/][count]{total_scraped}[/] [muted]total)[/]"
            )
        except OSError as exc:
            Panic(
                IOError,
                f"Failed to write checkpoint for channel {channel_id}: {exc}",
                solutions=[
                    f"Check write permissions on {self._dir}",
                    "Ensure disk space is available",
                ],
                note="CheckpointManager.save failed",
            )

    # ------------------------------------------------------------------ #
    #  LOAD                                                                #
    # ------------------------------------------------------------------ #
    def load(self, channel_id: str) -> Optional[dict]:
        """
        Load previously saved progress for *channel_id*.

        Returns ``None`` if no checkpoint exists (fresh scrape).
        """
        path = self._path_for(channel_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            console.print(
                f"  [success]✓[/] [muted]Resuming[/] [channel]ch:{channel_id}[/] "
                f"[muted]from msg[/] [highlight]{data['last_message_id']}[/] "
                f"[muted]([/][count]{data['total_scraped']}[/] [muted]already scraped)[/]"
            )
            return data
        except (json.JSONDecodeError, OSError) as exc:
            Panic(
                IOError,
                f"Corrupted checkpoint for channel {channel_id}: {exc}",
                solutions=[
                    f"Delete {path} and restart",
                    "Check file encoding (must be UTF-8 JSON)",
                ],
                note="CheckpointManager.load failed",
            )
            return None

    # ------------------------------------------------------------------ #
    #  CLEAR                                                               #
    # ------------------------------------------------------------------ #
    def clear(self, channel_id: str) -> None:
        """Remove a checkpoint after a channel is fully scraped."""
        path = self._path_for(channel_id)
        if path.exists():
            path.unlink()
            console.print(
                f"  [success]✓[/] [muted]Checkpoint cleared for[/] "
                f"[channel]ch:{channel_id}[/]"
            )
