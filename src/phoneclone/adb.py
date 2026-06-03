from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def find_adb() -> str:
    """Resolve adb.exe: bundled install, common SDK paths, then PATH."""
    from phoneclone.paths import PhoneClonePaths

    bundled = PhoneClonePaths().adb_exe
    if bundled.is_file():
        return str(bundled)

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(local_app) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(r"C:\Android\platform-tools\adb.exe"),
            Path.home() / "scoop" / "apps" / "adb" / "current" / "adb.exe",
        ]
        for path in candidates:
            if path.is_file():
                return str(path)

    found = shutil.which("adb")
    return found or ""


class AdbClient:
    """Minimal ADB wrapper for Android-x86 input, location, files, and shell commands."""

    def __init__(self, port: int = 5555, log: Callable[[str], None] | None = None) -> None:
        self.port = port
        self._log = log or (lambda _msg: None)
        self._adb = find_adb()

    @property
    def serial(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def available(self) -> bool:
        return bool(self._adb)

    def connect(self) -> bool:
        if not self._adb:
            self._log("ADB not found. Run setup or install Android platform-tools.")
            return False
        result = subprocess.run(
            [self._adb, "connect", self.serial],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        self._log(output or "ADB connect issued.")
        return result.returncode == 0

    def wait_for_device(self, timeout_sec: float = 45) -> bool:
        if not self._adb:
            return False
        self.connect()
        try:
            result = subprocess.run(
                [self._adb, "-s", self.serial, "wait-for-device"],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def device_state(self) -> str:
        if not self._adb:
            return ""
        result = subprocess.run(
            [self._adb, "-s", self.serial, "get-state"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (result.stdout + result.stderr).strip().lower()

    def shell(self, command: str) -> bool:
        if not self._adb:
            return False
        result = subprocess.run(
            [self._adb, "-s", self.serial, "shell", command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            self._log(result.stderr.strip() or "ADB shell command failed.")
            return False
        return True

    def shell_output(self, command: str) -> str:
        if not self._adb:
            return ""
        result = subprocess.run(
            [self._adb, "-s", self.serial, "shell", command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (result.stdout + result.stderr).strip()

    def setprop(self, key: str, value: str) -> bool:
        escaped = value.replace("'", r"\'")
        return self.shell(f"setprop {key} '{escaped}'")

    def keyevent(self, code: int) -> bool:
        return self.shell(f"input keyevent {code}")

    def tap(self, x: int, y: int) -> bool:
        return self.shell(f"input tap {x} {y}")

    def set_mock_location(self, latitude: float, longitude: float) -> bool:
        """Set GPS coordinates inside the guest (Android 7+ cmd location)."""
        self.shell("settings put secure mock_location 1")
        self.shell("settings put secure location_mode 3")
        ok = self.shell(f"cmd location set-location {latitude} {longitude}")
        if ok:
            self._log(f"Location set to {latitude:.6f}, {longitude:.6f}")
            return True
        # Fallback for older Android-x86 builds
        ok = self.shell(
            f"am broadcast -a android.location.GPS_ENABLED_CHANGE "
            f"--ef latitude {latitude} --ef longitude {longitude}"
        )
        if ok:
            self._log(f"Location broadcast sent ({latitude:.6f}, {longitude:.6f})")
        else:
            self._log(
                "Could not set location. Enable Developer options → Allow mock locations in Android."
            )
        return ok

    def push(self, local_path: str | Path, remote_path: str = "/sdcard/Download/") -> bool:
        if not self._adb:
            self._log("ADB not found.")
            return False
        local = Path(local_path)
        if not local.is_file():
            self._log(f"File not found: {local}")
            return False
        remote = remote_path.rstrip("/") + "/" + local.name
        result = subprocess.run(
            [self._adb, "-s", self.serial, "push", str(local), remote],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            self._log(f"Sent {local.name} → {remote}")
            return True
        self._log(output or "ADB push failed.")
        return False

    def pull(self, remote_path: str, local_path: str | Path) -> bool:
        if not self._adb:
            return False
        result = subprocess.run(
            [self._adb, "-s", self.serial, "pull", remote_path, str(local_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            self._log(f"Pulled {remote_path} → {local_path}")
            return True
        self._log(output or "ADB pull failed.")
        return False

    def install_apk(self, apk_path: str | Path) -> tuple[bool, str]:
        if not self._adb:
            return False, "ADB not found. Run Get Started setup or install Android platform-tools."
        result = subprocess.run(
            [self._adb, "-s", self.serial, "install", "-r", str(apk_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "Success" in output:
            self._log(f"Installed {Path(apk_path).name}")
            return True, ""
        message = output or "ADB install failed."
        self._log(message)
        return False, message

    def uninstall(self, package: str) -> bool:
        if not self._adb:
            return False
        result = subprocess.run(
            [self._adb, "-s", self.serial, "uninstall", package],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "Success" in output:
            self._log(f"Uninstalled {package}")
            return True
        self._log(output or "ADB uninstall failed.")
        return False

    def back(self) -> bool:
        return self.keyevent(4)

    def home(self) -> bool:
        return self.keyevent(3)

    def recent_apps(self) -> bool:
        return self.keyevent(187)

    def power(self) -> bool:
        return self.keyevent(26)
