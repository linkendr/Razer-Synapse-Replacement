#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LIGHTING_DLL = PROJECT_DIR / "vendor" / "razer-runtime" / "common" / "lighting_driver_v1.9.11.0.dll"
LIGHTING_LOG = Path(
    r"C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\lighting_driver.log"
)
DEFAULT_DEVICE = {
    "type": "device.register",
    "device_handle": 1,
    "device_identifier": {
        "deviceContainerId": "{00000000-0000-0000-FFFF-FFFFFFFFFFFF}",
        "claimInterface": 2,
        "productId": 624,
    },
    "write_function": "hid.sendFeatureReportInBatch",
    "category": "system",
    "protocol": "rzDevice25LedMatrix",
    "is_dock": False,
    "base_class_name": "rzDevice25",
    "batch_processing": True,
    "is_wdl_supported": False,
    "report_id": 0,
}


class ProbeError(RuntimeError):
    pass


class LightingDriver:
    def __init__(self, dll_path: Path) -> None:
        if not dll_path.exists():
            raise ProbeError(f"lighting driver DLL not found: {dll_path}")

        self._dll = ctypes.WinDLL(str(dll_path))
        self._dll.Startup.argtypes = []
        self._dll.Startup.restype = ctypes.c_int
        self._dll.Shutdown.argtypes = []
        self._dll.Shutdown.restype = ctypes.c_int
        self._dll.GetDllVersion.argtypes = []
        self._dll.GetDllVersion.restype = ctypes.c_void_p
        self._dll.Configure.argtypes = [ctypes.c_char_p]
        self._dll.Configure.restype = ctypes.c_void_p
        self._dll.HandleLightingCallback.argtypes = [ctypes.c_char_p]
        self._dll.HandleLightingCallback.restype = ctypes.c_bool
        self._dll.SetWriteFFICallback.argtypes = [ctypes.c_void_p]
        self._dll.SetWriteFFICallback.restype = ctypes.c_bool
        self._dll.HookLightingCallback.argtypes = [ctypes.c_char_p]
        self._dll.HookLightingCallback.restype = ctypes.c_void_p
        self._dll.FreeString.argtypes = [ctypes.c_void_p]
        self._dll.FreeString.restype = None
        self._started = False
        self._write_callback_refs: list[object] = []

    def startup(self) -> int:
        status = int(self._dll.Startup())
        self._started = True
        return status

    def shutdown(self) -> int:
        if not self._started:
            return 0
        status = int(self._dll.Shutdown())
        self._started = False
        return status

    def _decode_ptr(self, ptr: int | None) -> str | None:
        if not ptr:
            return None
        try:
            value = ctypes.string_at(ptr).decode("utf-8", errors="replace")
            return value
        finally:
            self._dll.FreeString(ctypes.c_void_p(ptr))

    def get_version(self) -> str | None:
        return self._decode_ptr(self._dll.GetDllVersion())

    def configure(self, payload: dict[str, object]) -> str | None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self._decode_ptr(self._dll.Configure(raw))

    def callback(self, payload: dict[str, object]) -> bool:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return bool(self._dll.HandleLightingCallback(raw))

    def callback_raw(self, payload: str) -> bool:
        return bool(self._dll.HandleLightingCallback(payload.encode("utf-8")))

    def set_write_ffi_callback(self, callback) -> bool:
        callback_type = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_char_p)
        wrapped = callback_type(callback)
        self._write_callback_refs.append(wrapped)
        return bool(self._dll.SetWriteFFICallback(wrapped))

    def hook_lighting_callback(self, payload: dict[str, object]) -> str | None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self._decode_ptr(self._dll.HookLightingCallback(raw))


def tail_log(lines: int) -> str:
    if not LIGHTING_LOG.exists():
        return ""
    content = LIGHTING_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def build_rgb_frame(red: int, green: int, blue: int) -> list[int]:
    if not all(0 <= channel <= 255 for channel in (red, green, blue)):
        raise ProbeError("RGB channels must be between 0 and 255")
    return [value for _row in range(6) for _col in range(16) for value in (red, green, blue)]


def command_version(args: argparse.Namespace) -> int:
    driver = LightingDriver(Path(args.dll))
    try:
        print(json.dumps({"startup": driver.startup(), "version": driver.get_version()}, indent=2))
        return 0
    finally:
        driver.shutdown()


def command_register(args: argparse.Namespace) -> int:
    driver = LightingDriver(Path(args.dll))
    try:
        result = {
            "startup": driver.startup(),
            "version": driver.get_version(),
            "protocol_use_base_class": driver.configure(
                {
                    "type": "protocol.use_base_class",
                    "name": [
                        "rzDevice25Linker",
                        "rzDevice25DualLinkMouse",
                        "rzDevice25DualLinkKeyboard",
                        "rzDevice25Oled",
                        "rzDevice25Krakoff",
                    ],
                }
            ),
            "device_register": driver.configure(DEFAULT_DEVICE | {"device_handle": args.device_handle}),
        }
        if args.mode is not None:
            result["mode_set"] = driver.configure(
                {
                    "type": "mode.set",
                    "device_handle": args.device_handle,
                    "mode": args.mode,
                    "param": args.param,
                }
            )
        print(json.dumps(result, indent=2))
        if args.tail_log:
            print("\n--- lighting_driver.log tail ---")
            print(tail_log(args.tail_log))
        return 0
    finally:
        driver.shutdown()


def command_frame(args: argparse.Namespace) -> int:
    driver = LightingDriver(Path(args.dll))
    frame = build_rgb_frame(args.red, args.green, args.blue)
    try:
        result = {
            "startup": driver.startup(),
            "version": driver.get_version(),
            "protocol_use_base_class": driver.configure(
                {
                    "type": "protocol.use_base_class",
                    "name": [
                        "rzDevice25Linker",
                        "rzDevice25DualLinkMouse",
                        "rzDevice25DualLinkKeyboard",
                        "rzDevice25Oled",
                        "rzDevice25Krakoff",
                    ],
                }
            ),
            "device_register": driver.configure(DEFAULT_DEVICE | {"device_handle": args.device_handle}),
        }
        if args.mode is not None:
            result["mode_set"] = driver.configure(
                {
                    "type": "mode.set",
                    "device_handle": args.device_handle,
                    "mode": args.mode,
                    "param": args.param,
                }
            )
        result["custom_rgb_event"] = driver.callback(
            {
                "event": "ledMatrix",
                "payload": {
                    "device_handle": args.device_handle,
                    "numRow": 6,
                    "numCol": 16,
                    "regionId": 0,
                    "profileId": 0,
                    "frame": frame,
                },
            }
        )
        print(json.dumps(result, indent=2))
        if args.tail_log:
            print("\n--- lighting_driver.log tail ---")
            print(tail_log(args.tail_log))
        return 0
    finally:
        driver.shutdown()


def command_unregister(args: argparse.Namespace) -> int:
    driver = LightingDriver(Path(args.dll))
    try:
        result = {
            "startup": driver.startup(),
            "device_unregister": driver.configure({"type": "device.unregister", "device_handle": args.device_handle}),
        }
        print(json.dumps(result, indent=2))
        if args.tail_log:
            print("\n--- lighting_driver.log tail ---")
            print(tail_log(args.tail_log))
        return 0
    finally:
        driver.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Razer lighting_driver.dll for Blade keyboard control.")
    parser.add_argument("--dll", default=str(LIGHTING_DLL), help="path to lighting_driver DLL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    version = subparsers.add_parser("version", help="print DLL version")
    version.set_defaults(func=command_version)

    register = subparsers.add_parser("register", help="register the Blade keyboard and optionally set mode")
    register.add_argument("--device-handle", type=int, default=1)
    register.add_argument("--mode", type=int)
    register.add_argument("--param", type=int, default=0)
    register.add_argument("--tail-log", type=int, default=40)
    register.set_defaults(func=command_register)

    frame = subparsers.add_parser("frame", help="register the Blade keyboard and send a custom RGB frame event")
    frame.add_argument("--device-handle", type=int, default=1)
    frame.add_argument("--mode", type=int, default=3)
    frame.add_argument("--param", type=int, default=0)
    frame.add_argument("--red", type=int, default=255)
    frame.add_argument("--green", type=int, default=255)
    frame.add_argument("--blue", type=int, default=255)
    frame.add_argument("--tail-log", type=int, default=60)
    frame.set_defaults(func=command_frame)

    unregister = subparsers.add_parser("unregister", help="unregister the Blade keyboard handle")
    unregister.add_argument("--device-handle", type=int, default=1)
    unregister.add_argument("--tail-log", type=int, default=20)
    unregister.set_defaults(func=command_unregister)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
