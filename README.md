# PhoneClone

Windows desktop Android emulator powered by **QEMU** and **Android-x86**.

PhoneClone is a native `.exe` GUI that boots Android-x86 disk images inside QEMU, shows the screen over embedded VNC, and forwards touch, mouse, and hardware navigation keys via ADB.

## Quick start

### First launch (recommended)

1. Build or run PhoneClone (see below).
2. On first launch, the **Setup wizard** opens automatically:
   - **Download QEMU** (~100 MB portable build)
   - **Download Android-x86 ISO** (~1.2 GB)
   - **Create a 16 GB disk** and run the **one-time Android installer**
   - **Tune GPU & performance** (WHPX, VirtIO GPU, RAM, CPU)
3. Click **Power** to boot.

All downloaded files live in `%USERPROFILE%\.phoneclone\`.

You can rerun setup anytime via toolbar **Setup wizard**.

### Build the executable

```powershell
.\build.ps1
```

Output: `dist\PhoneClone.exe`

You can also run from source:

```powershell
pip install -r requirements.txt
python run.py
```

### Manual setup (alternative)

If you prefer manual installation instead of the wizard:

### Install QEMU

Download QEMU for Windows and note the path to `qemu-system-x86_64.exe`:

- [https://qemu.weilnetz.de/w64/](https://qemu.weilnetz.de/w64/)
- Or via Scoop: `scoop install qemu`

### Create an Android-x86 disk image

1. Download an **Android-x86** ISO from [android-x86.org](https://www.android-x86.org/download).
2. Create a raw disk image (example, 16 GB):

   ```powershell
   qemu-img create -f raw android.img 16G
   ```

3. Boot the ISO once to install Android onto the disk:

   ```powershell
   qemu-system-x86_64 -m 2048 -cdrom android-x86.iso -drive file=android.img,format=raw -boot d
   ```

4. In PhoneClone **Settings**, set:
   - **QEMU executable** → path to `qemu-system-x86_64.exe`
   - **Android disk image** → path to `android.img`

### Optional: ADB (navigation buttons)

Install [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) and add `adb` to your PATH. PhoneClone uses ADB for Back, Home, Recents, and Power key events.

Enable **Settings → Debugging → Android Debug Bridge** inside Android-x86 on first boot.

### Location, instances, privacy, and files

| Feature | How to use |
|---------|------------|
| **Location** | Toolbar **Location** → type an address → **Look up address**. Enable mock locations in Android Developer options. |
| **Fresh instances** | Set a clean **Clone template image** in Settings → **Instances** → **New fresh instance**. |
| **Privacy** | Enabled by default in Settings. Use **Apply privacy** after boot for manual refresh. |
| **Send files** | **Send file** toolbar button, or drag files onto the emulator screen. |

## Features

- Single-file Windows `.exe` build
- **First-run setup wizard** with automatic QEMU & Android-x86 downloads
- **GPU tuning** — VirtIO GPU, QXL, or VirtIO VGA; CPU host/max/auto; WHPX + power hints
- QEMU backend with WHPX acceleration when available
- Embedded VNC display with mouse/touch forwarding
- ADB hardware key support
- **GPS location** — enter any address; coordinates are applied via ADB
- **Clone fresh instances** — copy a golden template into independent phone disks
- **Privacy mode** — neutral QEMU fingerprint and retail device profiles via ADB
- **File transfer** — send files from PC via toolbar or drag-and-drop onto the screen (APKs auto-install)
- Configurable RAM, CPU cores, ports, and extra QEMU arguments
- Settings stored in `%USERPROFILE%\.phoneclone\config.json`

## Requirements

- Windows 10/11 (64-bit)
- QEMU (`qemu-system-x86_64`)
- Android-x86 raw disk image (`.img`)
- Python 3.10+ (only for building from source)

## Project layout

```
phoneclone/
  src/phoneclone/   # Application source
  run.py            # Dev entry point
  build.ps1         # Build script
  phoneclone.spec   # PyInstaller spec
  dist/             # Built executable (after build)
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "QEMU path is not set" | Open **Settings** and browse to `qemu-system-x86_64.exe`. |
| Black screen after power on | Wait 30–60s for Android to boot; check the log panel. |
| VNC connection failed | Ensure nothing else uses port 5900; change VNC port in Settings. |
| Nav buttons do nothing | Install ADB, enable USB debugging in Android-x86, wait for boot. |
| Slow performance | Run **Setup wizard** performance step; enable WHPX; use VirtIO GPU; set CPU to Host; add RAM. |
| WHPX unavailable | Enable **Windows Hypervisor Platform** in Windows Features, then reboot. |

## License

MIT
