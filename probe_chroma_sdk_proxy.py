#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
PROXY_DLL = Path(r"C:\Program Files\Razer Chroma SDK\bin\RzChromaSDKProxy64.dll")
DEFAULT_LED_CONFIG = PROJECT_DIR / "captures" / "lighting-engine" / "blade-14-2021-led-config.json"


class ProxyError(RuntimeError):
    pass


class ChromaSdkProxy:
    def __init__(self, dll_path: Path) -> None:
        if not dll_path.exists():
            raise ProxyError(f"proxy DLL not found: {dll_path}")
        self._dll = ctypes.WinDLL(str(dll_path))
        self._dll.Init.argtypes = []
        self._dll.Init.restype = ctypes.c_int
        self._dll.UnInit.argtypes = []
        self._dll.UnInit.restype = ctypes.c_int
        self._dll.SetOperatingMode.argtypes = [ctypes.c_uint32]
        self._dll.SetOperatingMode.restype = None
        self._dll.FreeMalloc.argtypes = [ctypes.c_void_p]
        self._dll.FreeMalloc.restype = None
        self._node_ffi_callback = None
        for name in ("RzChromaSDKProxy",):
            func = getattr(self._dll, name)
            func.argtypes = [ctypes.c_char_p]
            func.restype = ctypes.c_void_p
        self._dll.SetNodeFFIEvent.argtypes = [ctypes.c_void_p]
        self._dll.SetNodeFFIEvent.restype = None

    def _decode_ptr(self, ptr: int | None) -> str | None:
        if not ptr:
            return None
        try:
            return ctypes.string_at(ptr).decode("utf-8", errors="replace")
        finally:
            self._dll.FreeMalloc(ctypes.c_void_p(ptr))

    def init(self) -> int:
        return int(self._dll.Init())

    def uninit(self) -> int:
        return int(self._dll.UnInit())

    def set_operating_mode(self, mode: int) -> None:
        self._dll.SetOperatingMode(mode)

    def set_node_ffi_event(self, callback) -> None:
        cb_type = ctypes.CFUNCTYPE(None, ctypes.c_char_p)
        self._node_ffi_callback = cb_type(callback)
        self._dll.SetNodeFFIEvent(ctypes.cast(self._node_ffi_callback, ctypes.c_void_p))

    def call(self, fn_name: str, payload: str) -> dict[str, object] | str | None:
        fn = getattr(self._dll, fn_name)
        result = self._decode_ptr(fn(payload.encode("utf-8")))
        if result is None:
            return None
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result


def load_blade_payload(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    led_config = data["ledConfig"]
    return {
        "pid": int(data["pid"]),
        "x": int(data["x"]),
        "y": int(data["y"]),
        "ledConfig": led_config,
        "category": data["category"],
        "productName": data["productName"],
        "containerId": data["containerId"],
    }


def build_add_device_action(payload: dict[str, object]) -> str:
    inner = {
        "func": "AddDevice",
        "param": payload,
    }
    return json.dumps({"Action": 5, "message": json.dumps(inner, separators=(",", ":"))}, separators=(",", ":"))


def build_set_device_state_action(enable: bool, device_handle: int | None = None) -> str:
    param: dict[str, object] = {"enable": int(enable)}
    if device_handle is not None:
        param["device_handle"] = int(device_handle)
    inner = {
        "func": "SetDeviceState",
        "param": param,
    }
    return json.dumps({"Action": 5, "message": json.dumps(inner, separators=(",", ":"))}, separators=(",", ":"))


def command_probe(args: argparse.Namespace) -> int:
    proxy = ChromaSdkProxy(Path(args.dll))
    blade = load_blade_payload(Path(args.led_config))
    result: dict[str, object] = {"init": proxy.init()}
    try:
        proxy.set_operating_mode(args.operating_mode)
        result["operating_mode"] = args.operating_mode
        result["rzchroma_action1"] = proxy.call("RzChromaSDKProxy", json.dumps({"Action": 1}))
        result["add_device"] = proxy.call("RzChromaSDKProxy", build_add_device_action(blade))
        device_handle = None
        if isinstance(result["add_device"], dict):
            device_handle = result["add_device"].get("return", {}).get("device_handle")
        result["set_device_state"] = proxy.call(
            "RzChromaSDKProxy",
            build_set_device_state_action(True, int(device_handle) if device_handle is not None else None),
        )
        print(json.dumps(result, indent=2))
        return 0
    finally:
        result["uninit"] = proxy.uninit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe RzChromaSDKProxy64.dll.")
    parser.add_argument("--dll", default=str(PROXY_DLL))
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="run baseline proxy actions for the Blade keyboard")
    probe.add_argument("--led-config", default=str(DEFAULT_LED_CONFIG))
    probe.add_argument("--operating-mode", type=int, default=2)
    probe.set_defaults(func=command_probe)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ProxyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
