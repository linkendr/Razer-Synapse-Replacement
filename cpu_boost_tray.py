#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
import ctypes
import json
import re
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import clr  # type: ignore
import psutil

import razer_fan_control as rfc


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "cpu-boost-tray-config.json"
CRASH_LOG_PATH = PROJECT_DIR / "cpu-boost-tray-crash.log"
MUTEX_NAME = r"Global\RazerCpuBoostTray"
ERROR_ALREADY_EXISTS = 183


clr.AddReference("System.Drawing")
clr.AddReference("System")
clr.AddReference("System.Windows.Forms")

from System import IntPtr  # type: ignore
from System.Diagnostics import PerformanceCounter, PerformanceCounterCategory  # type: ignore
from System.Drawing import (  # type: ignore
    Bitmap,
    Color,
    Font,
    FontFamily,
    FontStyle,
    Graphics,
    GraphicsUnit,
    Icon,
    Pen,
    PointF,
    RectangleF,
    SolidBrush,
    StringAlignment,
    StringFormat,
)
from System.Drawing.Drawing2D import GraphicsPath, SmoothingMode  # type: ignore
from System.Windows.Forms import (  # type: ignore
    Application,
    ApplicationContext,
    ContextMenuStrip,
    MethodInvoker,
    MouseButtons,
    NotifyIcon,
    ToolStripMenuItem,
)


class CpuBoostTrayError(RuntimeError):
    pass


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_uint32),
        ("BatteryFullLifeTime", ctypes.c_uint32),
    ]


class SingleInstanceGuard:
    def __init__(self, name: str) -> None:
        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise CpuBoostTrayError("failed to create tray mutex")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            raise CpuBoostTrayError("CPU boost tray is already running")

    def close(self) -> None:
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


class FileLogger:
    def __init__(self, path: Path, verbose: bool) -> None:
        self.path = path
        self.verbose = verbose
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if self.verbose:
            print(line)


class GpuTelemetryReader:
    _LUID_PATTERN = re.compile(r"(luid_0x[0-9a-f]+_0x[0-9a-f]+_phys_\d+)", re.IGNORECASE)

    def __init__(self, logger: FileLogger) -> None:
        self.logger = logger
        self._creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.adapter_luid: str | None = None
        self.engine_counters: list[PerformanceCounter] = []
        self.memory_counter: PerformanceCounter | None = None
        self.memory_instance_name: str | None = None

    def _dispose_counter(self, counter: PerformanceCounter | None) -> None:
        if counter is None:
            return
        try:
            counter.Close()
        except Exception:
            pass
        try:
            counter.Dispose()
        except Exception:
            pass

    def _dispose_engine_counters(self) -> None:
        for counter in self.engine_counters:
            self._dispose_counter(counter)
        self.engine_counters = []

    def _nvidia_memory_used_mb(self) -> float:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=self._creationflags,
        )
        first_line = completed.stdout.strip().splitlines()[0]
        return float(first_line.strip())

    def _extract_luid(self, path: str) -> str:
        match = self._LUID_PATTERN.search(path)
        if not match:
            raise CpuBoostTrayError(f"failed to extract GPU adapter LUID from {path!r}")
        return match.group(1).lower()

    def _memory_instances(self) -> list[tuple[str, float]]:
        category = PerformanceCounterCategory("GPU Adapter Memory")
        rows: list[tuple[str, float]] = []
        for instance_name in category.GetInstanceNames():
            counter = PerformanceCounter("GPU Adapter Memory", "Dedicated Usage", instance_name, True)
            try:
                rows.append((str(instance_name), float(counter.NextValue())))
            finally:
                self._dispose_counter(counter)
        return rows

    def _refresh_engine_counters(self) -> None:
        if self.adapter_luid is None:
            raise CpuBoostTrayError("GPU adapter LUID is not initialized")
        self._dispose_engine_counters()
        engine_category = PerformanceCounterCategory("GPU Engine")
        counters = [
            PerformanceCounter("GPU Engine", "Utilization Percentage", instance_name, True)
            for instance_name in engine_category.GetInstanceNames()
            if self.adapter_luid in str(instance_name).lower() and "engtype_3d" in str(instance_name).lower()
        ]
        for counter in counters:
            try:
                counter.NextValue()
            except Exception:
                continue
        self.engine_counters = counters

    def discover_adapter(self) -> str:
        rows = self._memory_instances()
        try:
            nvidia_used_mb = self._nvidia_memory_used_mb()
        except Exception as exc:
            self.logger.log(f"nvidia-smi memory query failed, falling back to adapter counters: {exc}")
            nvidia_used_mb = None
        best_luid = None
        best_score = None
        best_instance = None
        for instance_name, cooked_value in rows:
            dedicated_mb = cooked_value / (1024.0 * 1024.0)
            luid = self._extract_luid(instance_name)
            if nvidia_used_mb is None:
                score = -dedicated_mb
            else:
                score = abs(dedicated_mb - nvidia_used_mb)
            if best_score is None or score < best_score:
                best_score = score
                best_luid = luid
                best_instance = instance_name

        if best_luid is None or best_instance is None:
            raise CpuBoostTrayError("failed to identify NVIDIA GPU adapter counter")

        self.adapter_luid = best_luid
        self.memory_instance_name = best_instance
        self._dispose_counter(self.memory_counter)
        self.memory_counter = PerformanceCounter("GPU Adapter Memory", "Dedicated Usage", best_instance, True)
        self._refresh_engine_counters()
        self.logger.log(f"GPU telemetry attached to adapter {best_luid}.")
        return best_luid

    def sample(self) -> tuple[float, float]:
        if self.adapter_luid is None:
            self.discover_adapter()

        if self.memory_counter is None:
            raise CpuBoostTrayError("GPU memory counter is not initialized")

        try:
            if not self.engine_counters:
                self._refresh_engine_counters()
            gpu_3d_percent = sum(float(counter.NextValue()) for counter in self.engine_counters)
        except Exception:
            self._refresh_engine_counters()
            gpu_3d_percent = sum(float(counter.NextValue()) for counter in self.engine_counters)

        try:
            gpu_vram_mb = float(self.memory_counter.NextValue()) / (1024.0 * 1024.0)
        except Exception:
            if self.memory_instance_name is None:
                raise
            self._dispose_counter(self.memory_counter)
            self.memory_counter = PerformanceCounter("GPU Adapter Memory", "Dedicated Usage", self.memory_instance_name, True)
            gpu_vram_mb = float(self.memory_counter.NextValue()) / (1024.0 * 1024.0)
        return min(100.0, gpu_3d_percent), gpu_vram_mb

    def close(self) -> None:
        self._dispose_engine_counters()
        self._dispose_counter(self.memory_counter)
        self.memory_counter = None


@dataclass
class TrayConfig:
    vendor_id: int
    product_id: int
    control_mode: str
    refresh_interval_seconds: float
    state_sync_interval_seconds: float
    log_interval_seconds: float
    require_ac_power: bool
    disable_on_battery_saver: bool
    gpu_balanced_mode: int
    gpu_high_mode: int
    fast_on_gpu_3d_percent: float
    fast_on_window_seconds: float
    on_gpu_3d_percent: float
    on_gpu_3d_window_seconds: float
    on_gpu_3d_with_vram_percent: float
    on_gpu_vram_mb: float
    on_gpu_vram_window_seconds: float
    on_cpu_average_percent: float
    on_cpu_window_seconds: float
    off_gpu_3d_percent: float
    off_cpu_average_percent: float
    off_gpu_3d_with_vram_percent: float
    off_gpu_vram_mb: float
    off_window_seconds: float
    min_on_seconds: float
    min_off_seconds: float
    log_path: Path
    path: Path

    @classmethod
    def load(cls, path: Path) -> "TrayConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        log_path = Path(str(data.get("log_path", "cpu-boost-tray.log")))
        if not log_path.is_absolute():
            log_path = path.parent / log_path
        return cls(
            vendor_id=int(data.get("vendor_id", rfc.RAZER_VENDOR_ID)),
            product_id=int(data.get("product_id", rfc.DEFAULT_PRODUCT_ID)),
            control_mode=str(data.get("control_mode", "auto")).lower(),
            refresh_interval_seconds=float(data.get("refresh_interval_seconds", 5.0)),
            state_sync_interval_seconds=float(data.get("state_sync_interval_seconds", 60.0)),
            log_interval_seconds=float(data.get("log_interval_seconds", 30.0)),
            require_ac_power=bool(data.get("require_ac_power", True)),
            disable_on_battery_saver=bool(data.get("disable_on_battery_saver", True)),
            gpu_balanced_mode=int(data.get("gpu_balanced_mode", 1)),
            gpu_high_mode=int(data.get("gpu_high_mode", 2)),
            fast_on_gpu_3d_percent=float(data.get("fast_on_gpu_3d_percent", 85.0)),
            fast_on_window_seconds=float(data.get("fast_on_window_seconds", 5.0)),
            on_gpu_3d_percent=float(data.get("on_gpu_3d_percent", 55.0)),
            on_gpu_3d_window_seconds=float(data.get("on_gpu_3d_window_seconds", 15.0)),
            on_gpu_3d_with_vram_percent=float(data.get("on_gpu_3d_with_vram_percent", 35.0)),
            on_gpu_vram_mb=float(data.get("on_gpu_vram_mb", 1536.0)),
            on_gpu_vram_window_seconds=float(data.get("on_gpu_vram_window_seconds", 15.0)),
            on_cpu_average_percent=float(data.get("on_cpu_average_percent", 80.0)),
            on_cpu_window_seconds=float(data.get("on_cpu_window_seconds", 20.0)),
            off_gpu_3d_percent=float(data.get("off_gpu_3d_percent", 15.0)),
            off_cpu_average_percent=float(data.get("off_cpu_average_percent", 35.0)),
            off_gpu_3d_with_vram_percent=float(data.get("off_gpu_3d_with_vram_percent", 25.0)),
            off_gpu_vram_mb=float(data.get("off_gpu_vram_mb", 700.0)),
            off_window_seconds=float(data.get("off_window_seconds", 60.0)),
            min_on_seconds=float(data.get("min_on_seconds", 180.0)),
            min_off_seconds=float(data.get("min_off_seconds", 45.0)),
            log_path=log_path,
            path=path,
        )

    def save(self) -> None:
        payload = {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "control_mode": self.control_mode,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "state_sync_interval_seconds": self.state_sync_interval_seconds,
            "log_interval_seconds": self.log_interval_seconds,
            "require_ac_power": self.require_ac_power,
            "disable_on_battery_saver": self.disable_on_battery_saver,
            "gpu_balanced_mode": self.gpu_balanced_mode,
            "gpu_high_mode": self.gpu_high_mode,
            "fast_on_gpu_3d_percent": self.fast_on_gpu_3d_percent,
            "fast_on_window_seconds": self.fast_on_window_seconds,
            "on_gpu_3d_percent": self.on_gpu_3d_percent,
            "on_gpu_3d_window_seconds": self.on_gpu_3d_window_seconds,
            "on_gpu_3d_with_vram_percent": self.on_gpu_3d_with_vram_percent,
            "on_gpu_vram_mb": self.on_gpu_vram_mb,
            "on_gpu_vram_window_seconds": self.on_gpu_vram_window_seconds,
            "on_cpu_average_percent": self.on_cpu_average_percent,
            "on_cpu_window_seconds": self.on_cpu_window_seconds,
            "off_gpu_3d_percent": self.off_gpu_3d_percent,
            "off_cpu_average_percent": self.off_cpu_average_percent,
            "off_gpu_3d_with_vram_percent": self.off_gpu_3d_with_vram_percent,
            "off_gpu_vram_mb": self.off_gpu_vram_mb,
            "off_window_seconds": self.off_window_seconds,
            "min_on_seconds": self.min_on_seconds,
            "min_off_seconds": self.min_off_seconds,
            "log_path": str(self.log_path if self.log_path.is_absolute() else self.log_path.name),
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@dataclass
class TelemetrySample:
    timestamp: float
    cpu_average_percent: float
    cpu_max_percent: float
    gpu_3d_percent: float
    gpu_vram_mb: float
    ac_connected: bool
    battery_saver: bool


@dataclass
class AppState:
    config: TrayConfig
    logger: FileLogger
    current_cpu_boost: int | None = None
    current_gpu_boost: int | None = None
    last_error: str | None = None
    last_cpu_utilizations: list[float] | None = None
    last_gpu_3d_percent: float | None = None
    last_gpu_vram_mb: float | None = None
    ac_connected: bool | None = None
    battery_saver: bool | None = None
    battery_percent: int | None = None
    last_mode_change_monotonic: float = 0.0
    last_state_sync_monotonic: float = 0.0

    @property
    def control_mode(self) -> str:
        return self.config.control_mode

    def set_control_mode(self, mode: str) -> None:
        self.config.control_mode = mode
        self.config.save()
        self.logger.log(f"Set tray control mode to {mode}.")


class CpuBoostTrayApp:
    def __init__(self, state: AppState) -> None:
        self.state = state
        if self.state.last_mode_change_monotonic <= 0.0:
            self.state.last_mode_change_monotonic = time.monotonic()
        self.state_lock = threading.RLock()
        self.io_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._worker_loop, name="CpuBoostTrayWorker", daemon=True)
        self.context = ApplicationContext()
        self.notify_icon = NotifyIcon()
        self.notify_icon.Visible = False
        self.notify_icon.Text = "CPU Boost"

        self.menu = ContextMenuStrip()
        self.status_item = ToolStripMenuItem("CPU:Unknown")
        self.status_item.Enabled = False
        self.mode_item = ToolStripMenuItem("GPU: Unknown")
        self.mode_item.Enabled = False
        self.power_item = ToolStripMenuItem("Power: Unknown")
        self.power_item.Enabled = False
        self.manual_on_item = ToolStripMenuItem("Manual Boost ON")
        self.manual_off_item = ToolStripMenuItem("Manual Boost OFF")
        self.auto_item = ToolStripMenuItem("Auto Mode")
        self.exit_item = ToolStripMenuItem("Exit")

        self.menu.Items.Add(self.status_item)
        self.menu.Items.Add(self.mode_item)
        self.menu.Items.Add(self.power_item)
        self.menu.Items.Add(self.manual_on_item)
        self.menu.Items.Add(self.manual_off_item)
        self.menu.Items.Add(self.auto_item)
        self.menu.Items.Add("-")
        self.menu.Items.Add(self.exit_item)
        self.notify_icon.ContextMenuStrip = self.menu

        self.manual_on_item.Click += self.on_manual_on
        self.manual_off_item.Click += self.on_manual_off
        self.auto_item.Click += self.on_auto_mode
        self.exit_item.Click += self.on_exit
        self.notify_icon.MouseClick += self.on_mouse_click

        self._icon_handles: list[int] = []
        self._icon_cache: dict[tuple[bool, bool], Icon] = {}
        self._last_icon_signature: tuple[object, ...] | None = None
        self._last_menu_signature: tuple[object, ...] | None = None
        self._last_error_signature: str | None = None
        self._last_error_log_monotonic = 0.0
        self._mixed_state_since_monotonic: float | None = None
        self.telemetry_reader = GpuTelemetryReader(self.state.logger)
        self.history: deque[TelemetrySample] = deque()
        psutil.cpu_percent(interval=None, percpu=True)

    def cleanup_icons(self) -> None:
        for handle in self._icon_handles:
            ctypes.windll.user32.DestroyIcon(handle)
        self._icon_handles.clear()

    def icon_text(self) -> str:
        return "AUTO" if self.state.control_mode == "auto" else "CPU"

    def add_rounded_rectangle(self, path: GraphicsPath, x: float, y: float, width: float, height: float, radius: float) -> None:
        diameter = radius * 2.0
        path.AddArc(x, y, diameter, diameter, 180.0, 90.0)
        path.AddArc(x + width - diameter, y, diameter, diameter, 270.0, 90.0)
        path.AddArc(x + width - diameter, y + height - diameter, diameter, diameter, 0.0, 90.0)
        path.AddArc(x, y + height - diameter, diameter, diameter, 90.0, 90.0)
        path.CloseFigure()

    def add_lightning_bolt(self, path: GraphicsPath, x: float, y: float, width: float, height: float) -> None:
        path.StartFigure()
        path.AddLine(PointF(x + width * 0.55, y), PointF(x + width * 0.15, y + height * 0.52))
        path.AddLine(PointF(x + width * 0.15, y + height * 0.52), PointF(x + width * 0.40, y + height * 0.52))
        path.AddLine(PointF(x + width * 0.40, y + height * 0.52), PointF(x + width * 0.28, y + height))
        path.AddLine(PointF(x + width * 0.28, y + height), PointF(x + width * 0.85, y + height * 0.35))
        path.AddLine(PointF(x + width * 0.85, y + height * 0.35), PointF(x + width * 0.58, y + height * 0.35))
        path.CloseFigure()

    def draw_auto_badge(self, graphics: Graphics, size: int) -> None:
        badge_path = GraphicsPath()
        self.add_rounded_rectangle(badge_path, 10.0, 41.0, float(size - 20), 16.0, 6.0)
        graphics.FillPath(SolidBrush(Color.FromArgb(232, 248, 236)), badge_path)

        font = Font(FontFamily.GenericSansSerif, 10.0, FontStyle.Bold, GraphicsUnit.Pixel)
        fmt = StringFormat()
        fmt.Alignment = StringAlignment.Center
        fmt.LineAlignment = StringAlignment.Center
        graphics.DrawString("AUTO", font, SolidBrush(Color.FromArgb(18, 92, 44)), RectangleF(10.0, 41.0, float(size - 20), 16.0), fmt)

    def _build_icon(self, enabled: bool, is_auto: bool) -> Icon:
        size = 64
        bitmap = Bitmap(size, size)
        graphics = Graphics.FromImage(bitmap)
        graphics.Clear(Color.Transparent)
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        circle_color = Color.FromArgb(24, 160, 72) if enabled or is_auto else Color.FromArgb(178, 42, 42)
        graphics.FillEllipse(SolidBrush(circle_color), RectangleF(4.0, 4.0, float(size - 8), float(size - 8)))

        bolt_path = GraphicsPath()
        self.add_lightning_bolt(bolt_path, 18.0, 12.0, 28.0, 36.0)
        if enabled or is_auto:
            graphics.FillPath(SolidBrush(Color.White), bolt_path)
        else:
            graphics.DrawPath(Pen(Color.White, 4.0), bolt_path)

        if is_auto:
            self.draw_auto_badge(graphics, size)

        graphics.Flush()

        hicon = bitmap.GetHicon().ToInt64()
        self._icon_handles.append(hicon)
        return Icon.FromHandle(IntPtr(hicon))

    def create_icon(self, enabled: bool, is_auto: bool) -> Icon:
        key = (enabled, is_auto)
        icon = self._icon_cache.get(key)
        if icon is None:
            icon = self._build_icon(enabled, is_auto)
            self._icon_cache[key] = icon
        return icon

    def cpu_boost_label(self) -> str:
        with self.state_lock:
            return self._cpu_boost_label_for(self.state.current_cpu_boost)

    def _cpu_boost_label_for(self, value: int | None) -> str:
        if value is None:
            return "Unknown"
        if value == 0:
            return "Normal"
        if value == 1:
            return "BOOST"
        return f"Raw {value}"

    def gpu_mode_label(self) -> str:
        with self.state_lock:
            return self._gpu_mode_label_for(self.state.current_gpu_boost)

    def _gpu_mode_label_for(self, value: int | None) -> str:
        if value is None:
            return "Unknown"
        if value == self.state.config.gpu_high_mode:
            return "High"
        if value in (0, self.state.config.gpu_balanced_mode):
            return "Normal"
        return f"Raw {value}"

    def performance_enabled(self) -> bool:
        with self.state_lock:
            return self._performance_enabled_unlocked()

    def balanced_state_active(self) -> bool:
        with self.state_lock:
            return self._balanced_state_active_unlocked()

    def _performance_enabled_unlocked(self) -> bool:
        return (
            self.state.current_cpu_boost not in (None, 0)
            and self.state.current_gpu_boost == self.state.config.gpu_high_mode
        )

    def _balanced_state_active_unlocked(self) -> bool:
        return (
            self.state.current_cpu_boost == 0
            and self.state.current_gpu_boost == self.state.config.gpu_balanced_mode
        )

    def _clear_error(self) -> None:
        with self.state_lock:
            self.state.last_error = None
        self._last_error_signature = None
        self.request_visual_update()

    def _set_error(self, message: str, *, log_prefix: str) -> None:
        with self.state_lock:
            self.state.last_error = message
        now = time.monotonic()
        if (
            self._last_error_signature != message
            or now - self._last_error_log_monotonic >= 60.0
        ):
            self.state.logger.log(f"{log_prefix}: {message}")
            self._last_error_signature = message
            self._last_error_log_monotonic = now
        self.request_visual_update()

    def _append_history(self, sample: TelemetrySample) -> None:
        self.history.append(sample)
        max_window = max(
            self.state.config.min_on_seconds,
            self.state.config.min_off_seconds,
            self.state.config.off_window_seconds,
            self.state.config.on_cpu_window_seconds,
            self.state.config.on_gpu_3d_window_seconds,
            self.state.config.on_gpu_vram_window_seconds,
            self.state.config.fast_on_window_seconds,
        ) + self.state.config.refresh_interval_seconds + 5.0
        cutoff = sample.timestamp - max_window
        while self.history and self.history[0].timestamp < cutoff:
            self.history.popleft()

    def _window_samples(self, now: float, window_seconds: float) -> list[TelemetrySample]:
        return [item for item in self.history if now - item.timestamp <= window_seconds + 1e-6]

    def _window_ready(self, now: float, window_seconds: float) -> bool:
        samples = self._window_samples(now, window_seconds)
        if not samples:
            return False
        return now - samples[0].timestamp >= max(0.0, window_seconds - 1e-6)

    def _window_average(self, now: float, window_seconds: float, field_name: str) -> float | None:
        samples = self._window_samples(now, window_seconds)
        if not samples or not self._window_ready(now, window_seconds):
            return None
        return sum(float(getattr(item, field_name)) for item in samples) / len(samples)

    def _time_in_current_mode(self, now: float) -> float:
        return max(0.0, now - self.state.last_mode_change_monotonic)

    def power_label(self) -> str:
        with self.state_lock:
            return self._power_label_for(self.state.ac_connected, self.state.battery_saver, self.state.battery_percent)

    def _power_label_for(self, ac_connected: bool | None, battery_saver: bool | None, battery_percent: int | None) -> str:
        ac_label = "AC" if ac_connected else "Battery"
        saver_label = "Saver On" if battery_saver else "Saver Off"
        if ac_connected is None or battery_saver is None:
            return "Unknown"
        if battery_percent is None:
            return f"{ac_label} | {saver_label}"
        return f"{ac_label} | {saver_label} | {battery_percent}%"

    def mode_label(self) -> str:
        with self.state_lock:
            return self._mode_label_for(self.state.control_mode, self.state.current_cpu_boost, self.state.current_gpu_boost)

    def _mode_label_for(self, control_mode: str, current_cpu_boost: int | None, current_gpu_boost: int | None) -> str:
        if control_mode == "auto":
            return "AUTO"
        if current_cpu_boost not in (None, 0) and current_gpu_boost == self.state.config.gpu_high_mode:
            return "Manual On"
        if current_cpu_boost == 0 and current_gpu_boost == self.state.config.gpu_balanced_mode:
            return "Manual Off"
        return "Manual"

    def request_visual_update(self) -> None:
        try:
            if self.menu.IsDisposed:
                return
            if self.menu.InvokeRequired:
                self.menu.BeginInvoke(MethodInvoker(self.update_visuals))
            else:
                self.update_visuals()
        except Exception:
            pass

    def update_visuals(self) -> None:
        with self.state_lock:
            enabled = self._performance_enabled_unlocked()
            current_cpu_boost = self.state.current_cpu_boost
            current_gpu_boost = self.state.current_gpu_boost
            control_mode = self.state.control_mode
            last_error = self.state.last_error
            ac_connected = self.state.ac_connected
            battery_saver = self.state.battery_saver
            battery_percent = self.state.battery_percent

        status = f"CPU:{self._cpu_boost_label_for(current_cpu_boost)}"
        gpu_text = f"GPU: {self._gpu_mode_label_for(current_gpu_boost)}"
        power_text = f"Power: {self._power_label_for(ac_connected, battery_saver, battery_percent)}"
        tooltip = f"Boost Mode {'Auto' if control_mode == 'auto' else ('On' if enabled else 'Off')}"
        if last_error:
            tooltip = "Boost Mode Error"
        icon_signature = (enabled, control_mode == "auto", bool(last_error))
        menu_signature = (
            status,
            gpu_text,
            power_text,
            tooltip[:63],
            control_mode == "auto",
        )
        if icon_signature != self._last_icon_signature:
            self.notify_icon.Icon = self.create_icon(enabled, control_mode == "auto")
            self._last_icon_signature = icon_signature
        if menu_signature != self._last_menu_signature:
            self.status_item.Text = status
            self.mode_item.Text = gpu_text
            self.power_item.Text = power_text
            self.notify_icon.Text = tooltip[:63]
            self.auto_item.Checked = control_mode == "auto"
            self._last_menu_signature = menu_signature

    def read_system_power(self) -> tuple[bool, bool, int | None]:
        power_status = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power_status)):
            raise CpuBoostTrayError("GetSystemPowerStatus failed")
        ac_connected = power_status.ACLineStatus == 1
        battery_saver = power_status.SystemStatusFlag == 1
        battery_percent = None if power_status.BatteryLifePercent == 255 else int(power_status.BatteryLifePercent)
        with self.state_lock:
            changed = (
                self.state.ac_connected != ac_connected
                or self.state.battery_saver != battery_saver
                or self.state.battery_percent != battery_percent
            )
            self.state.ac_connected = ac_connected
            self.state.battery_saver = battery_saver
            self.state.battery_percent = battery_percent
        if changed:
            self.request_visual_update()
        return ac_connected, battery_saver, battery_percent

    def sync_performance_modes(self, force_log: bool = False) -> None:
        with self.io_lock:
            cpu_boost, gpu_boost = rfc.query_performance_modes(self.state.config.vendor_id, self.state.config.product_id)
        with self.state_lock:
            changed = (
                self.state.current_cpu_boost != cpu_boost
                or self.state.current_gpu_boost != gpu_boost
            )
            self.state.current_cpu_boost = cpu_boost
            self.state.current_gpu_boost = gpu_boost
            self.state.last_state_sync_monotonic = time.monotonic()
        self._clear_error()
        if changed or force_log:
            self.state.logger.log(f"Synchronized performance modes cpu={cpu_boost} gpu={gpu_boost}.")
        if changed:
            self.request_visual_update()

    def read_gpu_telemetry(self) -> tuple[float, float]:
        gpu_3d_percent, gpu_vram_mb = self.telemetry_reader.sample()
        with self.state_lock:
            self.state.last_gpu_3d_percent = gpu_3d_percent
            self.state.last_gpu_vram_mb = gpu_vram_mb
        return gpu_3d_percent, gpu_vram_mb

    def write_performance_modes(self, *, cpu_boost: int, gpu_boost: int) -> None:
        with self.io_lock:
            cpu_result, gpu_result = rfc.set_performance_modes(
                self.state.config.vendor_id,
                self.state.config.product_id,
                cpu_mode=cpu_boost,
                gpu_mode=gpu_boost,
            )
        if cpu_result != cpu_boost or gpu_result != gpu_boost:
            raise CpuBoostTrayError(
                f"performance mode verify mismatch: requested cpu={cpu_boost} gpu={gpu_boost}, "
                f"got cpu={cpu_result} gpu={gpu_result}"
            )
        with self.state_lock:
            self.state.current_cpu_boost = cpu_result
            self.state.current_gpu_boost = gpu_result
            self.state.last_mode_change_monotonic = time.monotonic()
            self.state.last_state_sync_monotonic = self.state.last_mode_change_monotonic
        self._mixed_state_since_monotonic = None
        self._clear_error()
        self.state.logger.log(f"Set performance modes cpu={cpu_result} gpu={gpu_result}.")
        self.request_visual_update()

    def apply_performance_state(self, enabled: bool) -> None:
        cpu_mode = 1 if enabled else 0
        gpu_mode = self.state.config.gpu_high_mode if enabled else self.state.config.gpu_balanced_mode
        self.write_performance_modes(cpu_boost=cpu_mode, gpu_boost=gpu_mode)

    def manual_set(self, enabled: bool) -> None:
        try:
            self.state.set_control_mode("manual")
            self.apply_performance_state(enabled)
        except Exception as exc:
            self._set_error(str(exc), log_prefix="Manual performance write failed")
        self.refresh_tick()
        self.request_visual_update()

    def set_auto_mode(self) -> None:
        try:
            self.state.set_control_mode("auto")
            self._mixed_state_since_monotonic = None
            self._clear_error()
            self.state.logger.log(
                "Auto mode enabled "
                f"(require_ac={self.state.config.require_ac_power}, "
                f"disable_on_battery_saver={self.state.config.disable_on_battery_saver}, "
                f"fast_gpu>={self.state.config.fast_on_gpu_3d_percent}%/{self.state.config.fast_on_window_seconds}s, "
                f"gpu>={self.state.config.on_gpu_3d_percent}%/{self.state.config.on_gpu_3d_window_seconds}s, "
                f"gpu+vram>={self.state.config.on_gpu_3d_with_vram_percent}%+{self.state.config.on_gpu_vram_mb:.0f}MB/"
                f"{self.state.config.on_gpu_vram_window_seconds}s, "
                f"cpu_avg>={self.state.config.on_cpu_average_percent}%/{self.state.config.on_cpu_window_seconds}s, "
                f"off_window={self.state.config.off_window_seconds}s, "
                f"min_on={self.state.config.min_on_seconds}s, "
                f"min_off={self.state.config.min_off_seconds}s)."
            )
            self.refresh_tick()
        except Exception as exc:
            self._set_error(str(exc), log_prefix="Failed to enable auto mode")
            self.request_visual_update()

    def _auto_enable_reason(self, now: float) -> str | None:
        avg_gpu_fast = self._window_average(now, self.state.config.fast_on_window_seconds, "gpu_3d_percent")
        if avg_gpu_fast is not None and avg_gpu_fast >= self.state.config.fast_on_gpu_3d_percent:
            return (
                f"fast GPU 3D path avg={avg_gpu_fast:.1f}% over "
                f"{self.state.config.fast_on_window_seconds:.0f}s"
            )

        avg_gpu = self._window_average(now, self.state.config.on_gpu_3d_window_seconds, "gpu_3d_percent")
        if avg_gpu is not None and avg_gpu >= self.state.config.on_gpu_3d_percent:
            return (
                f"GPU 3D avg={avg_gpu:.1f}% over "
                f"{self.state.config.on_gpu_3d_window_seconds:.0f}s"
            )

        avg_gpu_vram = self._window_average(now, self.state.config.on_gpu_vram_window_seconds, "gpu_3d_percent")
        avg_vram = self._window_average(now, self.state.config.on_gpu_vram_window_seconds, "gpu_vram_mb")
        if (
            avg_gpu_vram is not None
            and avg_vram is not None
            and avg_gpu_vram >= self.state.config.on_gpu_3d_with_vram_percent
            and avg_vram >= self.state.config.on_gpu_vram_mb
        ):
            return (
                f"GPU 3D avg={avg_gpu_vram:.1f}% and VRAM avg={avg_vram:.0f}MB over "
                f"{self.state.config.on_gpu_vram_window_seconds:.0f}s"
            )

        avg_cpu = self._window_average(now, self.state.config.on_cpu_window_seconds, "cpu_average_percent")
        if avg_cpu is not None and avg_cpu >= self.state.config.on_cpu_average_percent:
            return (
                f"CPU average={avg_cpu:.1f}% over "
                f"{self.state.config.on_cpu_window_seconds:.0f}s"
            )

        return None

    def _auto_disable_reason(self, now: float) -> str | None:
        avg_gpu = self._window_average(now, self.state.config.off_window_seconds, "gpu_3d_percent")
        avg_cpu = self._window_average(now, self.state.config.off_window_seconds, "cpu_average_percent")
        avg_vram = self._window_average(now, self.state.config.off_window_seconds, "gpu_vram_mb")
        if avg_gpu is None or avg_cpu is None or avg_vram is None:
            return None

        if avg_gpu <= self.state.config.off_gpu_3d_percent and avg_cpu <= self.state.config.off_cpu_average_percent:
            return (
                f"GPU 3D avg={avg_gpu:.1f}% and CPU avg={avg_cpu:.1f}% over "
                f"{self.state.config.off_window_seconds:.0f}s"
            )

        if avg_gpu <= self.state.config.off_gpu_3d_with_vram_percent and avg_vram <= self.state.config.off_gpu_vram_mb:
            return (
                f"GPU 3D avg={avg_gpu:.1f}% and VRAM avg={avg_vram:.0f}MB over "
                f"{self.state.config.off_window_seconds:.0f}s"
            )

        return None

    def _background_refresh(self) -> None:
        try:
            now = time.monotonic()
            need_sync = False
            with self.state_lock:
                if (
                    self.state.current_cpu_boost is None
                    or self.state.current_gpu_boost is None
                    or now - self.state.last_state_sync_monotonic >= self.state.config.state_sync_interval_seconds
                ):
                    need_sync = True

            if need_sync:
                self.sync_performance_modes(force_log=False)

            ac_connected, battery_saver, _battery_percent = self.read_system_power()
            cpu_utils = [float(value) for value in psutil.cpu_percent(interval=None, percpu=True)]
            with self.state_lock:
                self.state.last_cpu_utilizations = cpu_utils
            gpu_3d_percent, gpu_vram_mb = self.read_gpu_telemetry()
            cpu_average = (sum(cpu_utils) / len(cpu_utils)) if cpu_utils else 0.0
            cpu_max = max(cpu_utils) if cpu_utils else 0.0
            sample = TelemetrySample(
                timestamp=now,
                cpu_average_percent=cpu_average,
                cpu_max_percent=cpu_max,
                gpu_3d_percent=gpu_3d_percent,
                gpu_vram_mb=gpu_vram_mb,
                ac_connected=ac_connected,
                battery_saver=battery_saver,
            )
            with self.state_lock:
                self._append_history(sample)
                control_mode = self.state.control_mode
                config = self.state.config
                if control_mode == "auto":
                    time_in_mode = self._time_in_current_mode(now)
                    currently_balanced = self._balanced_state_active_unlocked()
                    currently_enabled = self._performance_enabled_unlocked()
                    cpu_mode = self.state.current_cpu_boost
                    gpu_mode = self.state.current_gpu_boost
                else:
                    time_in_mode = 0.0
                    currently_balanced = False
                    currently_enabled = False
                    cpu_mode = None
                    gpu_mode = None

            if now - getattr(self, "_last_telemetry_log_monotonic", 0.0) >= self.state.config.log_interval_seconds:
                self.state.logger.log(
                    f"Telemetry cpu_avg={cpu_average:.1f}% cpu_max={cpu_max:.1f}% "
                    f"gpu_3d={gpu_3d_percent:.1f}% gpu_vram={gpu_vram_mb:.0f}MB "
                    f"ac={ac_connected} saver={battery_saver}."
                )
                self._last_telemetry_log_monotonic = now

            if control_mode == "auto":
                if not currently_enabled and not currently_balanced and (cpu_mode is not None or gpu_mode is not None):
                    if self._mixed_state_since_monotonic is None:
                        self._mixed_state_since_monotonic = now
                        self.state.logger.log(
                            f"Auto mode detected mixed performance state cpu={cpu_mode} gpu={gpu_mode}; waiting before normalization."
                        )
                    elif now - self._mixed_state_since_monotonic >= max(15.0, config.refresh_interval_seconds * 3.0):
                        self.state.logger.log(
                            f"Auto mode normalizing persistent mixed performance state cpu={cpu_mode} gpu={gpu_mode} to balanced."
                        )
                        self.apply_performance_state(False)
                    return
                self._mixed_state_since_monotonic = None

                if config.require_ac_power and not ac_connected:
                    if not currently_balanced:
                        self.state.logger.log("Auto mode forcing balanced state because AC power is not connected.")
                        self.apply_performance_state(False)
                    return

                if config.disable_on_battery_saver and battery_saver:
                    if not currently_balanced:
                        self.state.logger.log("Auto mode forcing balanced state because Battery Saver is active.")
                        self.apply_performance_state(False)
                    return

                enable_reason = self._auto_enable_reason(now)
                disable_reason = self._auto_disable_reason(now)

                if not currently_enabled:
                    if time_in_mode >= config.min_off_seconds and enable_reason is not None:
                        self.state.logger.log(f"Auto mode turning performance on because {enable_reason}.")
                        self.apply_performance_state(True)
                else:
                    if time_in_mode >= config.min_on_seconds and disable_reason is not None:
                        self.state.logger.log(f"Auto mode turning performance off because {disable_reason}.")
                        self.apply_performance_state(False)
        except Exception as exc:
            self._set_error(str(exc), log_prefix="Performance refresh failed")

    def refresh_tick(self) -> None:
        self.wake_event.set()

    def _worker_loop(self) -> None:
        self._last_telemetry_log_monotonic = 0.0
        while not self.stop_event.is_set():
            self._background_refresh()
            if self.stop_event.is_set():
                break
            if self.wake_event.wait(self.state.config.refresh_interval_seconds):
                self.wake_event.clear()

    def toggle(self) -> None:
        if self.state.control_mode == "auto":
            self.manual_set(True)
            return

        if not self.performance_enabled():
            self.set_auto_mode()
            return

        self.manual_set(False)

    def on_mouse_click(self, _sender, event_args) -> None:
        if event_args.Button == MouseButtons.Left:
            self.toggle()

    def on_manual_on(self, _sender, _event_args) -> None:
        self.manual_set(True)

    def on_manual_off(self, _sender, _event_args) -> None:
        self.manual_set(False)

    def on_auto_mode(self, _sender, _event_args) -> None:
        self.set_auto_mode()

    def on_exit(self, _sender, _event_args) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        self.telemetry_reader.close()
        self.notify_icon.Visible = False
        self.cleanup_icons()
        self.context.ExitThread()

    def run(self) -> int:
        self.sync_performance_modes(force_log=True)
        self.notify_icon.Visible = True
        self.update_visuals()
        self.worker_thread.start()
        self.refresh_tick()
        Application.Run(self.context)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tray app for toggling Razer Blade performance modes.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to tray config JSON")
    parser.add_argument("--verbose", action="store_true", help="also print logs to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = TrayConfig.load(args.config)
    logger = FileLogger(config.log_path, args.verbose)
    guard = SingleInstanceGuard(MUTEX_NAME)
    app = CpuBoostTrayApp(AppState(config=config, logger=logger))

    try:
        logger.log("CPU boost tray starting.")
        result = app.run()
        logger.log("CPU boost tray exiting.")
        return result
    finally:
        guard.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CpuBoostTrayError as exc:
        if str(exc) == "CPU boost tray is already running":
            raise SystemExit(0)
        raise
    except Exception:
        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] Unhandled exception\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
        raise
