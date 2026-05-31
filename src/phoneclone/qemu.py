from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from phoneclone.config import EmulatorConfig


class QemuEmulator:
    """Launches and manages a QEMU Android-x86 virtual machine."""

    WINDOW_TITLE = "PhoneClone-Android"
    PRIVACY_WINDOW_TITLE = "android"

    GPU_MODES = {
        "virtio_vga": "VirtIO VGA (maximum compatibility)",
        "virtio_gpu": "VirtIO GPU (recommended)",
        "qxl": "QXL (legacy 2D acceleration)",
    }

    CPU_MODES = {
        "auto": "Auto (best for current settings)",
        "host": "Host passthrough (fastest on WHPX)",
        "max": "max (feature-rich guest CPU)",
        "qemu64": "qemu64 (compatible baseline)",
    }

    def __init__(self, config: EmulatorConfig, log: Callable[[str], None] | None = None) -> None:
        self.config = config
        self._log = log or (lambda _msg: None)
        self._process: subprocess.Popen[str] | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _drive_format(image_path: str) -> str:
        lower = image_path.lower()
        if lower.endswith(".qcow2"):
            return "qcow2"
        return "raw"

    def _machine_arg(self, cfg: EmulatorConfig) -> str:
        if cfg.use_whp:
            parts = ["q35", "accel=whpx:tcg"]
            if cfg.enable_cpu_pm:
                parts.append("kernel-irqchip=on")
            return ",".join(parts)
        return "q35,accel=tcg"

    def _cpu_arg(self, cfg: EmulatorConfig) -> str:
        mode = cfg.cpu_mode
        if mode != "auto":
            return mode
        if cfg.privacy_mode:
            return "max"
        if cfg.use_whp:
            return "host"
        return "qemu64"

    def _gpu_args(self, cfg: EmulatorConfig) -> list[str]:
        if cfg.gpu_mode == "qxl":
            ram = max(cfg.video_memory_mb, 16) * 1024 * 1024
            return ["-device", f"qxl-vga,ram_size={ram},vram_size={ram}"]
        if cfg.gpu_mode == "virtio_gpu":
            return [
                "-device",
                f"virtio-gpu-pci,max_outputs=1",
            ]
        return ["-device", "virtio-vga"]

    def build_command(self) -> list[str]:
        cfg = self.config
        vnc_display = max(cfg.vnc_port - 5900, 0)
        privacy = cfg.privacy_mode
        window_name = self.PRIVACY_WINDOW_TITLE if privacy else self.WINDOW_TITLE
        drive_fmt = self._drive_format(cfg.system_image)
        cmd = [
            cfg.qemu_path,
            "-name",
            window_name,
            "-machine",
            self._machine_arg(cfg),
            "-cpu",
            self._cpu_arg(cfg),
            "-smp",
            str(cfg.cpu_cores),
            "-m",
            str(cfg.ram_mb),
            "-drive",
            f"file={cfg.system_image},format={drive_fmt},if=virtio,cache=writeback,aio=threads",
            "-netdev",
            f"user,id=net0,hostfwd=tcp::{cfg.adb_port}-:5555",
            "-device",
            "virtio-net-pci,netdev=net0",
            *self._gpu_args(cfg),
            "-display",
            f"vnc=127.0.0.1:{vnc_display}",
            "-usb",
            "-device",
            "usb-tablet",
            "-audiodev",
            "dsound,id=snd0",
            "-device",
            "intel-hda",
            "-device",
            "hda-duplex,audiodev=snd0",
            "-rtc",
            "base=localtime",
            "-boot",
            "order=c",
        ]
        if cfg.enable_cpu_pm and cfg.use_whp:
            cmd.extend(["-overcommit", "cpu-pm=on"])
        if cfg.extra_qemu_args.strip():
            cmd.extend(cfg.extra_qemu_args.split())
        return cmd

    def start(self) -> None:
        if self.is_running:
            raise RuntimeError("Emulator is already running.")

        errors = self.config.validate()
        if errors:
            raise ValueError("\n".join(errors))

        cmd = self.build_command()
        self._log("Starting QEMU: " + " ".join(f'"{part}"' if " " in part else part for part in cmd))
        if self.config.gpu_mode == "virtio_gpu":
            self._log("GPU: VirtIO GPU (2D acceleration via guest driver).")
        elif self.config.gpu_mode == "qxl":
            self._log("GPU: QXL display adapter.")

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )

    def read_output_line(self) -> str | None:
        if not self._process or not self._process.stdout:
            return None
        return self._process.stdout.readline()

    def stop(self) -> None:
        if not self._process:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
        self._process = None
        self._log("Emulator stopped.")

    @staticmethod
    def find_qemu() -> str:
        from phoneclone.paths import PhoneClonePaths

        bundled = PhoneClonePaths().qemu_exe
        if bundled.is_file():
            return str(bundled)

        candidates = [
            Path(r"C:\Program Files\qemu\qemu-system-x86_64.exe"),
            Path(r"C:\Program Files\qemu\qemu-system-x86_64w.exe"),
            Path.home() / "scoop" / "apps" / "qemu" / "current" / "qemu-system-x86_64.exe",
        ]
        for path in candidates:
            if path.is_file():
                return str(path)
        return ""

    @staticmethod
    def find_qemu_img() -> str:
        from phoneclone.paths import PhoneClonePaths

        bundled = PhoneClonePaths().qemu_img
        if bundled.is_file():
            return str(bundled)
        for exe in (QemuEmulator.find_qemu(),):
            if not exe:
                continue
            sibling = Path(exe).with_name("qemu-img.exe")
            if sibling.is_file():
                return str(sibling)
            sibling_w = Path(exe).with_name("qemu-imgw.exe")
            if sibling_w.is_file():
                return str(sibling_w)
        return ""

    @staticmethod
    def whpx_available() -> bool:
        exe = QemuEmulator.find_qemu()
        if not exe:
            return False
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [exe, "-accel", "whpx"],
            capture_output=True,
            text=True,
            creationflags=flags,
        )
        combined = (result.stdout + result.stderr).lower()
        return "whpx" in combined and "not supported" not in combined and "failed" not in combined
