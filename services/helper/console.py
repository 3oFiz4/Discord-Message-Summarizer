"""
All modules import from here to ensure consistent styling
and a single Console instance across the application.
"""

from rich.console import Console
from rich.theme import Theme

# ── Custom theme ──────────────────────────────────────────────
custom_theme = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
    "muted": "dim white",
    "highlight": "magenta",
    "channel": "blue",
    "count": "cyan bold",
    "timestamp": "dim cyan",
    "path": "underline bright_blue",
})

# ── Shared console instance ───────────────────────────────────
console = Console(theme=custom_theme)
