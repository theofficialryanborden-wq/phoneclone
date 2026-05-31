from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable


class AdbClient:
    """Minimal ADB wrapper for Android-x86 input, location, files, and shell commands."""

    def __init__(self, port: int = 5555, log: Callable[[str], None] | None = None) -> None:
        self.port = port
        self._log = log or (lambda _msg: None)
        self._adb = shutil.which("adb")

    @property
    def serial(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def available(self) -> bool:
        return self._adb is not None

    def connect(self) -> bool:
        if not self._adb:
            self._log("ADB not found in PATH. Install Android platform-tools to use nav buttons.")
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
            self._log("ADB not found in PATH.")
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

    def install_apk(self, apk_path: str | Path) -> bool:
        if not self._adb:
            return False
        result = subprocess.run(
            [self._adb, "-s", self.serial, "install", "-r", str(apk_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "Success" in output:
            self._log(f"Installed {Path(apk_path).name}")
            return True
        self._log(output or "ADB install failed.")
        return False

    def back(self) -> bool:
        return self.keyevent(4)

    def home(self) -> bool:
        return self.keyevent(3)

    def recent_apps(self) -> bool:
        return self.keyevent(187)

    def power(self) -> bool:
        return self.keyevent(26)
