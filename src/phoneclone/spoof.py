from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phoneclone.adb import AdbClient

# Common retail device fingerprints (best-effort via setprop on Android-x86).
DEVICE_PROFILES: dict[str, dict[str, str]] = {
    "pixel_6": {
        "ro.product.model": "Pixel 6",
        "ro.product.manufacturer": "Google",
        "ro.product.brand": "google",
        "ro.product.device": "oriole",
        "ro.product.name": "oriole",
        "ro.build.product": "oriole",
        "ro.hardware": "oriole",
        "ro.kernel.qemu": "0",
        "ro.kernel.android.qemud": "",
        "ro.boot.qemu": "0",
        "ro.boot.hardware": "oriole",
        "ro.secure": "1",
        "ro.debuggable": "0",
    },
    "samsung_s21": {
        "ro.product.model": "SM-G991B",
        "ro.product.manufacturer": "samsung",
        "ro.product.brand": "samsung",
        "ro.product.device": "o1s",
        "ro.product.name": "o1sxeea",
        "ro.build.product": "o1s",
        "ro.hardware": "exynos2100",
        "ro.kernel.qemu": "0",
        "ro.kernel.android.qemud": "",
        "ro.boot.qemu": "0",
        "ro.boot.hardware": "exynos2100",
        "ro.secure": "1",
        "ro.debuggable": "0",
    },
}


def apply_privacy_profile(adb: AdbClient, profile_key: str, log) -> int:
    """Apply device fingerprint overrides and hide common emulator signals."""
    profile = DEVICE_PROFILES.get(profile_key, DEVICE_PROFILES["pixel_6"])
    applied = 0

    for prop, value in profile.items():
        if adb.setprop(prop, value):
            applied += 1

    extras = [
        ("settings", "put", "global", "device_name", profile["ro.product.model"]),
        ("settings", "put", "secure", "android_id", _pseudo_android_id(profile_key)),
        ("settings", "put", "global", "adb_enabled", "0"),
    ]
    for parts in extras:
        if adb.shell(" ".join(parts)):
            applied += 1

    log(
        f"Privacy profile '{profile_key}' applied ({applied} changes). "
        "Some apps may still detect x86/QEMU; use a hardened Android-x86 image for best results."
    )
    return applied


def _pseudo_android_id(profile_key: str) -> str:
    seed = sum(ord(c) for c in profile_key) % 0xFFFFFFFF
    return f"{seed:016x}"
