#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import hid


REPORT_LENGTH = 90
FEATURE_REPORT_LENGTH = REPORT_LENGTH + 1
RAZER_VENDOR_ID = 0x1532
DEFAULT_PRODUCT_ID = 0x0270
DEFAULT_TRANSACTION_ID = 0x1F

GET_DIRECTION = 0x01
SET_DIRECTION = 0x00

COMMAND_CLASS_SYSTEM = 0x0D

COMMAND_FAN = 0x01
COMMAND_POWER = 0x02
COMMAND_BOOST = 0x07

BOOST_CPU = 0x01
BOOST_GPU = 0x02

LED_VARIABLE_STORAGE = 0x01
LED_LOGO = 0x04
LED_BACKLIGHT = 0x05

MATRIX_EFFECT_CUSTOMFRAME = 0x05
MATRIX_EFFECT_STATIC = 0x06

RESPONSE_SUCCESS = 0x02

MODEL_TABLE = {
    0x0270: {"name": 'Razer Blade 14" 2021', "fan_min": 3100, "fan_max": 5300},
    0x026F: {"name": 'Razer Blade 15" 2021 Base', "fan_min": 3100, "fan_max": 5300},
    0x026D: {"name": 'Razer Blade 15" 2021 Advanced', "fan_min": 3100, "fan_max": 5300},
    0x0276: {"name": 'Razer Blade 15" 2021 Mid Advanced', "fan_min": 3100, "fan_max": 5300},
}
WORKING_DEVICE_CACHE: dict[tuple[int, int], DeviceCandidate] = {}

POWER_MODE_MAP = {
    "balanced": 0,
    "custom": 1,
    "gaming": 1,
    "creator": 2,
}

CPU_BOOST_MODE_MAP = {
    "off": 0,
    "on": 1,
}
GPU_BOOST_MODE_MAP = {
    "low": 0,
    "medium": 1,
    "balanced": 1,
    "off": 1,
    "high": 2,
    "on": 2,
}
PROJECT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = PROJECT_DIR / "vendor" / "LibreHardwareMonitor-v0.9.6"
LHM_DLL = VENDOR_DIR / "LibreHardwareMonitorLib.dll"
RAZER_WRITE_MUTEX = r"Global\RazerReadWriteGuardMutex"


class RazerFanControlError(RuntimeError):
    pass


class NamedMutex:
    def __init__(self, name: str) -> None:
        self._name = name
        self._handle = None

    def __enter__(self) -> "NamedMutex":
        self._handle = ctypes.windll.kernel32.CreateMutexW(None, False, self._name)
        if not self._handle:
            raise RazerFanControlError(f"failed to create/open mutex {self._name}")

        wait_result = ctypes.windll.kernel32.WaitForSingleObject(self._handle, 5000)
        if wait_result not in (0, 0x80):
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            raise RazerFanControlError(f"failed waiting for mutex {self._name}: {wait_result}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle:
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


@dataclass(frozen=True)
class DeviceCandidate:
    path: bytes
    interface_number: int | None
    usage_page: int | None
    usage: int | None
    product_id: int
    vendor_id: int
    product_string: str | None
    manufacturer_string: str | None

    @property
    def path_str(self) -> str:
        return self.path.decode("utf-8", errors="replace")

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path_str,
            "interface_number": self.interface_number,
            "usage_page": self.usage_page,
            "usage": self.usage,
            "product_id": f"0x{self.product_id:04X}",
            "vendor_id": f"0x{self.vendor_id:04X}",
            "product_string": self.product_string,
            "manufacturer_string": self.manufacturer_string,
        }


@dataclass(frozen=True)
class PacketResponse:
    status: int
    transaction_id: int
    data_size: int
    command_class: int
    command_id: int
    args: bytes
    raw: bytes

    @property
    def is_success(self) -> bool:
        return self.status == RESPONSE_SUCCESS

    @property
    def direction(self) -> int:
        return (self.command_id >> 7) & 0x01

    @property
    def command_type(self) -> int:
        return self.command_id & 0x7F


@dataclass(frozen=True)
class FanQueryResult:
    fan_rpm: int
    fan_raw: int
    manual_fan: bool
    power_mode: int
    cpu_boost: int
    gpu_boost: int
    path: str
    product_id: str
    model_name: str

    def as_dict(self) -> dict[str, object]:
        return {
            "model_name": self.model_name,
            "product_id": self.product_id,
            "path": self.path,
            "fan_rpm": self.fan_rpm,
            "fan_raw": self.fan_raw,
            "manual_fan": self.manual_fan,
            "power_mode": self.power_mode,
            "cpu_boost": self.cpu_boost,
            "gpu_boost": self.gpu_boost,
        }


@dataclass(frozen=True)
class ThermalReadings:
    cpu_temp_c: float | None
    gpu_temp_c: float | None
    gpu_hotspot_c: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "cpu_temp_c": self.cpu_temp_c,
            "gpu_temp_c": self.gpu_temp_c,
            "gpu_hotspot_c": self.gpu_hotspot_c,
        }


def crc_packet(buffer: bytes) -> int:
    result = 0
    for byte in buffer[2:88]:
        result ^= byte
    return result


def build_packet(
    command_class: int,
    command_id: int,
    direction: int,
    args: Iterable[int],
    data_size: int | None = None,
    transaction_id: int = DEFAULT_TRANSACTION_ID,
) -> bytes:
    payload = list(args)
    packet = bytearray(REPORT_LENGTH)
    packet[0] = 0x00
    packet[1] = transaction_id
    packet[2] = 0x00
    packet[3] = 0x00
    packet[4] = 0x00
    packet[5] = len(payload) if data_size is None else data_size
    packet[6] = command_class
    packet[7] = ((direction & 0x01) << 7) | (command_id & 0x7F)
    packet[8:8 + len(payload)] = bytes(payload)
    packet[88] = crc_packet(packet)
    packet[89] = 0x00
    return bytes([0x00]) + bytes(packet)


def parse_response(report: bytes) -> PacketResponse:
    if len(report) != FEATURE_REPORT_LENGTH:
        raise RazerFanControlError(f"unexpected report length {len(report)}")

    packet = report[1:]
    return PacketResponse(
        status=packet[0],
        transaction_id=packet[1],
        data_size=packet[5],
        command_class=packet[6],
        command_id=packet[7],
        args=bytes(packet[8:88]),
        raw=bytes(packet),
    )


def enumerate_candidates(vendor_id: int, product_id: int) -> list[DeviceCandidate]:
    candidates: list[DeviceCandidate] = []
    for info in hid.enumerate(vendor_id, product_id):
        candidates.append(
            DeviceCandidate(
                path=info["path"],
                interface_number=info.get("interface_number"),
                usage_page=info.get("usage_page"),
                usage=info.get("usage"),
                product_id=info["product_id"],
                vendor_id=info["vendor_id"],
                product_string=info.get("product_string"),
                manufacturer_string=info.get("manufacturer_string"),
            )
        )
    return candidates


def read_thermal_sensors() -> ThermalReadings:
    if not LHM_DLL.exists():
        raise RazerFanControlError(f"LibreHardwareMonitor library not found at {LHM_DLL}")

    import clr  # type: ignore

    clr.AddReference(str(LHM_DLL))
    from LibreHardwareMonitor.Hardware import Computer, SensorType  # type: ignore

    computer = Computer()
    computer.IsCpuEnabled = True
    computer.IsGpuEnabled = True
    computer.IsMotherboardEnabled = True
    computer.IsControllerEnabled = True
    computer.Open()

    cpu_temp = None
    gpu_temp = None
    gpu_hotspot = None

    try:
        for _ in range(3):
            for hardware in computer.Hardware:
                hardware.Update()
                for sub_hardware in hardware.SubHardware:
                    sub_hardware.Update()

        for hardware in computer.Hardware:
            name = str(hardware.Name)
            for sensor in hardware.Sensors:
                if sensor.SensorType != SensorType.Temperature or sensor.Value is None:
                    continue

                value = round(float(sensor.Value), 2)
                sensor_name = str(sensor.Name)

                if "AMD Ryzen" in name and sensor_name == "Core (Tctl/Tdie)":
                    cpu_temp = value
                elif "NVIDIA" in name and sensor_name == "GPU Core":
                    gpu_temp = value
                elif "NVIDIA" in name and sensor_name == "GPU Hot Spot":
                    gpu_hotspot = value
    finally:
        computer.Close()

    return ThermalReadings(cpu_temp_c=cpu_temp, gpu_temp_c=gpu_temp, gpu_hotspot_c=gpu_hotspot)


def candidate_sort_key(candidate: DeviceCandidate) -> tuple[int, int, int]:
    preferred = 0
    if candidate.interface_number == 2:
        preferred = -3
    elif candidate.usage == 2:
        preferred = -2
    elif candidate.usage_page == 1:
        preferred = -1
    return (preferred, candidate.interface_number or -99, candidate.usage or -99)


class RazerDevice:
    def __init__(self, candidate: DeviceCandidate):
        self.candidate = candidate
        self._device = hid.device()
        self._device.open_path(candidate.path)
        self._device.set_nonblocking(0)

    def close(self) -> None:
        self._device.close()

    def __enter__(self) -> "RazerDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def keyboard_transaction_id(self) -> int:
        return DEFAULT_TRANSACTION_ID

    def transact(self, packet: bytes, delay_seconds: float = 0.20) -> PacketResponse:
        with NamedMutex(RAZER_WRITE_MUTEX):
            sent = self._device.send_feature_report(packet)
            if sent < 0:
                raise RazerFanControlError(f"send_feature_report failed on {self.candidate.path_str}")

            time.sleep(delay_seconds)
            report = self._device.get_feature_report(0, FEATURE_REPORT_LENGTH)
            response = parse_response(bytes(report))
            return response

    def query_fan(self, fan_id: int = 1) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_FAN, GET_DIRECTION, [0x00, fan_id, 0x00], data_size=0x03)
        return self.transact(packet)

    def set_fan(self, fan_id: int, fan_raw_div_100: int) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_FAN, SET_DIRECTION, [0x00, fan_id, fan_raw_div_100], data_size=0x03)
        return self.transact(packet)

    def query_power(self) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_POWER, GET_DIRECTION, [0x00, 0x02, 0x00, 0x00], data_size=0x04)
        return self.transact(packet)

    def set_power(self, power_mode: int, auto_fan: bool) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_POWER, SET_DIRECTION, [0x00, 0x01, power_mode, 0x00 if auto_fan else 0x01], data_size=0x04)
        return self.transact(packet)

    def query_boost(self, boost_id: int) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_BOOST, GET_DIRECTION, [0x00, boost_id, 0x00], data_size=0x03)
        return self.transact(packet)

    def set_boost(self, boost_id: int, mode: int) -> PacketResponse:
        packet = build_packet(COMMAND_CLASS_SYSTEM, COMMAND_BOOST, SET_DIRECTION, [0x00, boost_id, mode], data_size=0x03)
        return self.transact(packet)

    def set_keyboard_brightness_raw(self, brightness_raw: int) -> PacketResponse:
        packet = build_packet(0x0E, 0x04, SET_DIRECTION, [0x01, brightness_raw, 0x00], data_size=0x03, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)

    def set_keyboard_brightness_legacy_raw(self, brightness_raw: int) -> PacketResponse:
        packet = build_packet(0x03, 0x03, SET_DIRECTION, [LED_VARIABLE_STORAGE, LED_BACKLIGHT, brightness_raw], data_size=0x03, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)

    def send_keyboard_row(self, row_id: int, rgb: tuple[int, int, int]) -> PacketResponse:
        if row_id < 0 or row_id > 5:
            raise RazerFanControlError("row_id must be between 0 and 5")

        r, g, b = rgb
        # Match the Linux librazerblade/razer-laptop-control row layout:
        # ff <row> 00 0f 00 00 00 + 15 RGB triplets.
        args = bytearray(52)
        args[0] = 0xFF
        args[1] = row_id
        args[2] = 0x00
        args[3] = 0x0F
        args[4] = 0x00
        args[5] = 0x00
        args[6] = 0x00
        for idx in range(15):
            offset = 7 + (idx * 3)
            args[offset] = r
            args[offset + 1] = g
            args[offset + 2] = b

        packet = build_packet(0x03, 0x0B, SET_DIRECTION, args, data_size=0x34, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)

    def apply_chroma(self) -> PacketResponse:
        packet = build_packet(0x03, 0x0A, SET_DIRECTION, [0x05, 0x00], data_size=0x02, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)

    def set_keyboard_static_effect(self, rgb: tuple[int, int, int]) -> PacketResponse:
        r, g, b = rgb
        packet = build_packet(0x03, 0x0A, SET_DIRECTION, [MATRIX_EFFECT_STATIC, r, g, b], data_size=0x04, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)

    def set_logo_state(self, enabled: bool) -> PacketResponse:
        packet = build_packet(0x03, 0x00, SET_DIRECTION, [LED_VARIABLE_STORAGE, LED_LOGO, 0x01 if enabled else 0x00], data_size=0x03, transaction_id=self.keyboard_transaction_id)
        return self.transact(packet)


def product_model(product_id: int) -> dict[str, object]:
    return MODEL_TABLE.get(product_id, {"name": f"Unknown 0x{product_id:04X}", "fan_min": 3100, "fan_max": 5300})


def decode_fan_response(response: PacketResponse) -> int:
    return response.args[2] * 100


def decode_power_mode(response: PacketResponse) -> int:
    return response.args[2]


def decode_manual_fan(response: PacketResponse) -> bool:
    return response.args[3] == 1


def decode_boost(response: PacketResponse) -> int:
    return response.args[2]


def resolve_power_mode(value: str | None, current_mode: int) -> int:
    if value is None:
        return current_mode
    lowered = value.lower()
    if lowered in POWER_MODE_MAP:
        return POWER_MODE_MAP[lowered]
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise RazerFanControlError(f"invalid power mode {value!r}") from exc
    if parsed < 0 or parsed > 4:
        raise RazerFanControlError("power mode must be between 0 and 4")
    return parsed


def resolve_cpu_boost_mode(value: str) -> int:
    lowered = value.lower()
    if lowered in CPU_BOOST_MODE_MAP:
        return CPU_BOOST_MODE_MAP[lowered]
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise RazerFanControlError(f"invalid boost mode {value!r}") from exc
    if parsed < 0 or parsed > 255:
        raise RazerFanControlError("boost mode must be between 0 and 255")
    return parsed


def resolve_gpu_boost_mode(value: str) -> int:
    lowered = value.lower()
    if lowered in GPU_BOOST_MODE_MAP:
        return GPU_BOOST_MODE_MAP[lowered]
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise RazerFanControlError(f"invalid GPU mode {value!r}") from exc
    if parsed < 0 or parsed > 255:
        raise RazerFanControlError("GPU mode must be between 0 and 255")
    return parsed


def brightness_percent_to_raw(percent: int) -> int:
    if percent < 0 or percent > 100:
        raise RazerFanControlError("brightness percent must be between 0 and 100")
    return round((percent / 100.0) * 255.0)


def set_keyboard_solid(vendor_id: int, product_id: int, rgb: tuple[int, int, int], brightness_percent: int) -> None:
    for channel in rgb:
        if channel < 0 or channel > 255:
            raise RazerFanControlError("RGB channels must be between 0 and 255")

    candidate, _ = find_working_device(vendor_id, product_id)
    brightness_raw = brightness_percent_to_raw(brightness_percent)

    with RazerDevice(candidate) as device:
        # Prefer the Linux/librazerblade brightness path first, then fall back
        # to the Synapse-captured legacy packet family.
        response = device.set_keyboard_brightness_raw(brightness_raw)
        if not response.is_success:
            response = device.set_keyboard_brightness_legacy_raw(brightness_raw)
        if not response.is_success:
            raise RazerFanControlError(f"keyboard brightness write failed with status {response.status}")

        response = device.set_logo_state(False)
        if not response.is_success:
            raise RazerFanControlError(f"logo state write failed with status {response.status}")

        for row_id in range(6):
            response = device.send_keyboard_row(row_id, rgb)
            if not response.is_success:
                raise RazerFanControlError(f"keyboard row {row_id} write failed with status {response.status}")

        response = device.apply_chroma()
        if not response.is_success:
            raise RazerFanControlError(f"keyboard final apply failed with status {response.status}")


def query_boost_mode(vendor_id: int, product_id: int, boost_id: int) -> int:
    def query_with_candidate(candidate: DeviceCandidate) -> int:
        with RazerDevice(candidate) as device:
            response = device.query_boost(boost_id)
            if not response.is_success:
                raise RazerFanControlError(f"boost query failed with status {response.status}")
            return decode_boost(response)

    cache_key = (vendor_id, product_id)
    cached_candidate = WORKING_DEVICE_CACHE.get(cache_key)
    if cached_candidate is not None:
        try:
            return query_with_candidate(cached_candidate)
        except Exception:
            WORKING_DEVICE_CACHE.pop(cache_key, None)

    candidate, _ = find_working_device(vendor_id, product_id)
    return query_with_candidate(candidate)


def query_performance_modes(vendor_id: int, product_id: int) -> tuple[int, int]:
    def query_with_candidate(candidate: DeviceCandidate) -> tuple[int, int]:
        with RazerDevice(candidate) as device:
            cpu_response = device.query_boost(BOOST_CPU)
            gpu_response = device.query_boost(BOOST_GPU)
            if not cpu_response.is_success:
                raise RazerFanControlError(f"CPU boost query failed with status {cpu_response.status}")
            if not gpu_response.is_success:
                raise RazerFanControlError(f"GPU boost query failed with status {gpu_response.status}")
            return decode_boost(cpu_response), decode_boost(gpu_response)

    cache_key = (vendor_id, product_id)
    cached_candidate = WORKING_DEVICE_CACHE.get(cache_key)
    if cached_candidate is not None:
        try:
            return query_with_candidate(cached_candidate)
        except Exception:
            WORKING_DEVICE_CACHE.pop(cache_key, None)

    candidate, state = find_working_device(vendor_id, product_id)
    return state.cpu_boost, state.gpu_boost


def set_boost_mode(vendor_id: int, product_id: int, boost_id: int, mode: int) -> int:
    def set_with_candidate(candidate: DeviceCandidate) -> int:
        with RazerDevice(candidate) as device:
            response = device.set_boost(boost_id, mode)
            if not response.is_success:
                raise RazerFanControlError(f"boost write failed with status {response.status}")
            verify = device.query_boost(boost_id)
            if not verify.is_success:
                raise RazerFanControlError(f"boost verify failed with status {verify.status}")
            verified_mode = decode_boost(verify)
            if verified_mode != mode:
                raise RazerFanControlError(f"boost verify mismatch: requested {mode}, got {verified_mode}")
            return verified_mode

    cache_key = (vendor_id, product_id)
    cached_candidate = WORKING_DEVICE_CACHE.get(cache_key)
    if cached_candidate is not None:
        try:
            return set_with_candidate(cached_candidate)
        except Exception:
            WORKING_DEVICE_CACHE.pop(cache_key, None)

    candidate, _ = find_working_device(vendor_id, product_id)
    return set_with_candidate(candidate)


def set_performance_modes(
    vendor_id: int,
    product_id: int,
    *,
    cpu_mode: int | None = None,
    gpu_mode: int | None = None,
) -> tuple[int, int]:
    if cpu_mode is None and gpu_mode is None:
        raise RazerFanControlError("at least one performance mode must be provided")

    def set_with_candidate(candidate: DeviceCandidate) -> tuple[int, int]:
        with RazerDevice(candidate) as device:
            if cpu_mode is not None:
                response = device.set_boost(BOOST_CPU, cpu_mode)
                if not response.is_success:
                    raise RazerFanControlError(f"CPU boost write failed with status {response.status}")
            if gpu_mode is not None:
                response = device.set_boost(BOOST_GPU, gpu_mode)
                if not response.is_success:
                    raise RazerFanControlError(f"GPU boost write failed with status {response.status}")

            cpu_verify = device.query_boost(BOOST_CPU)
            gpu_verify = device.query_boost(BOOST_GPU)
            if not cpu_verify.is_success:
                raise RazerFanControlError(f"CPU boost verify failed with status {cpu_verify.status}")
            if not gpu_verify.is_success:
                raise RazerFanControlError(f"GPU boost verify failed with status {gpu_verify.status}")
            verified_cpu = decode_boost(cpu_verify)
            verified_gpu = decode_boost(gpu_verify)
            if cpu_mode is not None and verified_cpu != cpu_mode:
                raise RazerFanControlError(f"CPU boost verify mismatch: requested {cpu_mode}, got {verified_cpu}")
            if gpu_mode is not None and verified_gpu != gpu_mode:
                raise RazerFanControlError(f"GPU boost verify mismatch: requested {gpu_mode}, got {verified_gpu}")
            return verified_cpu, verified_gpu

    cache_key = (vendor_id, product_id)
    cached_candidate = WORKING_DEVICE_CACHE.get(cache_key)
    if cached_candidate is not None:
        try:
            return set_with_candidate(cached_candidate)
        except Exception:
            WORKING_DEVICE_CACHE.pop(cache_key, None)

    candidate, _ = find_working_device(vendor_id, product_id)
    return set_with_candidate(candidate)


def clamp_rpm(rpm: int, product_id: int, unsafe_unclamped: bool) -> tuple[int, int]:
    if rpm < 0:
        raise RazerFanControlError("rpm must be non-negative")
    model = product_model(product_id)
    fan_min = int(model["fan_min"])
    fan_max = int(model["fan_max"])
    target = rpm
    if not unsafe_unclamped:
        if target == 0:
            return 0, 0
        target = max(min(target, fan_max), fan_min)
    if target > 25500:
        raise RazerFanControlError("rpm is too large for the packet format")
    normalized_target = 0 if target == 0 else (target // 100) * 100
    return normalized_target, normalized_target // 100


def probe_candidate(candidate: DeviceCandidate) -> dict[str, object]:
    result = candidate.as_dict()
    try:
        with RazerDevice(candidate) as device:
            response = device.query_fan()
            result["query_success"] = response.is_success
            result["response_status"] = response.status
            result["fan_rpm"] = decode_fan_response(response) if response.is_success else None
    except Exception as exc:
        result["query_success"] = False
        result["error"] = str(exc)
    return result


def find_working_device(vendor_id: int, product_id: int) -> tuple[DeviceCandidate, FanQueryResult]:
    candidates = sorted(enumerate_candidates(vendor_id, product_id), key=candidate_sort_key)
    if not candidates:
        raise RazerFanControlError(f"no HID devices found for {vendor_id:04X}:{product_id:04X}")

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            with RazerDevice(candidate) as device:
                fan = device.query_fan()
                power = device.query_power()
                cpu_boost = device.query_boost(BOOST_CPU)
                gpu_boost = device.query_boost(BOOST_GPU)
                if not all(item.is_success for item in (fan, power, cpu_boost, gpu_boost)):
                    continue
                model = product_model(candidate.product_id)
                WORKING_DEVICE_CACHE[(vendor_id, product_id)] = candidate
                return candidate, FanQueryResult(
                    fan_rpm=decode_fan_response(fan),
                    fan_raw=fan.args[2],
                    manual_fan=decode_manual_fan(power),
                    power_mode=decode_power_mode(power),
                    cpu_boost=decode_boost(cpu_boost),
                    gpu_boost=decode_boost(gpu_boost),
                    path=candidate.path_str,
                    product_id=f"0x{candidate.product_id:04X}",
                    model_name=str(model["name"]),
                )
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise RazerFanControlError(f"failed to find a working device: {last_error}") from last_error
    raise RazerFanControlError("found matching HID devices, but none responded to the Razer query protocol")


def command_probe(args: argparse.Namespace) -> int:
    data = [probe_candidate(candidate) for candidate in sorted(enumerate_candidates(args.vendor_id, args.product_id), key=candidate_sort_key)]
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        for item in data:
            print(json.dumps(item, indent=2))
    return 0


def command_query(args: argparse.Namespace) -> int:
    _, result = find_working_device(args.vendor_id, args.product_id)
    temps = read_thermal_sensors()
    payload = result.as_dict()
    payload.update(temps.as_dict())
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Model: {result.model_name} ({result.product_id})")
        print(f"Path: {result.path}")
        print(f"Fan RPM: {result.fan_rpm}")
        print(f"Manual Fan Mode: {result.manual_fan}")
        print(f"Power Mode: {result.power_mode}")
        print(f"CPU Boost: {result.cpu_boost}")
        print(f"GPU Boost: {result.gpu_boost}")
        print(f"CPU Temp C: {temps.cpu_temp_c}")
        print(f"GPU Temp C: {temps.gpu_temp_c}")
        print(f"GPU Hotspot C: {temps.gpu_hotspot_c}")
    return 0


def command_temps(args: argparse.Namespace) -> int:
    temps = read_thermal_sensors()
    if args.json:
        print(json.dumps(temps.as_dict(), indent=2))
    else:
        print(f"CPU Temp C: {temps.cpu_temp_c}")
        print(f"GPU Temp C: {temps.gpu_temp_c}")
        print(f"GPU Hotspot C: {temps.gpu_hotspot_c}")
    return 0


def command_set_fan(args: argparse.Namespace) -> int:
    candidate, current = find_working_device(args.vendor_id, args.product_id)
    target_rpm, target_raw = clamp_rpm(args.rpm, candidate.product_id, args.unsafe_unclamped)
    power_mode = resolve_power_mode(args.power_mode, current.power_mode)

    with RazerDevice(candidate) as device:
        fan_response = device.set_fan(args.fan_id, target_raw)
        if not fan_response.is_success:
            raise RazerFanControlError(f"fan write failed with status {fan_response.status}")

        power_response = device.set_power(power_mode, auto_fan=False)
        if not power_response.is_success:
            raise RazerFanControlError(f"power write failed with status {power_response.status}")

        verify_power = device.query_power()
        verify_fan = device.query_fan(args.fan_id)
        if (
            not verify_power.is_success
            or not verify_fan.is_success
            or not decode_manual_fan(verify_power)
            or decode_power_mode(verify_power) != power_mode
            or decode_fan_response(verify_fan) != target_rpm
        ):
            raise RazerFanControlError(f"manual fan verification failed for fan {args.fan_id} target {target_rpm} RPM")

        print(f"Set fan {args.fan_id} to {target_rpm} RPM in manual mode using power mode {power_mode}.")
    return 0


def command_set_fans(args: argparse.Namespace) -> int:
    candidate, current = find_working_device(args.vendor_id, args.product_id)
    power_mode = resolve_power_mode(args.power_mode, current.power_mode)

    with RazerDevice(candidate) as device:
        fan_values: list[tuple[int, int]] = []
        for fan_id, rpm in ((1, args.rpm), (2, args.rpm2 if args.rpm2 is not None else args.rpm)):
            target_rpm, target_raw = clamp_rpm(rpm, candidate.product_id, args.unsafe_unclamped)
            response = device.set_fan(fan_id, target_raw)
            if not response.is_success:
                raise RazerFanControlError(f"fan {fan_id} write failed with status {response.status}")
            fan_values.append((fan_id, target_rpm))

        power_response = device.set_power(power_mode, auto_fan=False)
        if not power_response.is_success:
            raise RazerFanControlError(f"power write failed with status {power_response.status}")

        verify_power = device.query_power()
        verify_fans = {fan_id: device.query_fan(fan_id) for fan_id, _rpm in fan_values}
        if (
            not verify_power.is_success
            or not decode_manual_fan(verify_power)
            or decode_power_mode(verify_power) != power_mode
        ):
            raise RazerFanControlError("manual fan verification failed after dual-fan write")
        for fan_id, rpm in fan_values:
            verify_fan = verify_fans[fan_id]
            if not verify_fan.is_success or decode_fan_response(verify_fan) != rpm:
                raise RazerFanControlError(f"manual fan verification failed for fan {fan_id} target {rpm} RPM")

    formatted = ", ".join(f"fan {fan_id}={rpm} RPM" for fan_id, rpm in fan_values)
    print(f"Set {formatted} in manual mode using power mode {power_mode}.")
    return 0


def command_auto(args: argparse.Namespace) -> int:
    candidate, current = find_working_device(args.vendor_id, args.product_id)
    power_mode = resolve_power_mode(args.power_mode, current.power_mode)
    with RazerDevice(candidate) as device:
        response = device.set_power(power_mode, auto_fan=True)
        if not response.is_success:
            raise RazerFanControlError(f"auto mode write failed with status {response.status}")
        verify_power = device.query_power()
        if (
            not verify_power.is_success
            or decode_manual_fan(verify_power)
            or decode_power_mode(verify_power) != power_mode
        ):
            raise RazerFanControlError("automatic mode verification failed")
    print(f"Returned fan control to automatic mode using power mode {power_mode}.")
    return 0


def command_set_cpu_boost(args: argparse.Namespace) -> int:
    mode = resolve_cpu_boost_mode(args.mode)
    result = set_boost_mode(args.vendor_id, args.product_id, BOOST_CPU, mode)
    print(f"Set CPU boost to mode {result}.")
    return 0


def command_set_gpu_boost(args: argparse.Namespace) -> int:
    mode = resolve_gpu_boost_mode(args.mode)
    result = set_boost_mode(args.vendor_id, args.product_id, BOOST_GPU, mode)
    print(f"Set GPU boost to mode {result}.")
    return 0


def command_set_keyboard_solid(args: argparse.Namespace) -> int:
    rgb = (args.red, args.green, args.blue)
    set_keyboard_solid(args.vendor_id, args.product_id, rgb, args.brightness_percent)
    print(f"Set keyboard to solid RGB({rgb[0]}, {rgb[1]}, {rgb[2]}) at {args.brightness_percent}% brightness.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Razer Blade fan controller for the 2021 Blade protocol.")
    parser.set_defaults(func=None)
    parser.add_argument("--vendor-id", type=lambda value: int(value, 0), default=RAZER_VENDOR_ID, help="USB vendor ID, default 0x1532")
    parser.add_argument("--product-id", type=lambda value: int(value, 0), default=DEFAULT_PRODUCT_ID, help="USB product ID, default 0x0270")

    subparsers = parser.add_subparsers(dest="command")

    probe = subparsers.add_parser("probe", help="list matching HID interfaces and test a read-only fan query")
    probe.add_argument("--json", action="store_true", help="print JSON")
    probe.set_defaults(func=command_probe)

    query = subparsers.add_parser("query", help="query the current fan and power state")
    query.add_argument("--json", action="store_true", help="print JSON")
    query.set_defaults(func=command_query)

    temps = subparsers.add_parser("temps", help="query CPU and GPU temperatures")
    temps.add_argument("--json", action="store_true", help="print JSON")
    temps.set_defaults(func=command_temps)

    set_fan = subparsers.add_parser("set-fan", help="set one fan and force manual mode")
    set_fan.add_argument("--fan-id", type=int, choices=(1, 2), required=True, help="fan id")
    set_fan.add_argument("--rpm", type=int, required=True, help="target RPM")
    set_fan.add_argument("--power-mode", help="balanced, custom, creator, gaming, or a numeric value")
    set_fan.add_argument("--unsafe-unclamped", action="store_true", help="skip model RPM clamping")
    set_fan.set_defaults(func=command_set_fan)

    set_fans = subparsers.add_parser("set-fans", help="set both fans and force manual mode")
    set_fans.add_argument("--rpm", type=int, required=True, help="target RPM for fan 1 and by default fan 2")
    set_fans.add_argument("--rpm2", type=int, help="optional target RPM for fan 2")
    set_fans.add_argument("--power-mode", help="balanced, custom, creator, gaming, or a numeric value")
    set_fans.add_argument("--unsafe-unclamped", action="store_true", help="skip model RPM clamping")
    set_fans.set_defaults(func=command_set_fans)

    auto = subparsers.add_parser("auto", help="return fans to automatic mode")
    auto.add_argument("--power-mode", help="balanced, custom, creator, gaming, or a numeric value")
    auto.set_defaults(func=command_auto)

    cpu_boost = subparsers.add_parser("set-cpu-boost", help="set the CPU boost mode")
    cpu_boost.add_argument("--mode", required=True, help="boost mode: on, off, or a raw numeric value")
    cpu_boost.set_defaults(func=command_set_cpu_boost)

    gpu_boost = subparsers.add_parser("set-gpu-boost", help="set the GPU boost mode")
    gpu_boost.add_argument("--mode", required=True, help="GPU mode: low, medium, high, balanced, on, off, or a raw numeric value")
    gpu_boost.set_defaults(func=command_set_gpu_boost)

    keyboard = subparsers.add_parser("set-keyboard-solid", help="set the keyboard to one solid RGB color")
    keyboard.add_argument("--red", type=int, required=True, help="red channel 0-255")
    keyboard.add_argument("--green", type=int, required=True, help="green channel 0-255")
    keyboard.add_argument("--blue", type=int, required=True, help="blue channel 0-255")
    keyboard.add_argument("--brightness-percent", type=int, default=100, help="keyboard brightness percent 0-100")
    keyboard.set_defaults(func=command_set_keyboard_solid)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.func is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except RazerFanControlError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
