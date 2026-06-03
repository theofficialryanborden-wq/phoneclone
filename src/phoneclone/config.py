from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class EmulatorConfig:
    """Persisted emulator settings."""

    qemu_path: str = ""
    system_image: str = ""
    ram_mb: int = 2048
    cpu_cores: int = 2
    display_width: int = 540
    display_height: int = 960
    adb_port: int = 5555
    vnc_port: int = 5900
    use_whp: bool = True
    extra_qemu_args: str = ""
    # GPU / performance
    gpu_mode: str = "virtio_gpu"  # virtio_vga | virtio_gpu | qxl
    cpu_mode: str = "auto"  # auto | host | max | qemu64
    video_memory_mb: int = 128
    enable_cpu_pm: bool = True
    auto_start: bool = True
    runtime_ready: bool = False
    # Legacy flag kept for upgrades
    setup_complete: bool = False
    # Location
    location_address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    apply_location_on_boot: bool = True
    # Privacy / anti-detection
    privacy_mode: bool = True
    device_profile: str = "pixel_6"
    apply_privacy_on_boot: bool = True
    # Instance cloning
    template_image: str = ""

    @property
    def config_path(self) -> Path:
        base = Path.home() / ".phoneclone"
        base.mkdir(parents=True, exist_ok=True)
        return base / "config.json"

    def save(self) -> None:
        self.config_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> EmulatorConfig:
        path = cls().config_path
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def needs_setup(self) -> bool:
        from phoneclone.downloads import runtime_ready

        if self.runtime_ready or self.setup_complete:
            return not runtime_ready() and bool(self.validate())
        return True

    def apply_bundled_defaults(self) -> None:
        from phoneclone.paths import PhoneClonePaths

        paths = PhoneClonePaths()
        paths.ensure()
        if not self.qemu_path and paths.qemu_exe.is_file():
            self.qemu_path = str(paths.qemu_exe)
        if not self.system_image and paths.android_disk.is_file():
            self.system_image = str(paths.android_disk)
        if not self.template_image and paths.android_disk.is_file():
            self.template_image = str(paths.android_disk)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.qemu_path:
            errors.append("QEMU path is not set.")
        elif not Path(self.qemu_path).is_file():
            errors.append(f"QEMU executable not found: {self.qemu_path}")
        if not self.system_image:
            errors.append("Android system image is not set.")
        elif not Path(self.system_image).is_file():
            errors.append(f"System image not found: {self.system_image}")
        if self.ram_mb < 512:
            errors.append("RAM must be at least 512 MB.")
        return errors
