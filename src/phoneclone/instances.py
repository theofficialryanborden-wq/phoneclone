from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from phoneclone.config import EmulatorConfig


@dataclass
class InstanceResources:
    """QEMU performance settings stored per phone instance."""

    ram_mb: int = 2048
    cpu_cores: int = 2
    gpu_mode: str = "virtio_gpu"
    cpu_mode: str = "auto"
    video_memory_mb: int = 128
    enable_cpu_pm: bool = True

    @classmethod
    def from_config(cls, config: EmulatorConfig) -> InstanceResources:
        return cls(
            ram_mb=config.ram_mb,
            cpu_cores=config.cpu_cores,
            gpu_mode=config.gpu_mode,
            cpu_mode=config.cpu_mode,
            video_memory_mb=config.video_memory_mb,
            enable_cpu_pm=config.enable_cpu_pm,
        )

    def apply_to(self, config: EmulatorConfig) -> None:
        config.ram_mb = self.ram_mb
        config.cpu_cores = self.cpu_cores
        config.gpu_mode = self.gpu_mode
        config.cpu_mode = self.cpu_mode
        config.video_memory_mb = self.video_memory_mb
        config.enable_cpu_pm = self.enable_cpu_pm


@dataclass
class InstanceInfo:
    id: str
    name: str
    disk_path: str
    created_at: str
    ram_mb: int = 2048
    cpu_cores: int = 2
    gpu_mode: str = "virtio_gpu"
    cpu_mode: str = "auto"
    video_memory_mb: int = 128
    enable_cpu_pm: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> InstanceInfo:
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @property
    def resources(self) -> InstanceResources:
        return InstanceResources(
            ram_mb=self.ram_mb,
            cpu_cores=self.cpu_cores,
            gpu_mode=self.gpu_mode,
            cpu_mode=self.cpu_mode,
            video_memory_mb=self.video_memory_mb,
            enable_cpu_pm=self.enable_cpu_pm,
        )

    def apply_to_config(self, config: EmulatorConfig) -> None:
        config.system_image = self.disk_path
        self.resources.apply_to(config)


class InstanceManager:
    """Manage cloned Android-x86 disk instances under ~/.phoneclone/instances."""

    def __init__(self) -> None:
        self.root = Path.home() / ".phoneclone"
        self.instances_dir = self.root / "instances"
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "instances.json"

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"active_id": "", "instances": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, data: dict) -> None:
        self.index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_instances(self) -> list[InstanceInfo]:
        data = self._load_index()
        return [InstanceInfo.from_dict(item) for item in data.get("instances", [])]

    def get_active_id(self) -> str:
        return self._load_index().get("active_id", "")

    def get_active(self) -> InstanceInfo | None:
        active_id = self.get_active_id()
        if not active_id:
            return None
        for instance in self.list_instances():
            if instance.id == active_id:
                return instance
        return None

    def set_active(self, instance_id: str) -> InstanceInfo | None:
        data = self._load_index()
        target = None
        for item in data.get("instances", []):
            if item["id"] == instance_id:
                target = InstanceInfo.from_dict(item)
                break
        if not target:
            return None
        data["active_id"] = instance_id
        self._save_index(data)
        return target

    def create_fresh(
        self,
        template_image: str,
        name: str,
        *,
        qemu_img: str = "",
        copy_on_write: bool = False,
        resources: InstanceResources | None = None,
    ) -> InstanceInfo:
        """Create a new instance disk from a template (golden) image."""
        template = Path(template_image)
        if not template.is_file():
            raise FileNotFoundError(f"Template image not found: {template}")

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip()) or "instance"
        instance_id = uuid.uuid4().hex[:10]
        folder = self.instances_dir / f"{safe_name}_{instance_id}"
        folder.mkdir(parents=True, exist_ok=False)

        if copy_on_write and qemu_img:
            disk_path = folder / "disk.qcow2"
            self._create_cow_clone(qemu_img, template, disk_path)
        else:
            suffix = template.suffix or ".img"
            disk_path = folder / f"disk{suffix}"
            shutil.copy2(template, disk_path)

        res = resources or InstanceResources()
        info = InstanceInfo(
            id=instance_id,
            name=name.strip() or safe_name,
            disk_path=str(disk_path),
            created_at=datetime.now(timezone.utc).isoformat(),
            ram_mb=res.ram_mb,
            cpu_cores=res.cpu_cores,
            gpu_mode=res.gpu_mode,
            cpu_mode=res.cpu_mode,
            video_memory_mb=res.video_memory_mb,
            enable_cpu_pm=res.enable_cpu_pm,
        )
        data = self._load_index()
        data.setdefault("instances", []).append(asdict(info))
        data["active_id"] = instance_id
        self._save_index(data)
        return info

    def delete_instance(self, instance_id: str) -> bool:
        data = self._load_index()
        instances = data.get("instances", [])
        removed = None
        kept = []
        for item in instances:
            if item["id"] == instance_id:
                removed = InstanceInfo.from_dict(item)
            else:
                kept.append(item)
        if not removed:
            return False

        data["instances"] = kept
        if data.get("active_id") == instance_id:
            data["active_id"] = kept[-1]["id"] if kept else ""

        folder = Path(removed.disk_path).parent
        if folder.is_dir() and folder.parent == self.instances_dir:
            shutil.rmtree(folder, ignore_errors=True)
        elif Path(removed.disk_path).is_file():
            Path(removed.disk_path).unlink(missing_ok=True)

        self._save_index(data)
        return True

    @staticmethod
    def _create_cow_clone(qemu_img: str, backing: Path, output: Path) -> None:
        fmt = "qcow2" if backing.suffix.lower() == ".qcow2" else "raw"
        cmd = [
            qemu_img,
            "create",
            "-f",
            "qcow2",
            "-F",
            fmt,
            "-b",
            str(backing),
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "qemu-img create failed.")

    @staticmethod
    def resolve_qemu_img(qemu_path: str) -> str:
        if not qemu_path:
            return ""
        qemu_dir = Path(qemu_path).parent
        for name in ("qemu-img.exe", "qemu-img"):
            candidate = qemu_dir / name
            if candidate.is_file():
                return str(candidate)
        return shutil.which("qemu-img") or ""
