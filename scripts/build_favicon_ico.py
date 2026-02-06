#!/usr/bin/env python3
"""
从多张 PNG 图标生成一个包含多尺寸的 favicon.ico（ICO 内嵌 PNG，不依赖 Pillow/ImageMagick）。

设计目标：
- 不引入第三方依赖（仅标准库）
- 输入为方形 PNG（例如 48/96/192）
- 输出为一个 .ico，浏览器可按需选择最合适尺寸

用法示例：
  python3 scripts/build_favicon_ico.py \
    --out /tmp/favicon.ico \
    /path/to/48.png /path/to/96.png /path/to/192.png
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _read_png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("not a PNG file (signature mismatch)")

    # PNG chunks: length(4) type(4) data(length) crc(4)
    offset = 8
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + length
        if chunk_data_end + 4 > len(data):
            break
        if ctype == b"IHDR":
            if length < 8:
                raise ValueError("invalid IHDR chunk")
            width, height = struct.unpack(">II", data[chunk_data_start : chunk_data_start + 8])
            return int(width), int(height)
        offset = chunk_data_end + 4

    raise ValueError("IHDR chunk not found")


def _width_height_byte(v: int) -> int:
    # ICO uses 1 byte for width/height; 0 means 256.
    if v == 256:
        return 0
    if not (1 <= v <= 255):
        raise ValueError(f"icon size out of range for ICO: {v}")
    return v


def build_ico_from_png_bytes(png_images: list[bytes]) -> bytes:
    if not png_images:
        raise ValueError("no images provided")

    images_with_size: list[tuple[int, int, bytes]] = []
    for b in png_images:
        w, h = _read_png_size(b)
        if w != h:
            raise ValueError(f"PNG must be square (got {w}x{h})")
        images_with_size.append((w, h, b))

    # Sort by size to make output deterministic and friendly to icon pickers.
    images_with_size.sort(key=lambda x: x[0])

    count = len(images_with_size)
    header = struct.pack("<HHH", 0, 1, count)
    entries: list[bytes] = []
    blobs: list[bytes] = []

    # ICONDIR (6 bytes) + N * ICONDIRENTRY (16 bytes each)
    offset = 6 + 16 * count
    for w, h, blob in images_with_size:
        width = _width_height_byte(w)
        height = _width_height_byte(h)
        bytes_in_res = len(blob)

        # For PNG payloads, many generators set planes/bitcount to 0. We set 1/32.
        entry = struct.pack(
            "<BBBBHHII",
            width,
            height,
            0,  # color count
            0,  # reserved
            1,  # planes
            32,  # bit count
            bytes_in_res,
            offset,
        )
        entries.append(entry)
        blobs.append(blob)
        offset += bytes_in_res

    return header + b"".join(entries) + b"".join(blobs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build multi-size favicon.ico from PNG inputs.")
    parser.add_argument("--out", required=True, help="Output .ico path")
    parser.add_argument("inputs", nargs="+", help="Input PNG files (square, e.g. 48/96/192)")
    args = parser.parse_args()

    out_path = Path(args.out)
    inputs = [Path(p) for p in args.inputs]
    png_bytes = [p.read_bytes() for p in inputs]
    ico = build_ico_from_png_bytes(png_bytes)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(ico)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
