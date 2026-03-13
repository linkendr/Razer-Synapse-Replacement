#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from probe_chroma_sdk_proxy import ChromaSdkProxy, PROXY_DLL, build_add_device_action, build_set_device_state_action, load_blade_payload
from probe_lighting_driver import DEFAULT_DEVICE, LIGHTING_DLL, LIGHTING_LOG, LightingDriver
from probe_rzlighting_engine import DEFAULT_LED_CONFIG, ENGINE_DLL, RzLightingEngine, load_led_config
from razer_fan_control import (
    DEFAULT_PRODUCT_ID,
    DEFAULT_TRANSACTION_ID,
    FEATURE_REPORT_LENGTH,
    NamedMutex,
    RAZER_VENDOR_ID,
    RAZER_WRITE_MUTEX,
    RazerDevice,
    RazerFanControlError,
    crc_packet,
    find_working_device,
    parse_response,
)


PROJECT_DIR = Path(__file__).resolve().parent

BOOTSTRAP_DEFAULT_BEFORE = [
    [0, 2, 0, 0, 0, 2, 0, 4] + ([0] * 80) + [6, 0],
    [0, 3, 0, 0, 0, 1, 3, 10, 4] + ([0] * 79) + [12, 0],
]

BOOTSTRAP_DEFAULT_AFTER = [
    [0, 11, 0, 0, 0, 2, 0, 4] + ([0] * 80) + [6, 0],
    [0, 12, 0, 0, 0, 1, 3, 10, 4] + ([0] * 79) + [12, 0],
]

# Captured from Synapse static-white ownership/takeover sequences. These packets are
# distinct from the shared row/apply traffic and appear to be the best current candidate
# for clearing the firmware-owned breathing/reactive profile before the engine frames land.
BOOTSTRAP_OWNERSHIP_STATIC = [
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x87, 0x00, 0x01] + ([0x00] * 78) + [0x88, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x87, 0x00, 0x02] + ([0x00] * 78) + [0x8B, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x01, 0x00, 0x01, 0x21, 0x00] + ([0x00] * 76) + [0x2F, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x01, 0x00, 0x02, 0x21, 0x00] + ([0x00] * 76) + [0x2C, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x04, 0x0D, 0x02, 0x00, 0x01, 0x00, 0x01] + ([0x00] * 76) + [0x0B, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x04, 0x0D, 0x82, 0x00, 0x02] + ([0x00] * 78) + [0x89, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x81, 0x00, 0x01] + ([0x00] * 78) + [0x8E, 0x00],
    [0x00, 0x1F, 0x00, 0x00, 0x00, 0x03, 0x0D, 0x81, 0x00, 0x02] + ([0x00] * 78) + [0x8D, 0x00],
]

STATIC_WHITE_HANDOFF_PREFIX = [
    [0x00, 0x0B, 0x00, 0x00, 0x00, 0x03, 0x03, 0x03, 0x01, 0x05, 0x00] + ([0x00] * 77) + [0x07, 0x00],
    [0x00, 0x0C, 0x00, 0x00, 0x00, 0x03, 0x03, 0x03, 0x01, 0x05, 0xFF] + ([0x00] * 77) + [0xF8, 0x00],
]

def packet_from_hex(value: str) -> list[int]:
    return list(bytes.fromhex(value))


STATIC_WHITE_ROWS = [
    packet_from_hex("000900000034030bff00000f000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff000000000000000000000000000000000000000000000000000000003300"),
    packet_from_hex("000a00000034030bff01000f000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff000000ffffff00000000000000000000000000000000000000000000000000000000cd00"),
    packet_from_hex("000b00000034030bff02000f000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff000000ffffff00000000000000000000000000000000000000000000000000000000ce00"),
    packet_from_hex("000c00000034030bff03000f000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff000000000000ffffff000000000000000000000000000000000000000000000000000000003000"),
    packet_from_hex("000d00000034030bff04000f000000ffffff000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff000000000000ffffff00000000000000000000000000000000000000000000000000000000c800"),
    packet_from_hex("000e00000034030bff05000f000000ffffffffffffffffff000000ffffff000000000000000000ffffff000000ffffffffffffffffffffffffffffff00000000000000000000000000000000000000000000000000000000c900"),
    packet_from_hex("000f00000002030a05000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000e00"),
]

STATIC_WHITE_HANDOFF_SEQUENCE = STATIC_WHITE_HANDOFF_PREFIX + BOOTSTRAP_OWNERSHIP_STATIC + STATIC_WHITE_ROWS


def tail_log(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


def configure_base_class(driver: LightingDriver) -> str | None:
    return driver.configure(
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
    )


def register_handle(driver: LightingDriver, handle: int, mode: int) -> dict[str, object]:
    payload = DEFAULT_DEVICE | {"device_handle": int(handle)}
    result: dict[str, object] = {
        "device_register": driver.configure(payload),
        "mode_set": driver.configure(
            {
                "type": "mode.set",
                "device_handle": int(handle),
                "mode": int(mode),
                "param": 0,
            }
        ),
    }
    return result


def unpack_driver_batch_packets(buffer: list[int], transaction_id: int = DEFAULT_TRANSACTION_ID) -> list[bytes]:
    packets: list[bytes] = []
    record_size = 95
    header_size = 12
    compact_packet_size = 83
    offset = 0
    while offset + header_size + compact_packet_size <= len(buffer):
        compact = buffer[offset + header_size: offset + record_size]
        if len(compact) != compact_packet_size:
            break
        packet = bytearray(90)
        packet[0] = 0x00
        packet[1] = transaction_id
        packet[2] = 0x00
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5:88] = bytes(compact)
        packet[88] = crc_packet(packet)
        packet[89] = 0x00
        packets.append(bytes([0x00]) + bytes(packet))
        offset += record_size
    return packets


def make_feature_report_from_raw90(raw90: list[int]) -> bytes:
    if len(raw90) != 90:
        raise ValueError(f"expected 90 bytes, got {len(raw90)}")
    return bytes([0x00]) + bytes(raw90)


def run_static(args: argparse.Namespace) -> int:
    proxy = ChromaSdkProxy(Path(args.proxy_dll))
    engine = RzLightingEngine(Path(args.engine_dll))
    driver = LightingDriver(Path(args.driver_dll))
    blade_proxy_payload = load_blade_payload(Path(args.led_config))
    blade_engine_payload = load_led_config(Path(args.led_config))
    led_config = blade_engine_payload["ledConfig"]

    color_value = int(args.color, 16) if isinstance(args.color, str) else int(args.color)
    position_row = int(blade_engine_payload.get("y", 118))
    position_col = int(blade_engine_payload.get("x", 135))

    result: dict[str, object] = {}
    created_engine = None
    created_device = None
    proxy_handle = None
    callback_events: list[dict[str, object]] = []
    write_events: list[dict[str, object]] = []
    hid_writer: RazerDevice | None = None

    def ensure_hid_writer() -> RazerDevice:
        nonlocal hid_writer
        if hid_writer is None:
            candidate, _query = find_working_device(RAZER_VENDOR_ID, DEFAULT_PRODUCT_ID)
            hid_writer = RazerDevice(candidate)
        return hid_writer

    def send_raw_packets(raw_packets: list[list[int]]) -> list[dict[str, object]]:
        device = ensure_hid_writer()
        results: list[dict[str, object]] = []
        with NamedMutex(RAZER_WRITE_MUTEX):
            for raw90 in raw_packets:
                packet = make_feature_report_from_raw90(raw90)
                sent = device._device.send_feature_report(packet)
                if sent < 0:
                    raise RazerFanControlError("bootstrap send_feature_report failed")
                if args.write_delay_seconds > 0:
                    time.sleep(args.write_delay_seconds)
                report = bytes(device._device.get_feature_report(0, FEATURE_REPORT_LENGTH))
                response = parse_response(report)
                results.append(
                    {
                        "status": response.status,
                        "command_class": response.command_class,
                        "command_id": response.command_id,
                    }
                )
        return results

    def maybe_rewrite_device_handle(text: str) -> str:
        if proxy_handle is None or not args.rewrite_callback_handle:
            return text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        changed = False
        body = payload.get("payload")
        if isinstance(body, dict) and "device_handle" in body:
            body["device_handle"] = int(proxy_handle)
            changed = True
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict) and "device_handle" in item:
                    item["device_handle"] = int(proxy_handle)
                    changed = True
        if not changed:
            return text
        return json.dumps(payload, separators=(",", ":"))

    def make_bridge(source: str):
        def _bridge(raw: bytes | None) -> None:
            text = ""
            if raw:
                text = raw.decode("utf-8", errors="replace")
            bridged_text = maybe_rewrite_device_handle(text)
            event_record: dict[str, object] = {"source": source, "payload": text}
            if bridged_text != text:
                event_record["rewritten_payload"] = bridged_text
            callback_events.append(event_record)
            if args.bridge_driver and text:
                try:
                    driver.callback_raw(bridged_text)
                except Exception as exc:
                    callback_events.append({"source": f"{source}-bridge-error", "payload": str(exc)})

        return _bridge

    def write_bridge(raw: bytes | None) -> bool:
        text = ""
        if raw:
            text = raw.decode("utf-8", errors="replace")
        record: dict[str, object] = {"payload": text}
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            record["error"] = f"json:{exc}"
            write_events.append(record)
            return False

        record["function_name"] = payload.get("function_name")
        packets_sent = 0
        responses: list[dict[str, object]] = []

        if args.write_bridge_hid and payload.get("function_name") == "hid.sendFeatureReportInBatch":
            try:
                device = ensure_hid_writer()
                packets = unpack_driver_batch_packets(list(payload.get("buffer") or []), transaction_id=args.hid_transaction_id)
                record["decoded_packets"] = len(packets)
                with NamedMutex(RAZER_WRITE_MUTEX):
                    for packet in packets:
                        sent = device._device.send_feature_report(packet)
                        if sent < 0:
                            raise RazerFanControlError("driver write callback send_feature_report failed")
                        if args.write_delay_seconds > 0:
                            time.sleep(args.write_delay_seconds)
                        report = bytes(device._device.get_feature_report(0, FEATURE_REPORT_LENGTH))
                        response = parse_response(report)
                        responses.append(
                            {
                                "status": response.status,
                                "command_class": response.command_class,
                                "command_id": response.command_id,
                            }
                        )
                        packets_sent += 1
                record["responses"] = responses
            except Exception as exc:
                record["error"] = str(exc)
                write_events.append(record)
                return False

        record["packets_sent"] = packets_sent
        write_events.append(record)
        return True

    try:
        # Load the proxy and engine DLLs into the current process first so lighting_driver
        # can hook its callbacks into both of them during Startup().
        proxy.set_node_ffi_event(make_bridge("proxy"))
        engine.set_node_ffi_event(make_bridge("engine"))
        result["proxy_init"] = proxy.init()
        proxy.set_operating_mode(args.proxy_operating_mode)
        result["proxy_operating_mode"] = args.proxy_operating_mode

        engine.set_operating_mode(args.engine_operating_mode)
        result["engine_version"] = engine.get_version()
        result["engine_operating_mode"] = args.engine_operating_mode

        result["driver_startup"] = driver.startup()
        result["driver_version"] = driver.get_version()
        result["driver_protocol_use_base_class"] = configure_base_class(driver)
        if args.set_write_callback:
            result["driver_set_write_ffi_callback"] = driver.set_write_ffi_callback(write_bridge)

        if args.pre_register_handle is not None:
            result["driver_pre_register"] = register_handle(driver, args.pre_register_handle, args.mode)
        if args.send_default_bootstrap:
            result["default_bootstrap_before"] = send_raw_packets(BOOTSTRAP_DEFAULT_BEFORE)

        result["proxy_action1"] = proxy.call("RzChromaSDKProxy", json.dumps({"Action": 1}))
        result["proxy_add_device"] = proxy.call("RzChromaSDKProxy", build_add_device_action(blade_proxy_payload))
        if isinstance(result["proxy_add_device"], dict):
            proxy_handle = result["proxy_add_device"].get("return", {}).get("device_handle")
        result["proxy_set_device_state"] = proxy.call(
            "RzChromaSDKProxy",
            build_set_device_state_action(True, int(proxy_handle) if proxy_handle is not None else None),
        )

        if proxy_handle is not None:
            result["driver_proxy_register"] = register_handle(driver, int(proxy_handle), args.mode)
        if args.send_default_bootstrap:
            result["default_bootstrap_after"] = send_raw_packets(BOOTSTRAP_DEFAULT_AFTER)
        if args.send_ownership_bootstrap:
            result["ownership_bootstrap_before_engine"] = send_raw_packets(BOOTSTRAP_OWNERSHIP_STATIC)
        if args.send_literal_static_handoff:
            result["literal_static_handoff_before_engine"] = send_raw_packets(STATIC_WHITE_HANDOFF_SEQUENCE)

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
                "effect": args.effect_id,
                "EffectParam": {"Color": color_value},
            }
        )
        if args.send_ownership_bootstrap:
            result["ownership_bootstrap_before_enable"] = send_raw_packets(BOOTSTRAP_OWNERSHIP_STATIC)
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
        if args.send_literal_static_handoff_after_enable:
            result["literal_static_handoff_after_enable"] = send_raw_packets(STATIC_WHITE_HANDOFF_SEQUENCE)

        if args.hold_seconds > 0:
            time.sleep(args.hold_seconds)

        result["callback_events"] = callback_events
        result["write_events"] = write_events
        result["lighting_driver_log_tail"] = tail_log(LIGHTING_LOG, args.tail_log)
        print(json.dumps(result, indent=2))
        return 0
    finally:
        if hid_writer is not None:
            hid_writer.close()
        if args.cleanup and created_device is not None:
            result["destroy_device"] = engine.destroy_device(created_device)
        if args.cleanup and created_engine is not None:
            result["destroy_engine"] = engine.destroy_engine(created_engine)
        result["driver_shutdown"] = driver.shutdown()
        result["proxy_uninit"] = proxy.uninit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe the Blade keyboard through lighting_driver + Chroma proxy + LightingEngine in one process.")
    parser.add_argument("--driver-dll", default=str(LIGHTING_DLL))
    parser.add_argument("--proxy-dll", default=str(PROXY_DLL))
    parser.add_argument("--engine-dll", default=str(ENGINE_DLL))
    parser.add_argument("--led-config", default=str(DEFAULT_LED_CONFIG))
    subparsers = parser.add_subparsers(dest="command", required=True)

    static = subparsers.add_parser("static", help="run the combined static-white stack")
    static.add_argument("--color", default="0xFFFFFF")
    static.add_argument("--mode", type=int, default=3)
    static.add_argument("--pre-register-handle", type=int, default=3)
    static.add_argument("--proxy-operating-mode", type=int, default=2)
    static.add_argument("--engine-operating-mode", type=int, default=65538)
    static.add_argument("--engine-type", default="Basic")
    static.add_argument("--effect-id", type=int, default=6)
    static.add_argument("--fps", type=int, default=25)
    static.add_argument("--hold-seconds", type=float, default=5.0)
    static.add_argument("--tail-log", type=int, default=50)
    static.add_argument("--set-position", action="store_true")
    static.add_argument("--bridge-driver", action="store_true")
    static.add_argument("--rewrite-callback-handle", action="store_true")
    static.add_argument("--set-write-callback", action="store_true")
    static.add_argument("--write-bridge-hid", action="store_true")
    static.add_argument("--send-default-bootstrap", action="store_true")
    static.add_argument("--send-ownership-bootstrap", action="store_true")
    static.add_argument("--send-literal-static-handoff", action="store_true")
    static.add_argument("--send-literal-static-handoff-after-enable", action="store_true")
    static.add_argument("--hid-transaction-id", type=lambda value: int(value, 0), default=DEFAULT_TRANSACTION_ID)
    static.add_argument("--write-delay-seconds", type=float, default=0.01)
    static.add_argument("--cleanup", action="store_true")
    static.set_defaults(func=run_static)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
