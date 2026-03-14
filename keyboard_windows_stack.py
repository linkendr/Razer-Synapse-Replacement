#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from probe_blade_keyboard_windows_stack import (
    BOOTSTRAP_DEFAULT_BEFORE,
    BOOTSTRAP_DEFAULT_AFTER,
    STATIC_WHITE_HANDOFF_SEQUENCE,
    configure_base_class,
    make_feature_report_from_raw90,
    register_handle,
    unpack_driver_batch_packets,
)
from probe_chroma_sdk_proxy import ChromaSdkProxy, PROXY_DLL, build_add_device_action, build_set_device_state_action, load_blade_payload
from probe_lighting_driver import LIGHTING_DLL, LightingDriver
from probe_rzlighting_engine import ENGINE_DLL, RzLightingEngine, load_led_config
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
)


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_LED_CONFIG = PROJECT_DIR / "captures" / "lighting-engine" / "blade-14-2021-led-config.json"


class KeyboardWindowsStackError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyboardWindowsStackConfig:
    color_value: int = 0xFFFFFF
    effect_id: int = 6
    fps: int = 25
    proxy_operating_mode: int = 2
    engine_operating_mode: int = 65538
    mode: int = 3
    write_delay_seconds: float = 0.01
    led_config_path: Path = DEFAULT_LED_CONFIG
    engine_dll: Path = ENGINE_DLL
    proxy_dll: Path = PROXY_DLL
    driver_dll: Path = LIGHTING_DLL


class KeyboardWindowsStackSession:
    def __init__(self, config: KeyboardWindowsStackConfig) -> None:
        self.config = config
        self.proxy = ChromaSdkProxy(config.proxy_dll)
        self.engine = RzLightingEngine(config.engine_dll)
        self.driver = LightingDriver(config.driver_dll)
        self.blade_proxy_payload = load_blade_payload(config.led_config_path)
        self.blade_engine_payload = load_led_config(config.led_config_path)
        self.led_config = self.blade_engine_payload["ledConfig"]
        self.position_row = int(self.blade_engine_payload.get("y", 118))
        self.position_col = int(self.blade_engine_payload.get("x", 135))
        self.proxy_handle: int | None = None
        self.created_engine: int | None = None
        self.created_device: int | None = None
        self.current_effect_handle: int | None = None
        self.hid_writer: RazerDevice | None = None
        self._started = False
        self._ownership_applied = False

    def _ensure_hid_writer(self) -> RazerDevice:
        if self.hid_writer is None:
            candidate, _query = find_working_device(RAZER_VENDOR_ID, DEFAULT_PRODUCT_ID)
            self.hid_writer = RazerDevice(candidate)
        return self.hid_writer

    def _send_raw_packets(self, raw_packets: list[list[int]]) -> None:
        device = self._ensure_hid_writer()
        with NamedMutex(RAZER_WRITE_MUTEX):
            for raw90 in raw_packets:
                packet = make_feature_report_from_raw90(raw90)
                sent = device._device.send_feature_report(packet)
                if sent < 0:
                    raise KeyboardWindowsStackError("send_feature_report failed")
                if self.config.write_delay_seconds > 0:
                    time.sleep(self.config.write_delay_seconds)
                device._device.get_feature_report(0, FEATURE_REPORT_LENGTH)

    def _maybe_rewrite_device_handle(self, text: str) -> str:
        if self.proxy_handle is None:
            return text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        body = payload.get("payload")
        changed = False
        if isinstance(body, dict) and "device_handle" in body:
            body["device_handle"] = int(self.proxy_handle)
            changed = True
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict) and "device_handle" in item:
                    item["device_handle"] = int(self.proxy_handle)
                    changed = True
        if not changed:
            return text
        return json.dumps(payload, separators=(",", ":"))

    def _bridge_driver(self, raw: bytes | None) -> None:
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace")
        self.driver.callback_raw(self._maybe_rewrite_device_handle(text))

    def _write_bridge(self, raw: bytes | None) -> bool:
        if not raw:
            return True
        text = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
        if payload.get("function_name") != "hid.sendFeatureReportInBatch":
            return True

        packets = unpack_driver_batch_packets(
            list(payload.get("buffer") or []),
            transaction_id=DEFAULT_TRANSACTION_ID,
        )
        device = self._ensure_hid_writer()
        with NamedMutex(RAZER_WRITE_MUTEX):
            for packet in packets:
                sent = device._device.send_feature_report(packet)
                if sent < 0:
                    raise RazerFanControlError("driver write callback send_feature_report failed")
                if self.config.write_delay_seconds > 0:
                    time.sleep(self.config.write_delay_seconds)
                device._device.get_feature_report(0, FEATURE_REPORT_LENGTH)
        return True

    def start(self) -> None:
        if self._started:
            return
        self.proxy.set_node_ffi_event(self._bridge_driver)
        self.engine.set_node_ffi_event(self._bridge_driver)
        self.proxy.init()
        self.proxy.set_operating_mode(self.config.proxy_operating_mode)
        self.engine.set_operating_mode(self.config.engine_operating_mode)
        self.driver.startup()
        configure_base_class(self.driver)
        self.driver.set_write_ffi_callback(self._write_bridge)
        register_handle(self.driver, 3, self.config.mode)
        self._send_raw_packets(BOOTSTRAP_DEFAULT_BEFORE)
        add_device = self.proxy.call("RzChromaSDKProxy", build_add_device_action(self.blade_proxy_payload))
        if not isinstance(add_device, dict):
            raise KeyboardWindowsStackError("AddDevice returned invalid payload")
        self.proxy_handle = int(add_device.get("return", {}).get("device_handle"))
        self.proxy.call("RzChromaSDKProxy", build_set_device_state_action(True, int(self.proxy_handle)))
        register_handle(self.driver, int(self.proxy_handle), self.config.mode)
        self._send_raw_packets(BOOTSTRAP_DEFAULT_AFTER)
        create_engine = self.engine.api({"Action": 3, "fps": self.config.fps, "type": "Basic"})
        self.created_engine = int(create_engine["engine_handle"])
        create_device = self.engine.api({"Action": 1, "config": self.led_config})
        self.created_device = int(create_device["device_handle"])
        self.engine.api(
            {
                "Action": 17,
                "engine_handle": self.created_engine,
                "device_handle": self.created_device,
                "region": 0,
                "orientation": 0,
            },
        )
        self.engine.api(
            {
                "Action": 19,
                "engine_handle": self.created_engine,
                "device_handle": self.created_device,
                "region": 0,
                "row": self.position_row,
                "col": self.position_col,
                "layer": 0,
                "check_overlapping": False,
            },
        )
        self._started = True
        self._ownership_applied = False

    def _push_engine_effect(self) -> None:
        # Synapse removes the prior region effect before attaching the next one.
        if self.current_effect_handle is not None:
            self.engine.api(
                {
                    "Action": 34,
                    "engine_handle": self.created_engine,
                    "effect_handle": self.current_effect_handle,
                }
            )
            self.current_effect_handle = None

        # Wake/clear the engine before pushing the replacement effect.
        self.engine.api(
            {
                "Action": 49,
                "engine_handle": self.created_engine,
                "enable": 1,
                "device_handle": 0,
                "region": 0,
                "clearFrame": 1,
            },
        )

        # The low-level API receives an integer Color. The string "0xffffff"
        # lives in Synapse's higher JS layer before it normalizes the payload.
        effect_param: dict[str, object] = {"Color": int(self.config.color_value)}
        add_effect = self.engine.api(
            {
                "Action": 33,
                "engine_handle": self.created_engine,
                "effect": self.config.effect_id,
                "EffectParam": effect_param,
            },
        )
        effect_handle = add_effect.get("effect_handle")
        if effect_handle is not None:
            self.current_effect_handle = int(effect_handle)
        self.engine.api(
            {
                "Action": 49,
                "engine_handle": self.created_engine,
                "enable": 1,
                "device_handle": 0,
                "region": 0,
                "clearFrame": 1,
            },
        )

    def apply_static_white(self) -> None:
        if not self._started:
            self.start()
        if not self._ownership_applied:
            self._send_raw_packets(STATIC_WHITE_HANDOFF_SEQUENCE)
            self._ownership_applied = True
        self._push_engine_effect()

    def close(self) -> None:
        if self.hid_writer is not None:
            self.hid_writer.close()
            self.hid_writer = None
        if self.created_device is not None:
            try:
                self.engine.destroy_device(self.created_device)
            except Exception:
                pass
            self.created_device = None
        self.current_effect_handle = None
        if self.created_engine is not None:
            try:
                self.engine.destroy_engine(self.created_engine)
            except Exception:
                pass
            self.created_engine = None
        try:
            self.driver.shutdown()
        except Exception:
            pass
        try:
            self.proxy.uninit()
        except Exception:
            pass
        self._started = False
