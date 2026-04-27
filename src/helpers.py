import os
import sys


def format_time_duration(seconds: float) -> str:
    """Render elapsed seconds as a small human-readable duration."""

    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}hr")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def print_checkmarked_message(message: str) -> None:
    """Print a green checkmark line when supported (plain text otherwise)."""

    mark = "\N{CHECK MARK}"
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        line = f"\033[32m[{mark}]\033[0m {message}"
    else:
        line = f"[{mark}] {message}"
    print(line, flush=True)
