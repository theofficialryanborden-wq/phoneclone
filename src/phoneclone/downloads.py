from __future__ import annotations

import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from phoneclone.paths import PhoneClonePaths

ProgressCallback = Callable[[int, str], None]

# Pinned fallback when directory listing scrape fails.
QEMU_ZIP_FALLBACK = "https://qemu.weilnetz.de/w64/2024/qemu-w64-20241218.zip"
QEMU_LISTING_URL = "https://qemu.weilnetz.de/w64/"

ANDROID_ISO_URLS = (
    "https://zenlayer.dl.sourceforge.net/project/android-x86/Release%209.0/android-x86_64-9.0-r2.iso?viasf=1",
    "https://netactuate.dl.sourceforge.net/project/android-x86/Release%209.0/android-x86_64-9.0-r2.iso?viasf=1",
    "https://sourceforge.net/projects/android-x86/files/Release%209.0/android-x86_64-9.0-r2.iso/download",
)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(value)


def _emit(progress: ProgressCallback | None, percent: int, message: str) -> None:
    if progress:
        progress(max(0, min(100, percent)), message)


class _DownloadReporter:
    def __init__(self, total: int, progress: ProgressCallback | None, label: str) -> None:
        self._total = max(total, 1)
        self._progress = progress
        self._label = label
        self._done = 0

    def __call__(self, block_count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            self._total = total_size
        self._done += block_count * block_size
        pct = int(self._done * 100 / self._total)
        mb = self._done / (1024 * 1024)
        total_mb = self._total / (1024 * 1024)
        _emit(self._progress, pct, f"{self._label}: {mb:.1f} / {total_mb:.1f} MB")


def find_latest_qemu_zip_url() -> str:
    try:
        with urllib.request.urlopen(QEMU_LISTING_URL, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return QEMU_ZIP_FALLBACK

    parser = _LinkParser()
    parser.feed(html)
    zips = [link for link in parser.links if re.search(r"qemu-w64-\d{8}\.zip", link, re.I)]
    if not zips:
        return QEMU_ZIP_FALLBACK

    def sort_key(url: str) -> str:
        match = re.search(r"qemu-w64-(\d{8})\.zip", url, re.I)
        return match.group(1) if match else ""

    best = sorted(zips, key=sort_key)[-1]
    if best.startswith("http"):
        return best
    return urllib.request.urljoin(QEMU_LISTING_URL, best)


def download_file(
    url: str,
    dest: Path,
    *,
    progress: ProgressCallback | None = None,
    label: str = "Downloading",
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    _emit(progress, 0, f"{label}…")
    try:
        urllib.request.urlretrieve(url, tmp, _DownloadReporter(1, progress, label))
    except urllib.error.URLError as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc}") from exc
    tmp.replace(dest)
    _emit(progress, 100, f"{label} complete.")
    return dest


def download_qemu(progress: ProgressCallback | None = None) -> Path:
    paths = PhoneClonePaths()
    paths.ensure()
    url = find_latest_qemu_zip_url()
    zip_path = paths.cache_dir / "qemu-portable.zip"
    _emit(progress, 0, "Fetching QEMU package list…")
    download_file(url, zip_path, progress=progress, label="QEMU")
    _emit(progress, 95, "Extracting QEMU…")
    if paths.qemu_dir.exists():
        shutil.rmtree(paths.qemu_dir, ignore_errors=True)
    paths.qemu_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(paths.qemu_dir)
    exe = paths.qemu_exe
    if not exe.is_file():
        raise RuntimeError("QEMU archive extracted but qemu-system-x86_64.exe was not found.")
    _emit(progress, 100, f"QEMU ready at {exe}")
    return exe


def download_android_iso(progress: ProgressCallback | None = None) -> Path:
    paths = PhoneClonePaths()
    paths.ensure()
    dest = paths.android_iso
    last_error = ""
    for url in ANDROID_ISO_URLS:
        try:
            return download_file(url, dest, progress=progress, label="Android-x86 ISO")
        except RuntimeError as exc:
            last_error = str(exc)
            if dest.exists():
                dest.unlink(missing_ok=True)
    raise RuntimeError(last_error or "Could not download Android-x86 ISO.")


def create_android_disk(
    qemu_img: Path | str,
    dest: Path | None = None,
    size_gb: int = 16,
    *,
    progress: ProgressCallback | None = None,
) -> Path:
    paths = PhoneClonePaths()
    paths.ensure()
    disk = dest or paths.android_disk
    qemu_img_path = Path(qemu_img)
    if not qemu_img_path.is_file():
        raise FileNotFoundError(f"qemu-img not found: {qemu_img_path}")
    _emit(progress, 0, f"Creating {size_gb} GB disk image…")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [str(qemu_img_path), "create", "-f", "raw", str(disk), f"{size_gb}G"],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "qemu-img create failed.")
    _emit(progress, 100, f"Disk image created: {disk}")
    return disk


def launch_android_installer(qemu_exe: str, iso_path: str, disk_path: str, log: Callable[[str], None] | None = None) -> subprocess.Popen[str]:
    """Boot the Android-x86 installer in a visible window (one-time setup)."""
    _log = log or (lambda _m: None)
    cmd = [
        qemu_exe,
        "-name",
        "PhoneClone-Android-Install",
        "-machine",
        "q35,accel=whpx:tcg",
        "-cpu",
        "max",
        "-m",
        "2048",
        "-smp",
        "2",
        "-cdrom",
        iso_path,
        "-drive",
        f"file={disk_path},format=raw,if=virtio",
        "-boot",
        "d",
        "-device",
        "virtio-gpu-pci",
        "-display",
        "sdl",
        "-usb",
        "-device",
        "usb-tablet",
    ]
    _log("Launching Android installer: " + " ".join(cmd))
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def bundled_qemu_ready() -> bool:
    return PhoneClonePaths().qemu_exe.is_file()


def bundled_android_ready() -> bool:
    paths = PhoneClonePaths()
    return paths.android_disk.is_file() and paths.android_disk.stat().st_size > 512 * 1024 * 1024
