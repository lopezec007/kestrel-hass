# Hardware validation checklist

Items derived from the documentation, checked against two Kestrel DROP D3 units
(serials 3103865 and 3116707, firmware 1.61, hardware Rev 11A2, BLE profile
1.25) on 2026-10-17 through a Home Assistant 2026.10.1 host adapter.

Legend: [x] confirmed as documented, [!] differs from the documentation (code
adjusted), [ ] still open.

## Advertising / discovery
- [x] DROP advertises continuously; the payload is static, so HA only fires
      the advertisement callback once and the coordinator's timer fallback
      drives polling.
- [x] Scan response carries manufacturer id `0x00EA` with `[model_code][event]`
      (`2802ffff`) and the DROP service UUID.
- [!] The Complete Local Name is NUL-padded to 21 bytes (`"D3 - 3103865\0..."`).
- [x] Both units report model code 552 (DROP 3).

## GATT profile (DropProfile)
- [x] Status byte semantics match; absent measurements read `00 00 00`.
- [x] Value widths: 2 bytes for most, 3 bytes for heat stress index and density
      altitude (humidity ratio / moisture content are absent on the D3).
- [x] Station pressure raw × 0.1 gives hPa (856.4 hPa at a ~1500 m site).
      Barometric pressure is absent until a reference altitude is set.
- [!] Density altitude exponent is −1 (raw 19275 → 1927.5 m), not −2.
- [x] Battery Service 0x2A19 readable (100 % and 50 %).
- [!] Date/Time characteristic order is second, minute, hour, day, month,
      year (LE). It is a plain register: reads return the last written value
      and never advance. The running clock is behind LiNK Get/Set Time (14/15).
- [x] Settings characteristic reads real values; a write with ignore sentinels
      changed only the log interval (12 h → 10 min → 12 h) and left the rest.
- [x] Commands characteristic: blink LED accepted (write acknowledged).
- [x] Name characteristic readable.
- [!] Device Information characteristics are duplicated in the GATT table, so
      UUID lookups are ambiguous; resolved through the service tree
      ("Kestrel by NK", "Kestrel DROP 3", serial, "Rev 11A2", "1.61").

## LiNK / Mass Transfer
- [x] Mass Transfer service located and characteristics selected by property;
      a full Get Data Log transfer (5,937 records, 742 packets) completed.
- [x] 20-byte zero-padded chunking and per-packet acks behave as documented.
- [ ] `Get Data Snapshot` (not exercised yet; Get Data Log uses the same
      metadata/data flow and worked).
- [x] `Get Data Log` packet numbering and End of Data sequence parameter
      (last sequence 25593, record count matches command 2).
- [!] Log record timestamps use the DROP order (second first, year LE last),
      same as the clock characteristic.

## Behaviour
- [x] A poll takes about 6 s (2.3 s connect, 4.5 s reads). Effect on the
      phone app not checked.
- [ ] Does the LiNK clock keep time after Set Time (it read 2 h 15 min ahead
      before the LiNK-based sync was implemented)?
- [ ] Battery drain at the default 5-minute poll interval over a week.
