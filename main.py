from models.message.message import MessageDTO
from models.message.message_collection import MessageCollection
from datetime import datetime
from config import config
from services.discord.discord_scraper import DiscordScraper
import asyncio as aio
from services.helper.console import console
from services.helper.formatting import format_timestamp
"""
config.DISCORD_TOKEN: env
"""

# ── Install uvloop if available ──
try:
    import uvloop
    uvloop.install()
    _UVLOOP = True
except ImportError:
    _UVLOOP = False

def main() -> None:
    # ── Header ──
    console.print()
    console.print("[info]Discord Scraper[/]", style="bold")
    console.print(f"[muted]Started at[/] [timestamp]{format_timestamp(datetime.now())}[/]")
    console.print()

    # ── Config summary ──
    console.print("[muted]Configuration[/]")
    console.print(f"  [muted]Token[/]          {'[success]set[/]' if config.DISCORD_TOKEN else '[error]MISSING[/]'}")
    console.print(f"  [muted]Guild[/]          [highlight]{config.GUILD_ID or '[warning]NOT SET[/]'}[/]")
    console.print(f"  [muted]Channels[/]       [highlight]{config.CHANNELS}[/]")

    if config.FROM_AUTHORS:
        console.print(f"  [muted]Author Filter[/]  [highlight]{config.FROM_AUTHORS}[/]")
    else:
        console.print(f"  [muted]Author Filter[/]  [muted]ALL (no filter)[/]")

    console.print(f"  [muted]Human Mode[/]     {'[success]ON[/]' if config.HUMAN_IMITATION_ENABLED else '[muted]OFF[/]'}")
    console.print(f"  [muted]Workers[/]        [count]{config.MAX_CONCURRENT_CHANNEL_WORKERS}[/]")
    console.print(f"  [muted]Batch Size[/]     [count]{config.MAX_DISCORD_MESSAGE}[/] [muted]msgs/request[/]")
    console.print(
        f"  [muted]Flush Every[/]    [count]{config.WRITER_FLUSH_BATCH_SIZE}[/] [muted]batches or[/] "
        f"[count]{config.WRITER_FLUSH_INTERVAL_SECONDS}[/][muted]s[/]"
    )
    console.print(f"  [muted]Output Base[/]    [path]{config.OUTPUT_BASE_PATH}[/]")
    console.print(f"  [muted]Checkpoints[/]    [path]{config.CHECKPOINT_DIR}[/]")
    console.print(f"  [muted]Timestamp Fmt[/]  [muted]D-M-YY@H:MM:SS AM/PM[/]")
    console.print(f"  [muted]uvloop[/]         {'[success]active[/]' if _UVLOOP else '[muted]not installed[/]'}")
    console.print()

    # ── Run ──
    scraper = DiscordScraper()

    try:
        aio.run(scraper.run())
    except KeyboardInterrupt:
        console.print()
        console.print("[warning]![/] [warning]Interrupted by user[/]")
        console.print("[muted]Partial data may be saved. Check checkpoints to resume.[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
