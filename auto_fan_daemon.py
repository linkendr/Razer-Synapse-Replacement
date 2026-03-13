#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import razer_fan_control as rfc


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "auto-fan-config.json"
CRASH_LOG_PATH = PROJECT_DIR / "auto-fan-daemon-crash.log"
ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Global\RazerFanControlAutoFanDaemon"


class AutoFanDaemonError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurveStep:
    temp_c: float
    rpm: int


@dataclass(frozen=True)
class AutoFanConfig:
    poll_interval_seconds: float
    cooldown_samples: int
    temp_hysteresis_c: float
    startup_blast_seconds: float
    startup_blast_rpm: int
    manual_power_mode: str
    auto_power_mode: str
    restore_auto_on_exit: bool
    unsafe_unclamped: bool
    log_path: Path
    curve: list[CurveStep]
    vendor_id: int
    product_id: int

    @classmethod
    def load(cls, path: Path) -> "AutoFanConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        curve = [CurveStep(float(item["temp_c"]), int(item["rpm"])) for item in data["curve"]]
        curve.sort(key=lambda item: item.temp_c)
        log_path = Path(str(data.get("log_path", "auto-fan-daemon.log")))
        if not log_path.is_absolute():
            log_path = path.parent / log_path

        if not curve:
            raise AutoFanDaemonError("curve must contain at least one step")

        return cls(
            poll_interval_seconds=float(data.get("poll_interval_seconds", 5.0)),
            cooldown_samples=max(1, int(data.get("cooldown_samples", 3))),
            temp_hysteresis_c=max(0.0, float(data.get("temp_hysteresis_c", 3.0))),
            startup_blast_seconds=max(0.0, float(data.get("startup_blast_seconds", 60.0))),
            startup_blast_rpm=max(0, int(data.get("startup_blast_rpm", 5300))),
            manual_power_mode=str(data.get("manual_power_mode", "balanced")),
            auto_power_mode=str(data.get("auto_power_mode", "balanced")),
            restore_auto_on_exit=bool(data.get("restore_auto_on_exit", True)),
            unsafe_unclamped=bool(data.get("unsafe_unclamped", False)),
            log_path=log_path,
            curve=curve,
            vendor_id=int(data.get("vendor_id", rfc.RAZER_VENDOR_ID)),
            product_id=int(data.get("product_id", rfc.DEFAULT_PRODUCT_ID)),
        )


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


class SingleInstanceGuard:
    def __init__(self, name: str) -> None:
        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise AutoFanDaemonError("failed to create daemon mutex")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            raise AutoFanDaemonError("daemon is already running")

    def close(self) -> None:
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


class LibreHardwareMonitorReader:
    def __init__(self) -> None:
        if not rfc.LHM_DLL.exists():
            raise AutoFanDaemonError(f"LibreHardwareMonitor library not found at {rfc.LHM_DLL}")

        import clr  # type: ignore

        clr.AddReference(str(rfc.LHM_DLL))
        from LibreHardwareMonitor.Hardware import Computer, SensorType  # type: ignore

        self._computer_type = Computer
        self._sensor_type = SensorType
        self._computer = None
        self._hardware_nodes = []

    def open(self) -> None:
        computer = self._computer_type()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.Open()
        self._computer = computer
        self._hardware_nodes = []

        for hardware in self._computer.Hardware:
            hardware_name = str(hardware.Name)
            if "AMD Ryzen" in hardware_name or "NVIDIA" in hardware_name:
                self._hardware_nodes.append(hardware)
                self._hardware_nodes.extend(list(hardware.SubHardware))

        for hardware in self._hardware_nodes:
            hardware.Update()

    def close(self) -> None:
        if self._computer is not None:
            self._computer.Close()
            self._computer = None
            self._hardware_nodes = []

    def read(self) -> rfc.ThermalReadings:
        if self._computer is None:
            self.open()

        cpu_temp = None
        gpu_temp = None
        gpu_hotspot = None

        for hardware in self._hardware_nodes:
            hardware.Update()

        for hardware in self._hardware_nodes:
            hardware_name = str(hardware.Name)
            for sensor in hardware.Sensors:
                if sensor.SensorType != self._sensor_type.Temperature or sensor.Value is None:
                    continue

                sensor_name = str(sensor.Name)
                value = round(float(sensor.Value), 2)
                if "AMD Ryzen" in hardware_name and sensor_name == "Core (Tctl/Tdie)":
                    cpu_temp = value
                elif "NVIDIA" in hardware_name and sensor_name == "GPU Core":
                    gpu_temp = value
                elif "NVIDIA" in hardware_name and sensor_name == "GPU Hot Spot":
                    gpu_hotspot = value

        return rfc.ThermalReadings(cpu_temp_c=cpu_temp, gpu_temp_c=gpu_temp, gpu_hotspot_c=gpu_hotspot)


class AutoFanDaemon:
    def __init__(self, config: AutoFanConfig, logger: FileLogger, dry_run: bool) -> None:
        self.config = config
        self.logger = logger
        self.dry_run = dry_run
        self.running = True
        self.lower_target_pending: int | None = None
        self.lower_target_count = 0
        self.monitor = LibreHardwareMonitorReader()
        self.guard = SingleInstanceGuard(MUTEX_NAME)
        self._shutdown_done = False
        self._last_telemetry_log_at = 0.0
        self.candidate = None
        self.current_power_mode = 0

        state = self._refresh_candidate("initial attach")
        self.current_target_rpm = state.fan_rpm if state.manual_fan else 0
        self.current_power_mode = state.power_mode
        self.logger.log(
            f"Daemon attached to {state.model_name} on {state.path}. "
            f"Initial fan_rpm={state.fan_rpm} manual={state.manual_fan} power_mode={state.power_mode}."
        )

        atexit.register(self.shutdown)
        for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            if hasattr(signal, sig_name):
                signal.signal(getattr(signal, sig_name), self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:
        self.logger.log(f"Received signal {signum}, shutting down.")
        self.running = False

    def _refresh_candidate(self, reason: str) -> rfc.FanQueryResult:
        candidate, state = rfc.find_working_device(self.config.vendor_id, self.config.product_id)
        path_changed = self.candidate is None or self.candidate.path != candidate.path
        self.candidate = candidate
        self.current_power_mode = state.power_mode
        if path_changed:
            self.logger.log(f"Device attach ({reason}): using {state.path}.")
        else:
            self.logger.log(f"Device revalidated ({reason}) on {state.path}.")
        return state

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            if self.config.restore_auto_on_exit and not self.dry_run:
                self.logger.log("Restoring automatic fan mode on daemon exit.")
                self._set_auto()
        except Exception as exc:
            self.logger.log(f"Failed to restore automatic mode on exit: {exc}")
        finally:
            try:
                self.monitor.close()
            finally:
                self.guard.close()

    def _control_temp(self, temps: rfc.ThermalReadings) -> float:
        values = [value for value in (temps.cpu_temp_c, temps.gpu_hotspot_c, temps.gpu_temp_c) if value is not None]
        if not values:
            raise AutoFanDaemonError("no thermal sensors returned data")
        return max(values)

    def _target_rpm(self, control_temp: float) -> int:
        target_index = 0
        for idx, step in enumerate(self.config.curve):
            if control_temp >= step.temp_c:
                target_index = idx
            else:
                break

        current_index = 0
        for idx, step in enumerate(self.config.curve):
            if self.current_target_rpm >= step.rpm:
                current_index = idx

        if target_index < current_index:
            step_down_threshold = self.config.curve[current_index].temp_c - self.config.temp_hysteresis_c
            if control_temp > step_down_threshold:
                return self.current_target_rpm

        return self.config.curve[target_index].rpm

    def _apply_target(self, target_rpm: int, temps: rfc.ThermalReadings, control_temp: float) -> None:
        if target_rpm == self.current_target_rpm:
            self.lower_target_pending = None
            self.lower_target_count = 0
            return

        if target_rpm > self.current_target_rpm:
            self.lower_target_pending = None
            self.lower_target_count = 0
            self.logger.log(
                f"Raising fan target to {target_rpm} RPM at control_temp={control_temp:.2f}C "
                f"(cpu={temps.cpu_temp_c}, gpu={temps.gpu_temp_c}, hotspot={temps.gpu_hotspot_c})."
            )
            self._set_manual(target_rpm)
            self.current_target_rpm = target_rpm
            return

        if self.lower_target_pending == target_rpm:
            self.lower_target_count += 1
        else:
            self.lower_target_pending = target_rpm
            self.lower_target_count = 1

        self.logger.log(
            f"Lower target candidate {target_rpm} RPM seen {self.lower_target_count}/{self.config.cooldown_samples} "
            f"times at control_temp={control_temp:.2f}C."
        )

        if self.lower_target_count >= self.config.cooldown_samples:
            self._set_target_immediately(target_rpm, "Lowering fan target")
            self.lower_target_pending = None
            self.lower_target_count = 0

    def _set_target_immediately(self, target_rpm: int, reason: str) -> None:
        if target_rpm == 0:
            self.logger.log(f"{reason}: switching back to automatic fan control.")
            self._set_auto()
        else:
            self.logger.log(f"{reason}: setting {target_rpm} RPM.")
            self._set_manual(target_rpm)
        self.current_target_rpm = target_rpm

    def _run_startup_blast(self) -> None:
        if self.config.startup_blast_seconds <= 0 or self.config.startup_blast_rpm <= 0:
            return

        if self.candidate is None:
            self._refresh_candidate("startup blast precheck")
        clamped_rpm, _ = rfc.clamp_rpm(self.config.startup_blast_rpm, self.candidate.product_id, self.config.unsafe_unclamped)
        self.logger.log(
            f"Startup blast enabled: forcing {clamped_rpm} RPM for {self.config.startup_blast_seconds:.0f} seconds."
        )
        self._set_manual(clamped_rpm)
        self.current_target_rpm = clamped_rpm

        deadline = time.time() + self.config.startup_blast_seconds
        while self.running:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(self.config.poll_interval_seconds, remaining))

        if not self.running:
            return

        try:
            temps = self.monitor.read()
            control_temp = self._control_temp(temps)
            target_rpm = self._target_rpm(control_temp)
            self.logger.log(
                f"Startup blast complete. Transitioning to curve target {target_rpm} RPM at "
                f"control_temp={control_temp:.2f}C (cpu={temps.cpu_temp_c}, gpu={temps.gpu_temp_c}, hotspot={temps.gpu_hotspot_c})."
            )
            self.lower_target_pending = None
            self.lower_target_count = 0
            self._set_target_immediately(target_rpm, "Post-startup transition")
        except Exception as exc:
            self.logger.log(f"Startup blast handoff failed: {exc}")
            self.logger.log(traceback.format_exc().strip())

    def _set_manual(self, rpm: int) -> None:
        if self.candidate is None:
            self._refresh_candidate("manual mode precheck")
        clamped_rpm, raw = rfc.clamp_rpm(rpm, self.candidate.product_id, self.config.unsafe_unclamped)
        power_mode = rfc.resolve_power_mode(self.config.manual_power_mode, 0)
        if self.dry_run:
            self.logger.log(f"[dry-run] Would set both fans to {clamped_rpm} RPM in power mode {power_mode}.")
            return

        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                with rfc.RazerDevice(self.candidate) as device:
                    for fan_id in (1, 2):
                        response = device.set_fan(fan_id, raw)
                        if not response.is_success:
                            raise AutoFanDaemonError(f"fan {fan_id} write failed with status {response.status}")
                    response = device.set_power(power_mode, auto_fan=False)
                    if not response.is_success:
                        raise AutoFanDaemonError(f"manual power write failed with status {response.status}")

                    verify_power = device.query_power()
                    verify_fan_1 = device.query_fan(1)
                    verify_fan_2 = device.query_fan(2)
                    if (
                        verify_power.is_success
                        and verify_fan_1.is_success
                        and verify_fan_2.is_success
                        and rfc.decode_manual_fan(verify_power)
                        and rfc.decode_fan_response(verify_fan_1) == clamped_rpm
                        and rfc.decode_fan_response(verify_fan_2) == clamped_rpm
                    ):
                        return
                    raise AutoFanDaemonError(f"manual mode verification failed for target {clamped_rpm} RPM")
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    self.logger.log(f"Manual mode attempt {attempt} failed: {exc}")
                    time.sleep(0.35)
                    self._refresh_candidate(f"manual mode recovery attempt {attempt}")
                else:
                    break

        raise AutoFanDaemonError(f"manual mode verification failed for target {clamped_rpm} RPM: {last_error}")

    def _set_auto(self) -> None:
        power_mode = rfc.resolve_power_mode(self.config.auto_power_mode, 0)
        if self.dry_run:
            self.logger.log(f"[dry-run] Would restore automatic mode with power mode {power_mode}.")
            return

        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                if self.candidate is None:
                    self._refresh_candidate("auto mode precheck")
                with rfc.RazerDevice(self.candidate) as device:
                    response = device.set_power(power_mode, auto_fan=True)
                    if not response.is_success:
                        raise AutoFanDaemonError(f"auto mode write failed with status {response.status}")

                    verify_power = device.query_power()
                    if verify_power.is_success and not rfc.decode_manual_fan(verify_power) and rfc.decode_power_mode(verify_power) == power_mode:
                        return
                    raise AutoFanDaemonError("automatic mode verification failed")
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    self.logger.log(f"Automatic mode attempt {attempt} failed: {exc}")
                    time.sleep(0.35)
                    self._refresh_candidate(f"automatic mode recovery attempt {attempt}")
                else:
                    break

        raise AutoFanDaemonError(f"automatic mode verification failed: {last_error}")

    def _should_log_telemetry(self, target_rpm: int) -> bool:
        now = time.time()
        if target_rpm != self.current_target_rpm:
            self._last_telemetry_log_at = now
            return True
        if now - self._last_telemetry_log_at >= 60.0:
            self._last_telemetry_log_at = now
            return True
        return False

    def run(self, once: bool, duration_seconds: float | None) -> int:
        deadline = time.time() + duration_seconds if duration_seconds is not None else None
        self.logger.log(
            f"Daemon started with poll_interval={self.config.poll_interval_seconds}s "
            f"cooldown_samples={self.config.cooldown_samples} temp_hysteresis_c={self.config.temp_hysteresis_c} "
            f"startup_blast_seconds={self.config.startup_blast_seconds}s "
            f"startup_blast_rpm={self.config.startup_blast_rpm} dry_run={self.dry_run}."
        )

        if not self.dry_run and not once:
            self._run_startup_blast()

        while self.running:
            try:
                temps = self.monitor.read()
                control_temp = self._control_temp(temps)
                target_rpm = self._target_rpm(control_temp)
                if self._should_log_telemetry(target_rpm):
                    self.logger.log(
                        f"Telemetry cpu={temps.cpu_temp_c}C gpu={temps.gpu_temp_c}C hotspot={temps.gpu_hotspot_c}C "
                        f"control={control_temp:.2f}C target={target_rpm} current={self.current_target_rpm}."
                    )
                self._apply_target(target_rpm, temps, control_temp)
            except Exception as exc:
                self.logger.log(f"Loop error: {exc}")
                self.logger.log(traceback.format_exc().strip())
                self.monitor.close()

            if once:
                break
            if deadline is not None and time.time() >= deadline:
                break
            time.sleep(self.config.poll_interval_seconds)

        self.logger.log("Daemon loop exiting.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Background auto fan daemon for the Razer Blade 14 2021.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to daemon config JSON")
    parser.add_argument("--dry-run", action="store_true", help="log intended actions without changing fan state")
    parser.add_argument("--once", action="store_true", help="run one control cycle and exit")
    parser.add_argument("--duration-seconds", type=float, help="optional max runtime for testing")
    parser.add_argument("--verbose", action="store_true", help="also print logs to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AutoFanConfig.load(args.config)
    logger = FileLogger(config.log_path, args.verbose)
    daemon = AutoFanDaemon(config=config, logger=logger, dry_run=args.dry_run)
    try:
        return daemon.run(once=args.once, duration_seconds=args.duration_seconds)
    finally:
        daemon.shutdown()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutoFanDaemonError as exc:
        if str(exc) == "daemon is already running":
            raise SystemExit(0)
        raise
    except Exception:
        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] Unhandled exception\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
        raise
