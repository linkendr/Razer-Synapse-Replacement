#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import razer_fan_control as rfc


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "keyboard-white-config.json"
CRASH_LOG_PATH = PROJECT_DIR / "keyboard-white-crash.log"
ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Global\RazerKeyboardWhiteDaemon"


class KeyboardWhiteError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyboardWhiteConfig:
    vendor_id: int
    product_id: int
    brightness_percent: int
    rgb: tuple[int, int, int]
    reapply_interval_seconds: float
    log_path: Path

    @classmethod
    def load(cls, path: Path) -> "KeyboardWhiteConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        rgb = tuple(int(value) for value in data.get("rgb", [255, 255, 255]))
        if len(rgb) != 3:
            raise KeyboardWhiteError("rgb must contain exactly three integers")

        log_path = Path(str(data.get("log_path", "keyboard-white.log")))
        if not log_path.is_absolute():
            log_path = path.parent / log_path

        return cls(
            vendor_id=int(data.get("vendor_id", rfc.RAZER_VENDOR_ID)),
            product_id=int(data.get("product_id", rfc.DEFAULT_PRODUCT_ID)),
            brightness_percent=int(data.get("brightness_percent", 100)),
            rgb=(rgb[0], rgb[1], rgb[2]),
            reapply_interval_seconds=float(data.get("reapply_interval_seconds", 60.0)),
            log_path=log_path,
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
            raise KeyboardWhiteError("failed to create daemon mutex")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            raise KeyboardWhiteError("keyboard white daemon is already running")

    def close(self) -> None:
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Keep the Blade keyboard solid white without Synapse.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to keyboard config JSON")
    parser.add_argument("--once", action="store_true", help="apply once and exit")
    parser.add_argument("--duration-seconds", type=float, help="optional max runtime for testing")
    parser.add_argument("--verbose", action="store_true", help="also print logs to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = KeyboardWhiteConfig.load(args.config)
    logger = FileLogger(config.log_path, args.verbose)
    guard = SingleInstanceGuard(MUTEX_NAME)
    deadline = time.time() + args.duration_seconds if args.duration_seconds is not None else None

    try:
        logger.log(
            f"Keyboard white daemon started rgb={config.rgb} brightness={config.brightness_percent}% "
            f"interval={config.reapply_interval_seconds}s."
        )
        while True:
            rfc.set_keyboard_solid(config.vendor_id, config.product_id, config.rgb, config.brightness_percent)
            logger.log(
                f"Applied keyboard RGB({config.rgb[0]}, {config.rgb[1]}, {config.rgb[2]}) "
                f"at {config.brightness_percent}% brightness."
            )

            if args.once:
                break
            if config.reapply_interval_seconds <= 0:
                break
            if deadline is not None and time.time() >= deadline:
                break
            time.sleep(config.reapply_interval_seconds)
    finally:
        guard.close()

    logger.log("Keyboard white daemon exiting.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] Unhandled exception\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
        raise
