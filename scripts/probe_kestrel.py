#!/usr/bin/env python3
"""Developer utility: scan for Kestrel devices and dump a DROP over BLE.

This script talks to real hardware with ``bleak`` and the ``kestrel_link``
library.  It is not used by Home Assistant; it exists to validate the protocol
implementation against physical devices and to capture raw characteristic
values for new test fixtures.

Examples::

    python scripts/probe_kestrel.py scan
    python scripts/probe_kestrel.py dump AA:BB:CC:DD:EE:FF
    python scripts/probe_kestrel.py dump AA:BB:CC:DD:EE:FF --json
    python scripts/probe_kestrel.py link AA:BB:CC:DD:EE:FF   # LiNK snapshot + ids

Run it from the repository root so that ``custom_components`` is importable.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from custom_components.kestrel.kestrel_link.advertising import (
    parse_advertisement,
)
from custom_components.kestrel.kestrel_link.const import DeviceFamily
from custom_components.kestrel.kestrel_link.profiles import get_profile
from custom_components.kestrel.kestrel_link.types import DeviceState


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


async def cmd_scan(args: argparse.Namespace) -> int:
    """List Kestrel devices seen during a short scan."""
    seen: dict[str, tuple[BLEDevice, Any]] = {}

    def on_adv(device: BLEDevice, adv: Any) -> None:
        nk = parse_advertisement(
            adv.local_name, adv.manufacturer_data, adv.service_uuids
        )
        if nk is None and not args.all:
            return
        seen[device.address] = (device, nk)

    scanner = BleakScanner(on_adv)
    await scanner.start()
    await asyncio.sleep(args.seconds)
    await scanner.stop()
    if not seen:
        print("No Kestrel devices found.")
        return 1
    for address, (device, nk) in sorted(seen.items()):
        model = nk.model.name if nk and nk.model else "?"
        family = nk.family.value if nk else "-"
        event = nk.event_field if nk else None
        print(
            f"{address}  {device.name!s:<22} family={family:<12} model={model} event={event}"
        )
    return 0


async def cmd_dump(args: argparse.Namespace) -> int:
    """Connect to a device and dump its GATT profile and parsed state."""
    device = await BleakScanner.find_device_by_address(
        args.address, timeout=args.timeout
    )
    if device is None:
        print(f"Device {args.address} not found", file=sys.stderr)
        return 1
    family = DeviceFamily(args.family) if args.family else None
    async with BleakClient(device, timeout=args.timeout) as client:
        if args.raw or family is None:
            for service in client.services:
                print(f"[service] {service.uuid}  {service.description}")
                for char in service.characteristics:
                    value: str = ""
                    if "read" in char.properties:
                        try:
                            data = await client.read_gatt_char(char)
                            value = data.hex() + (
                                f"  ascii={bytes(data).decode('ascii', 'replace')!r}"
                                if all(32 <= b < 127 or b == 0 for b in data)
                                else ""
                            )
                        except Exception as exc:
                            value = f"<read failed: {exc}>"
                    print(f"    {char.uuid}  {','.join(char.properties):<30} {value}")
        if family is None:
            uuids = [s.uuid for s in client.services]
            from custom_components.kestrel.kestrel_link.models import (  # noqa: PLC0415
                family_from_service_uuids,
            )

            family = family_from_service_uuids(uuids)
            if family is None:
                print(
                    "Could not determine device family; pass --family", file=sys.stderr
                )
                return 1
        profile = get_profile(family)
        state = DeviceState(address=device.address, family=family, name=device.name)
        await profile.read_device_info(client, state)
        await profile.read_state(client, state)
    if args.json:
        print(json.dumps(_jsonable(state), indent=2, default=str))
    else:
        print(f"Device: {state.name}  family={state.family.value}  model={state.model}")
        print(f"Info: {state.info}")
        print(f"Battery: {state.battery_percent}%  device time: {state.device_time}")
        print(f"Settings: {state.settings}")
        for kind, m in state.measurements.items():
            flag = "present" if m.present else "absent "
            print(
                f"  {kind.value:<28} {flag} enabled={m.enabled!s:<5} valid={m.valid!s:<5} {m.value} {m.unit.value}  raw={m.raw.hex()}"
            )
    return 0


async def cmd_link(args: argparse.Namespace) -> int:
    """Exercise the LiNK Mass Transfer protocol: identity commands and a snapshot."""
    from custom_components.kestrel.kestrel_link.client import LinkClient  # noqa: PLC0415
    from custom_components.kestrel.kestrel_link.transport import LinkTransport  # noqa: PLC0415

    device = await BleakScanner.find_device_by_address(
        args.address, timeout=args.timeout
    )
    if device is None:
        print(f"Device {args.address} not found", file=sys.stderr)
        return 1
    async with BleakClient(device, timeout=args.timeout) as client:
        transport = LinkTransport(client)
        await transport.start()
        try:
            link = LinkClient(transport)
            print("serial:  ", await link.get_serial())
            print("model:   ", await link.get_model())
            print("firmware:", await link.get_firmware())
            print("hardware:", await link.get_hardware())
            print("name:    ", await link.get_name())
            print("time:    ", await link.get_time())
            print("battery: ", await link.get_battery())
            print("log count", await link.get_data_log_record_count())
            snapshot = await link.get_data_snapshot()
            print("snapshot:", snapshot)
            if args.log:
                result = await link.get_data_log(after=args.after)
                print(
                    f"log: {len(result.records)} records, last sequence {result.last_sequence}"
                )
                for rec in result.records[-5:]:
                    print("   ", rec)
        finally:
            await transport.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="scan for Kestrel devices")
    p_scan.add_argument("--seconds", type=float, default=8.0)
    p_scan.add_argument(
        "--all", action="store_true", help="show non-Kestrel devices too"
    )
    p_scan.set_defaults(func=cmd_scan)

    p_dump = sub.add_parser(
        "dump", help="dump a device's GATT profile and parsed state"
    )
    p_dump.add_argument("address")
    p_dump.add_argument("--family", choices=[f.value for f in DeviceFamily])
    p_dump.add_argument(
        "--raw", action="store_true", help="also list every characteristic"
    )
    p_dump.add_argument("--json", action="store_true")
    p_dump.add_argument("--timeout", type=float, default=20.0)
    p_dump.set_defaults(func=cmd_dump)

    p_link = sub.add_parser(
        "link", help="exercise the LiNK protocol over the Mass Transfer service"
    )
    p_link.add_argument("address")
    p_link.add_argument("--log", action="store_true", help="also download the data log")
    p_link.add_argument(
        "--after",
        type=int,
        default=None,
        help="only log records after this sequence number",
    )
    p_link.add_argument("--timeout", type=float, default=20.0)
    p_link.set_defaults(func=cmd_link)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
