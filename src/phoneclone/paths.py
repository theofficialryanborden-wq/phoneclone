from __future__ import annotations

from pathlib import Path


class PhoneClonePaths:
    """Standard data directories under %USERPROFILE%\\.phoneclone."""

    def __init__(self) -> None:
        self.root = Path.home() / ".phoneclone"
        self.qemu_dir = self.root / "qemu"
        self.images_dir = self.root / "images"
        self.cache_dir = self.root / "cache"
        self.downloads_dir = self.root / "downloads"

    def ensure(self) -> None:
        for path in (self.root, self.qemu_dir, self.images_dir, self.cache_dir, self.downloads_dir):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def qemu_exe(self) -> Path:
        for name in ("qemu-system-x86_64.exe", "qemu-system-x86_64w.exe"):
            candidate = self.qemu_dir / name
            if candidate.is_file():
                return candidate
        nested = list(self.qemu_dir.rglob("qemu-system-x86_64.exe"))
        if nested:
            return nested[0]
        return self.qemu_dir / "qemu-system-x86_64.exe"

    @property
    def qemu_img(self) -> Path:
        for name in ("qemu-img.exe", "qemu-imgw.exe"):
            candidate = self.qemu_dir / name
            if candidate.is_file():
                return candidate
        nested = list(self.qemu_dir.rglob("qemu-img.exe"))
        if nested:
            return nested[0]
        return self.qemu_dir / "qemu-img.exe"

    @property
    def android_iso(self) -> Path:
        return self.downloads_dir / "android-x86_64.iso"

    @property
    def android_disk(self) -> Path:
        return self.images_dir / "android.img"
