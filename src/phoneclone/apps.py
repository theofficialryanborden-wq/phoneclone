from __future__ import annotations

from phoneclone.adb import AdbClient


class AppManager:
    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb

    def list_user_apps(self) -> list[tuple[str, str]]:
        """Return (label, package) pairs for user-installed apps."""
        if not self._adb.available:
            return []
        raw = self._adb.shell_output("pm list packages -3")
        apps: list[tuple[str, str]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            package = line.split(":", 1)[1]
            label = _friendly_name(package)
            apps.append((label, package))
        apps.sort(key=lambda item: item[0].lower())
        return apps

    def launch(self, package: str) -> bool:
        return self._adb.shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        )

    def uninstall(self, package: str) -> bool:
        return self._adb.uninstall(package)


def _friendly_name(package: str) -> str:
    tail = package.rsplit(".", 1)[-1]
    return tail.replace("_", " ").title()
