from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Literal

from phoneclone.paths import PhoneClonePaths

ProgressCallback = Callable[[int, str], None]

QEMU_LISTING_URL = "https://qemu.weilnetz.de/w64/"
QEMU_SETUP_FALLBACK = "https://qemu.weilnetz.de/w64/qemu-w64-setup-20260501.exe"
QEMU_ZIP_FALLBACK = (
    "https://github.com/ganarcasas/qemu-portable/releases/download/20241220/qemu-portable-20241220.zip"
)
QEMU_SETUP_RE = re.compile(r"qemu-w64-setup-(\d{8})\.exe", re.I)
QEMU_ZIP_RE = re.compile(r"qemu-w64-(\d{8})\.zip", re.I)

PLATFORM_TOOLS_URL = (
    "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
)

# Pre-installed Android-x86 VirtualBox images (no ISO install required).
ANDROID_RUNTIME_URLS = (
    "https://zenlayer.dl.sourceforge.net/project/linuxvmimages/files/VirtualBox/A/Android_x86_64BIT_9.0_r2_VB.zip?viasf=1",
    "https://netactuate.dl.sourceforge.net/project/linuxvmimages/files/VirtualBox/A/Android_x86_64BIT_9.0_r2_VB.zip?viasf=1",
    "https://sourceforge.net/projects/linuxvmimages/files/VirtualBox/A/Android_x86_64BIT_9.0_r2_VB.zip/download",
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


def find_latest_qemu_download() -> tuple[str, Literal["exe", "zip"]]:
    try:
        with urllib.request.urlopen(QEMU_LISTING_URL, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return QEMU_SETUP_FALLBACK, "exe"

    parser = _LinkParser()
    parser.feed(html)
    setups = [link for link in parser.links if QEMU_SETUP_RE.search(link)]
    zips = [link for link in parser.links if QEMU_ZIP_RE.search(link)]

    def _pick_newest(links: list[str], pattern: re.Pattern[str]) -> str:
        dated: list[tuple[str, str]] = []
        for link in links:
            match = pattern.search(link)
            if match:
                dated.append((match.group(1), link))
        if not dated:
            return links[-1]
        dated.sort(key=lambda item: item[0])
        return dated[-1][1]

    if setups:
        best = _pick_newest(setups, QEMU_SETUP_RE)
        url = best if best.startswith("http") else urllib.request.urljoin(QEMU_LISTING_URL, best)
        return url, "exe"
    if zips:
        best = _pick_newest(zips, QEMU_ZIP_RE)
        url = best if best.startswith("http") else urllib.request.urljoin(QEMU_LISTING_URL, best)
        return url, "zip"
    return QEMU_SETUP_FALLBACK, "exe"


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


def _install_qemu_from_setup(installer: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [str(installer), "/S", f"/D={dest.resolve()}"],
        creationflags=flags,
        timeout=900,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"QEMU installer exited with code {result.returncode}.")


def _extract_qemu_zip(zip_path: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(dest)


def download_platform_tools(progress: ProgressCallback | None = None) -> Path:
    """Download Google platform-tools (adb) into ~/.phoneclone/platform-tools."""
    paths = PhoneClonePaths()
    paths.ensure()
    if paths.adb_exe.is_file():
        return paths.adb_exe

    zip_path = paths.cache_dir / "platform-tools.zip"
    _emit(progress, 0, "Downloading ADB tools…")
    download_file(PLATFORM_TOOLS_URL, zip_path, progress=progress, label="ADB")
    _emit(progress, 95, "Installing ADB tools…")
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(paths.root)
    if not paths.adb_exe.is_file():
        raise RuntimeError("platform-tools archive did not contain adb.exe.")
    _emit(progress, 100, "ADB tools ready.")
    return paths.adb_exe


def download_qemu(progress: ProgressCallback | None = None) -> Path:
    paths = PhoneClonePaths()
    paths.ensure()
    url, kind = find_latest_qemu_download()
    _emit(progress, 0, "Fetching emulator engine…")
    errors: list[str] = []

    if kind == "exe":
        installer_path = paths.cache_dir / "qemu-installer.exe"
        try:
            download_file(url, installer_path, progress=progress, label="Engine")
            _emit(progress, 95, "Installing engine…")
            _install_qemu_from_setup(installer_path, paths.qemu_dir)
            exe = paths.qemu_exe
            if exe.is_file():
                _emit(progress, 100, "Engine ready.")
                return exe
            errors.append("Engine install finished but qemu-system-x86_64.exe was not found.")
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))

    zip_url = url if kind == "zip" else QEMU_ZIP_FALLBACK
    zip_path = paths.cache_dir / "qemu-portable.zip"
    try:
        if kind != "zip":
            _emit(progress, 5, "Retrying with portable engine…")
        download_file(zip_url, zip_path, progress=progress, label="Engine")
        _emit(progress, 95, "Extracting engine…")
        _extract_qemu_zip(zip_path, paths.qemu_dir)
        exe = paths.qemu_exe
        if not exe.is_file():
            raise RuntimeError("Engine archive extracted but qemu-system-x86_64.exe was not found.")
        _emit(progress, 100, "Engine ready.")
        return exe
    except RuntimeError as exc:
        errors.append(str(exc))

    raise RuntimeError(errors[-1] if errors else "Could not download the emulator engine.")


def _find_disk_in_tree(root: Path) -> Path | None:
    for ext in (".vdi", ".vmdk", ".img", ".qcow2"):
        matches = sorted(root.rglob(f"*{ext}"))
        if matches:
            return max(matches, key=lambda p: p.stat().st_size)
    return None


def _extract_archive(archive: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(dest)
        return
    raise RuntimeError(f"Unsupported archive format: {archive.name}")


def _convert_to_raw_disk(source: Path, dest: Path, qemu_img: Path) -> None:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    fmt = "vdi" if source.suffix.lower() == ".vdi" else "vmdk" if source.suffix.lower() == ".vmdk" else "raw"
    if source.suffix.lower() == ".img":
        shutil.copy2(source, dest)
        return
    result = subprocess.run(
        [str(qemu_img), "convert", "-f", fmt, "-O", "raw", str(source), str(dest)],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not prepare Android disk.")


def download_android_runtime(progress: ProgressCallback | None = None) -> Path:
    """Download a pre-installed Android-x86 image and prepare it for boot (no ISO step)."""
    paths = PhoneClonePaths()
    paths.ensure()
    archive_path = paths.cache_dir / "android-runtime.zip"
    extract_dir = paths.cache_dir / "android-runtime-extract"

    last_error = ""
    for url in ANDROID_RUNTIME_URLS:
        try:
            download_file(url, archive_path, progress=progress, label="Android")
            break
        except RuntimeError as exc:
            last_error = str(exc)
            archive_path.unlink(missing_ok=True)
    else:
        raise RuntimeError(last_error or "Could not download Android runtime.")

    _emit(progress, 92, "Unpacking Android…")
    _extract_archive(archive_path, extract_dir)
    disk_source = _find_disk_in_tree(extract_dir)
    if not disk_source:
        raise RuntimeError("Downloaded Android package did not contain a disk image.")

    qemu_img = paths.qemu_img
    if not qemu_img.is_file():
        raise RuntimeError("Engine must be installed before preparing Android.")

    _emit(progress, 96, "Preparing Android (one-time)…")
    if paths.android_disk.exists():
        paths.android_disk.unlink(missing_ok=True)
    _convert_to_raw_disk(disk_source, paths.android_disk, qemu_img)
    _emit(progress, 100, "Android is ready to play.")
    return paths.android_disk


def runtime_ready() -> bool:
    paths = PhoneClonePaths()
    return (
        paths.qemu_exe.is_file()
        and paths.android_disk.is_file()
        and paths.android_disk.stat().st_size > 256 * 1024 * 1024
    )


def bundled_qemu_ready() -> bool:
    return PhoneClonePaths().qemu_exe.is_file()


def bundled_android_ready() -> bool:
    paths = PhoneClonePaths()
    return paths.android_disk.is_file() and paths.android_disk.stat().st_size > 256 * 1024 * 1024
