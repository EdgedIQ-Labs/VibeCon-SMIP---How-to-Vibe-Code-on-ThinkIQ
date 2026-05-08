# GEOPOINT encoding on SMIP

`geopointValue` on a `GEOPOINT`-typed attribute is exposed by the SMIP GraphQL
schema as a plain `String`, but the *contents* of that string are PostGIS
**EWKB hex** (Extended Well-Known Binary, hex-encoded) — not WKT, not GeoJSON.
Every read of a campus location attribute hands you back something like:

```
0101000020E6100000F4FDD478E9E65EC0A0F831E6AECF4240
```

This document describes the format so SDK consumers know what to do with it,
and so a future helper (`apiDemoMethods._parseGeoPointEwkbHex` and friends)
can land cleanly without re-deriving the spec.

## Why EWKB hex?

PostGIS stores geometries as binary internally. PostgreSQL's text rendering of
a `geometry` column is `ST_AsEWKB(geom)::text`, which produces uppercase hex
with the SRID embedded. PostGraphile passes this string scalar through to the
GraphQL layer untouched. The result is compact, lossless, round-trippable, and
self-describing — at the cost of needing client-side decoding.

We accept the format as-is because changing it would mean a server-side
PostGraphile plugin or a SMIP-wide schema migration, and EWKB is a perfectly
respectable interchange format. We just need to decode it.

## Byte layout (little-endian POINT, SRID 4326)

EWKB is a documented format. For our case (a 2D POINT in WGS84) the canonical
layout is 25 bytes / 50 hex characters:

| Offset | Size    | Meaning                         | Value for the canonical SMIP shape         |
| -----: | ------- | ------------------------------- | ------------------------------------------ |
|      0 | 1 byte  | byte order                      | `0x01` = little-endian (NDR)               |
|      1 | 4 bytes | uint32 LE — type code + flags   | `0x20000001` = POINT (`1`) \| SRID flag (`0x20000000`) |
|      5 | 4 bytes | uint32 LE — SRID                | `0x000010E6` = `4326` (WGS84)              |
|      9 | 8 bytes | float64 LE — X                  | longitude (degrees)                         |
|     17 | 8 bytes | float64 LE — Y                  | latitude (degrees)                          |

Two things worth flagging:

- **WKB and WKT both put X (longitude) before Y (latitude).** Humans usually
  say "lat, long" — the wire format is the opposite. Helper APIs should use
  named fields (`{ longitude, latitude }`) so callers can't positionally swap.
- **The hex prefix `0101000020E6100000` is canonical** for "little-endian
  POINT with SRID 4326". Any campus geopoint on this SMIP starts with these
  same 18 hex characters; only the trailing 32 hex (16 bytes = X then Y as
  float64) varies.

### Optional flags

EWKB's type-code field carries flags. We only handle the SRID flag in the
canonical case, but the spec also defines:

| Flag bit       | Meaning            | What it adds to the byte stream                |
| -------------- | ------------------ | ---------------------------------------------- |
| `0x20000000`   | SRID present       | 4 bytes for the SRID, between type and X       |
| `0x80000000`   | Z (altitude)       | 8 extra bytes after Y, for Z (e.g. metres ASL) |
| `0x40000000`   | M (measure)        | 8 extra bytes after Z (or Y if no Z)           |

A 3D POINT with altitude (`PointZ` with SRID) would have type code
`0x20000001 | 0x80000000 = 0xA0000001` and a 33-byte payload. SMIP campuses
have always been 2D so far, but a parser should at least *recognise* the Z
and M bits and skip past their bytes rather than mis-aligning the read.

## Worked example

Anthropic SF HQ at (37.7749 N, -122.4194 W) encodes as:

```
0101000020E6100000F4FDD478E9E65EC0A0F831E6AECF4240
```

Decoded byte-by-byte:

```
01                                        ← little-endian
01000020                                  ← uint32 LE = 0x20000001  → POINT + SRID flag
E6100000                                  ← uint32 LE = 0x000010E6  → SRID 4326
F4FDD478E9E65EC0                          ← float64 LE = -122.4194  → longitude (X)
A0F831E6AECF4240                          ← float64 LE =   37.7749  → latitude  (Y)
```

A round-trip parse → format on this string must be byte-identical to within
float64 precision.

## Helper sketch (not yet implemented)

Three private helpers on `apiDemoMethods`, naming convention matching
`_buildPatchLiteral`:

```js
// Strict: throws on null / empty / malformed input or non-POINT geometry.
apiDemoMethods._parseGeoPointEwkbHex(hex)
    → { latitude, longitude }

// Lenient: returns null on bad input. Useful for "render if set" UI logic.
apiDemoMethods._tryParseGeoPointEwkbHex(hex)
    → { latitude, longitude } | null

// Encode a { latitude, longitude } pair as PostGIS EWKB hex POINT with
// SRID 4326. Returns null when given null so callers can pipe straight
// into AttributePatch.geopointValue.
apiDemoMethods._formatGeoPointEwkbHex({ latitude, longitude })
    → "0101000020E6100000…"  (50 hex chars, uppercase)
```

Z and M dimensions, when present on read, are decoded but discarded. On
write the helper always emits 2D / SRID 4326 — if a future caller needs 3D
or a different SRID, the helper grows additional optional args rather than
forking into a parallel function.

## Python twin

The Python automation pipelines have a `GeoPoint` class
(`twTrackerWebApp.Model.GeoPoint`) with the same strict / lenient pair
(`parse_ewkb_hex` / `try_parse_ewkb_hex`), backed by the `geomet` package
for byte-level decoding. The JS port is intentionally framework-free so the
SDK stays drop-in for any SMIP project. Keep the two in lockstep — a change
to SMIP's geopoint encoding (e.g. a future PostGraphile plugin that exposes
GeoJSON instead) should land in both helpers in the same release.

## Status

**Not yet implemented.** This file documents the format ahead of the helper
landing so readers (and the LLM running the SDK) know the shape on the wire.
Until the JS helpers ship, callers reading a `GEOPOINT` attribute will get
the raw EWKB hex string back from `getObject` / `getTypes` and must decode
it themselves.
