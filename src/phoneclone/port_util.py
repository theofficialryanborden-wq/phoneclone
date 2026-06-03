from __future__ import annotations

import subprocess
import sys
from typing import Iterable


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def listening_pids(port: int) -> list[int]:
    """Return PIDs with a LISTENING socket on the given TCP port (best-effort)."""
    if sys.platform != "win32":
        return []
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        creationflags=_creationflags(),
    )
    if result.returncode != 0:
        return []
    needle = f":{port}"
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(pids)


def process_image(pid: int) -> str:
    if sys.platform != "win32":
        return ""
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        creationflags=_creationflags(),
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    # "qemu-system-x86_64.exe","1234",...
    first = result.stdout.strip().split(",")[0].strip('"')
    return first.lower()


def terminate_pids(pids: Iterable[int]) -> list[int]:
    """Force-terminate the given PIDs. Returns PIDs that were signaled."""
    stopped: list[int] = []
    for pid in pids:
        if pid <= 0:
            continue
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            creationflags=_creationflags(),
        )
        if result.returncode == 0:
            stopped.append(pid)
    return stopped


def release_qemu_ports(adb_port: int, vnc_port: int) -> list[int]:
    """Stop orphaned qemu-system-x86_64 listeners blocking PhoneClone ports."""
    targets: list[int] = []
    for port in (adb_port, vnc_port):
        for pid in listening_pids(port):
            image = process_image(pid)
            if image.startswith("qemu-system-x86_64"):
                targets.append(pid)
    return terminate_pids(sorted(set(targets)))
