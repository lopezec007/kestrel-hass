# Hardware validation checklist

Items derived from the documentation that need confirming on real devices.
Tick them off with `scripts/probe_kestrel.py` output attached to the PR.

## Advertising / discovery
- [ ] DROP advertises continuously (not only after a button press) so the
      coordinator's advertisement-driven polling and availability work.
- [ ] Scan response carries manufacturer id `0x00EA` with `[model_code][event]`
      and the DROP service UUID `12630000-cc25-497d-9854-9b6c02c77054`.
- [ ] Observed model codes for the two test units (expected 550–555).

## GATT profile (DropProfile)
- [ ] Status byte semantics (bit0 present, bit1 enabled, bit2 valid) match.
- [ ] Measurement value widths: 2 bytes for most, 3 bytes for heat stress
      index, density altitude, humidity ratio and moisture content.
- [ ] Station/barometric pressure scale: raw × 0.1 gives hPa (doc labels the
      unit "Bar" but the resolution table says 0.1 hPa).
- [ ] Density altitude exponent: doc says −2 for the DROP (−1 on the K5).
- [ ] Battery Service 0x2A19 readable.
- [ ] Date/Time characteristic byte order (SIG little-endian year).
- [ ] Settings characteristic: reading returns real values, and a write with
      ignore sentinels only changes the intended field.
- [ ] Commands characteristic: blink LED works; verify the device does **not**
      react to zero bytes.
- [ ] Name characteristic is readable and NUL-padded.

## LiNK / Mass Transfer
- [ ] Mass Transfer characteristic UUIDs: `85920001`/`85920002` vs the swapped
      `85920100`/`85920200` reading of the NK note (transport picks by property).
- [ ] 20-byte zero-padded chunking and indication acks behave as documented.
- [ ] `Get Data Snapshot` returns Metadata Start + Data + End of Data.
- [ ] `Get Data Log` packet numbering and End of Data sequence parameter.
- [ ] BT Date Time year byte order in log records.

## Behaviour
- [ ] Connection time per poll and effect on the phone app (the DROP accepts a
      single central at a time).
- [ ] Battery drain at the default 5-minute poll interval over a week.
