#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_MAIN_LOG = Path(
    r"C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\main.log"
)
DEFAULT_ENGINE_LOG = Path(
    r"C:\Users\Administrator\AppData\Local\Razer\RazerAppEngine\User Data\Logs\lighting-engine.log"
)
PROJECT_DIR = Path(__file__).resolve().parent


class ExtractError(RuntimeError):
    pass


def parse_embedded_json(line: str) -> dict[str, object]:
    marker = "actionArgs: '"
    start = line.find(marker)
    if start == -1:
        raise ExtractError("actionArgs marker not found")
    start += len(marker)
    end = line.rfind("'")
    if end <= start:
        raise ExtractError("unterminated actionArgs payload")
    payload = line[start:end]
    return json.loads(payload)


def decode_nested_message(outer_payload: str) -> dict[str, object]:
    prefix = '{"Action":5,"message":"'
    suffix = '"}'
    if not (outer_payload.startswith(prefix) and outer_payload.endswith(suffix)):
        raise ExtractError("unexpected outer message format")
    message = outer_payload[len(prefix) : -len(suffix)]
    # Synapse double-escapes the nested JSON blob before logging it.
    decoded = message.encode("utf-8").decode("unicode_escape")
    decoded = decoded.encode("utf-8").decode("unicode_escape")
    return json.loads(decoded)


def find_blade_ledconfig(log_path: Path) -> dict[str, object]:
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "actionArgs: '" not in line or "Razer Blade 14" not in line:
            continue
        try:
            outer_payload = line[line.find("actionArgs: '") + len("actionArgs: '") : line.rfind("'")]
            message = decode_nested_message(outer_payload)
        except Exception:
            continue
        if message.get("func") != "AddDevice":
            continue
        param = message["param"]
        if int(param.get("pid", -1)) != 624:
            continue
        led_config = param["ledConfig"]
        return {
            "pid": param["pid"],
            "x": param.get("x"),
            "y": param.get("y"),
            "category": param.get("category"),
            "productName": param.get("productName"),
            "containerId": param.get("containerId"),
            "ledConfig": led_config,
        }
    raise ExtractError("Blade 14 ledConfig not found in main.log")


def find_static_sequence(log_path: Path) -> dict[str, object]:
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    sequence: dict[str, object] = {
        "static_effect_mapping": None,
        "sequence_lines": [],
    }
    for line in lines:
        if "convertUItoLighting()" in line and "uiEffectId:1" in line and '"effectId":6' in line:
            sequence["static_effect_mapping"] = line
            break

    for idx, line in enumerate(lines):
        if "createLightingDeviceEx(rzDevice25LedMatrix, 624" not in line:
            continue
        window = lines[idx : idx + 30]
        if not any('Action":33' in item and '"Color":16777215' in item for item in window):
            continue
        sequence["sequence_lines"] = window
        return sequence

    raise ExtractError("static white engine sequence not found in lighting-engine.log")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Blade 14 2021 Synapse lighting config from logs.")
    parser.add_argument("--main-log", default=str(DEFAULT_MAIN_LOG))
    parser.add_argument("--engine-log", default=str(DEFAULT_ENGINE_LOG))
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_DIR / "captures" / "lighting-engine"),
        help="directory to write extracted JSON/text artifacts into",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    blade = find_blade_ledconfig(Path(args.main_log))
    sequence = find_static_sequence(Path(args.engine_log))

    blade_path = output_dir / "blade-14-2021-led-config.json"
    sequence_json_path = output_dir / "blade-14-2021-static-sequence.json"
    sequence_text_path = output_dir / "blade-14-2021-static-sequence.txt"

    blade_path.write_text(json.dumps(blade, indent=2), encoding="utf-8")
    sequence_json_path.write_text(json.dumps(sequence, indent=2), encoding="utf-8")
    sequence_text_path.write_text("\n".join(sequence["sequence_lines"]), encoding="utf-8")

    print(
        json.dumps(
            {
                "blade_led_config": str(blade_path),
                "static_sequence_json": str(sequence_json_path),
                "static_sequence_text": str(sequence_text_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
