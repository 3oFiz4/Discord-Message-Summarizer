from __future__ import annotations

import inspect
import sys
from typing import Sequence, overload

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import DOUBLE
from rich import box

console = Console(stderr=True, highlight=False)


def _get_caller_info() -> dict[str, str]:
    """Detect class name, method name, file and line where Panic was called."""
    stack = inspect.stack()
    # index 2 = the frame that called Panic()
    frame_info = stack[2]

    frame = frame_info.frame
    func_name = frame_info.function
    filename = frame_info.filename
    lineno = frame_info.lineno

    class_name = None
    if "self" in frame.f_locals:
        self_obj = frame.f_locals["self"]
        class_name = getattr(self_obj, "__class__", None).__name__

    location = f"{filename}:{lineno}"
    category = f"{class_name}.{func_name}" if class_name else func_name

    return {
        "class": class_name or "«global»",
        "function": func_name,
        "category": category,
        "location": location,
    }


@overload
def Panic(
    exc_type: type[Exception],
    message: str = "An error occurred",
    *,
    solutions: Sequence[str] | None = None,
    note: str | None = None,
) -> None: ...


@overload
def Panic(
    exc_instance: Exception,
    *,
    solutions: Sequence[str] | None = None,
    note: str | None = None,
) -> None: ...


def Panic(
    exc_or_type: type[Exception] | Exception,
    message: str | None = None,
    *,
    solutions: Sequence[str] | None = None,
    note: str | None = None,
) -> None:
    """
    Raise an exception with a gorgeous Rich panel that includes:
    • Error type + message
    • Exact location (class.method + file:line)
    • List of possible solutions (optional)
    • Extra note (optional)

    Usage examples:
        Panic(ValueError, "Age cannot be negative", solutions=[
            "Make sure the input is positive",
            "Add validation before calling calculate_bonus()"
        ])

        Panic(some_existing_exception, solutions=["Retry the request"])

        Panic(RuntimeError("Database connection failed"), note="Check your internet connection")
    """
    # ------------------------------------------------------------------
    # 1. Build the actual exception instance
    # ------------------------------------------------------------------
    if isinstance(exc_or_type, type) and issubclass(exc_or_type, Exception):
        exc_type = exc_or_type
        exc_message = message or "An error occurred"
        exc = exc_type(exc_message)
    else:
        exc = exc_or_type  # already an Exception instance
        exc_type = type(exc)
        exc_message = message or str(exc)

    # ------------------------------------------------------------------
    # 2. Gather context (class/method)
    # ------------------------------------------------------------------
    info = _get_caller_info()

    # ------------------------------------------------------------------
    # 3. Build the Rich content
    # ------------------------------------------------------------------
    content = Text()

    # Header line
    header = Text()
    header.append("[!] PANIC >>>\n", style="bold white on #ff0000")
    header.append("GOT ::: ", style="bold #ff0000")
    header.append(exc_type.__name__, style="bold white on #ff0000")
    content.append(header)
    content.append("\n")

    # Message
    content.append("WHEN ::: ", style="bold #ffff00")
    content.append(f"{exc_message}\n", style="#ffff00")

    # Location
    content.append("IN ::: ", style="bold #00ffff")
    content.append(f"c:{info['class']} :: ", style="#00ffff")
    content.append(f"fn:{info['function']}\n", style="#00ffff")
    content.append(f"( {info['location']} )\n", style="dim #222222")

    # Solutions
    if solutions:
        content.append("TRY :::\n", style="bold #00ff00")
        for i, sol in enumerate(solutions, 1):
            content.append(f"  {i}. ", style="#00ff00")
            content.append(f"{sol}\n", style="#00ff00")

    # Extra note
    if note:
        content.append("CLUE ::: \n", style="bold #ff00ff")
        content.append(f"  {note}\n", style="#ff00ff")

    # ------------------------------------------------------------------
    # 4. Print the beautiful panel
    # ------------------------------------------------------------------
    console.print("\n")
    console.print(content)
    console.print("\n")
