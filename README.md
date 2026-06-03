# PhoneClone

BlueStacks-style Android app player for Windows.

PhoneClone lets you **install APKs and play Android apps on PC** with a one-click setup — no ISO files, no virtual machine configuration, and no manual Android installation.

## How it works

1. Launch **PhoneClone.exe**
2. Click **Get Started** (one-time download of the emulator engine + ready-to-play Android)
3. Android starts automatically
4. Install apps via **Install APK** or drag-and-drop onto the Home screen
5. Open installed apps from **My Apps**

Everything is stored in `%USERPROFILE%\.phoneclone\`.

## Build

```powershell
.\build.ps1
```

Output: `dist\PhoneClone.exe`

Run from source:

```powershell
pip install -r requirements.txt
python run.py
```

## Features

- BlueStacks-like UI — Home, My Apps, Install APK sidebar
- One-click Android runtime download (pre-installed image, no ISO)
- Auto-start Android on launch
- APK install via button or drag-and-drop
- App launcher for installed apps
- Hardware acceleration (WHPX) and GPU tuning in Settings

## ADB

Setup downloads **platform-tools** (`adb`) into `%USERPROFILE%\.phoneclone\platform-tools\`. APK install and navigation buttons use that copy automatically. You can also use a system-wide install on your PATH.

## Settings

- RAM and CPU cores
- GPU adapter (VirtIO GPU recommended)
- Hardware acceleration (WHPX)
- Auto-start on open

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Setup download fails | Check internet; retry **Get Started**. |
| Black screen | Wait 30–60s for Android to boot. |
| APK install fails | Wait until status shows **Android running**; enable ADB in Android. |
| Slow performance | Settings → enable WHPX; increase RAM. |

## License

MIT
