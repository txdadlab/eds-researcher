"""Generate macOS launchd plist for weekly scheduled runs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.eds-researcher.weekly</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv_path}</string>
        <string>run</string>
        <string>--project</string>
        <string>{project_dir}</string>
        <string>eds-researcher</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>{weekday}</integer>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/eds-researcher-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/eds-researcher-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:{extra_path}</string>
    </dict>
</dict>
</plist>
"""


def generate_plist(
    project_dir: str | Path | None = None,
    weekday: int = 1,  # Monday
    hour: int = 9,
) -> str:
    """Generate launchd plist content for weekly scheduling.

    Args:
        project_dir: Path to the eds-researcher project root.
        weekday: Day of week (1=Monday, 7=Sunday).
        hour: Hour of day (0-23).

    Returns:
        The plist XML content.
    """
    project_dir = Path(project_dir or os.getcwd()).resolve()
    log_dir = project_dir / "data"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Find uv binary
    uv_path = _find_uv()

    return PLIST_TEMPLATE.format(
        uv_path=uv_path,
        project_dir=str(project_dir),
        log_dir=str(log_dir),
        weekday=weekday,
        hour=hour,
        extra_path=str(Path(uv_path).parent),
    )


def install_plist(project_dir: str | Path | None = None, weekday: int = 1, hour: int = 9) -> Path:
    """Write and load the launchd plist.

    Returns the path to the installed plist file.
    """
    plist_content = generate_plist(project_dir, weekday, hour)
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.eds-researcher.weekly.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Unload existing if present
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

    plist_path.write_text(plist_content)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

    return plist_path


def _find_uv() -> str:
    """Find the uv binary path."""
    result = subprocess.run(["which", "uv"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    # Common locations
    for path in [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/opt/homebrew/bin/uv"),
    ]:
        if path.exists():
            return str(path)
    return "uv"  # Hope it's on PATH
