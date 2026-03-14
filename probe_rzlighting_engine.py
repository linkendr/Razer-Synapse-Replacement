#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ENGINE_DLL = PROJECT_DIR / "vendor" / "razer-runtime" / "common" / "RzLightingEngineApi_v4.0.54.0.dll"
DEFAULT_LED_CONFIG = PROJECT_DIR / "captures" / "lighting-engine" / "blade-14-2021-led-config.json"


class EngineError(RuntimeError):
    pass


class RzLightingEngine:
    def __init__(self, dll_path: Path) -> None:
        if not dll_path.exists():
            raise EngineError(f"engine DLL not found: {dll_path}")
        self._dll = ctypes.WinDLL(str(dll_path))
        self._dll.GetDLLVersion.argtypes = []
        self._dll.GetDLLVersion.restype = ctypes.c_void_p
        self._dll.RzLightingApi.argtypes = [ctypes.c_char_p]
        self._dll.RzLightingApi.restype = ctypes.c_void_p
        self._dll.RzLightingApiNoReturn.argtypes = [ctypes.c_char_p]
        self._dll.RzLightingApiNoReturn.restype = None
        self._dll.SetOperatingMode.argtypes = [ctypes.c_uint32]
        self._dll.SetOperatingMode.restype = None
        self._dll.SetNodeFFIEvent.argtypes = [ctypes.c_void_p]
        self._dll.SetNodeFFIEvent.restype = None
        self._dll.FreeMalloc.argtypes = [ctypes.c_void_p]
        self._dll.FreeMalloc.restype = None
        self._dll.DestroyLightingDevice.argtypes = [ctypes.c_uint32]
        self._dll.DestroyLightingDevice.restype = ctypes.c_int
        self._dll.DestroyLightingEngine.argtypes = [ctypes.c_uint32]
        self._dll.DestroyLightingEngine.restype = ctypes.c_int
        self._node_ffi_callback = None

    def _decode_ptr(self, ptr: int | None) -> str | None:
        if not ptr:
            return None
        try:
            return ctypes.string_at(ptr).decode("utf-8", errors="replace")
        finally:
            self._dll.FreeMalloc(ctypes.c_void_p(ptr))

    def get_version(self) -> str | None:
        return self._decode_ptr(self._dll.GetDLLVersion())

    def set_operating_mode(self, mode: int) -> None:
        self._dll.SetOperatingMode(mode)

    def set_node_ffi_event(self, callback) -> None:
        cb_type = ctypes.CFUNCTYPE(None, ctypes.c_char_p)
        self._node_ffi_callback = cb_type(callback)
        self._dll.SetNodeFFIEvent(ctypes.cast(self._node_ffi_callback, ctypes.c_void_p))

    def api(self, payload: dict[str, object]) -> dict[str, object]:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        result = self._decode_ptr(self._dll.RzLightingApi(raw))
        if not result:
            raise EngineError(f"RzLightingApi returned no data for payload: {payload}")
        return json.loads(result)

    def destroy_device(self, handle: int) -> int:
        return int(self._dll.DestroyLightingDevice(handle))

    def destroy_engine(self, handle: int) -> int:
        return int(self._dll.DestroyLightingEngine(handle))


def load_led_config(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "ledConfig" not in data:
        raise EngineError(f"expected ledConfig in {path}")
    return data


def command_version(args: argparse.Namespace) -> int:
    engine = RzLightingEngine(Path(args.dll))
    print(json.dumps({"version": engine.get_version()}, indent=2))
    return 0


def command_static(args: argparse.Namespace) -> int:
    engine = RzLightingEngine(Path(args.dll))
    blade = load_led_config(Path(args.led_config))
    led_config = blade["ledConfig"]
    position_row = int(blade.get("y", 118))
    position_col = int(blade.get("x", 135))
    color_value = int(args.color, 16) if isinstance(args.color, str) else int(args.color)

    engine.set_operating_mode(args.operating_mode)
    result: dict[str, object] = {
        "version": engine.get_version(),
        "operating_mode": args.operating_mode,
    }
    created_engine = None
    created_device = None
    try:
        create_engine = engine.api({"Action": 3, "fps": args.fps, "type": args.engine_type})
        created_engine = int(create_engine["engine_handle"])
        result["create_engine"] = create_engine

        create_device = engine.api({"Action": 1, "config": led_config})
        created_device = int(create_device["device_handle"])
        result["create_device"] = create_device

        result["add_device"] = engine.api(
            {
                "Action": 17,
                "engine_handle": created_engine,
                "device_handle": created_device,
                "region": 0,
                "orientation": 0,
            }
        )

        if args.set_position:
            result["set_position"] = engine.api(
                {
                    "Action": 19,
                    "engine_handle": created_engine,
                    "device_handle": created_device,
                    "region": 0,
                    "row": position_row,
                    "col": position_col,
                    "layer": 0,
                    "check_overlapping": False,
                }
            )

        result["add_effect"] = engine.api(
            {
                "Action": 33,
                "engine_handle": created_engine,
                "effect": 6,
                "EffectParam": {"Color": color_value},
            }
        )
        result["enable_engine"] = engine.api(
            {
                "Action": 49,
                "engine_handle": created_engine,
                "enable": 1,
                "device_handle": 0,
                "region": 0,
                "clearFrame": 1,
            }
        )

        if args.hold_seconds > 0:
            time.sleep(args.hold_seconds)

        print(json.dumps(result, indent=2))
        return 0
    finally:
        if args.cleanup and created_device is not None:
            result["destroy_device"] = engine.destroy_device(created_device)
        if args.cleanup and created_engine is not None:
            result["destroy_engine"] = engine.destroy_engine(created_engine)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe RzLightingEngineApi on the Razer Blade 14 2021.")
    parser.add_argument("--dll", default=str(ENGINE_DLL))
    subparsers = parser.add_subparsers(dest="command", required=True)

    version = subparsers.add_parser("version", help="print engine DLL version")
    version.set_defaults(func=command_version)

    static = subparsers.add_parser("static", help="apply a static color through RzLightingApi")
    static.add_argument("--led-config", default=str(DEFAULT_LED_CONFIG))
    static.add_argument("--color", default="0xFFFFFF", help="hex color as 0xRRGGBB")
    static.add_argument("--engine-type", default="Basic")
    static.add_argument("--fps", type=int, default=25)
    static.add_argument("--operating-mode", type=int, default=65538)
    static.add_argument("--hold-seconds", type=float, default=2.0)
    static.add_argument("--set-position", action="store_true")
    static.add_argument("--cleanup", action="store_true")
    static.set_defaults(func=command_static)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
