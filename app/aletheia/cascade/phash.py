"""Perceptual image hashing (Phase 17, P17.4) — standard library first.

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.1 ("Image: exact
``sha256`` match, perceptual hashes (pHash/DCT + aHash/dHash ensemble),
avatar reuse detection").

The project installs no numeric package, so this module decodes a documented
subset itself and computes the DCT directly:

- **PNG** — non-interlaced, bit depths 1/2/4/8/16, color types 0 (gray),
  2 (RGB), 3 (palette), 4 (gray+alpha), 6 (RGBA); chunk CRCs are verified.
- **BMP** — uncompressed BI_RGB, 24-bit and 32-bit, either row order.
- **PPM/PGM** — P5/P6, maxval up to 65535 (16-bit samples keep their high
  byte).

JPEG is not in the stdlib subset. When Pillow happens to be importable (the
adapter sidecar images ship it for deepface-class work) it is used as a
fallback decoder; in the core test environment it is not required and an
unsupported format raises ``ImageLoadError`` with that reason instead of
guessing.

Hashes are 64-bit ints exposed as 16-char hex strings:

- ``ahash`` — average hash of the 8x8 box downsample (bit = pixel > mean).
- ``dhash`` — difference hash of the 9x8 downsample (bit = left > right).
- ``phash`` — DCT-II over the 32x32 downsample, median threshold of the
  8x8 low-frequency block (bit = coefficient > median).
- ``sha256`` — exact byte identity, carried alongside for the "identical
  media asset" evidence class.

All thresholds in this module are provisional v1 constants (reviewable), and
``is_match`` requires the pHash pair to agree *and* one of the cheaper hashes
to agree as well, so a single accidental hash collision cannot carry a match.
"""

from __future__ import annotations

import hashlib
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEFAULT_THRESHOLDS",
    "GrayscaleImage",
    "ImageHashes",
    "ImageLoadError",
    "average_hash",
    "difference_hash",
    "hash_ensemble",
    "hamming",
    "hamming_text",
    "is_match",
    "load_grayscale",
    "perceptual_hash",
]

# Provisional v1 thresholds (hamming bits, out of 64).
DEFAULT_THRESHOLDS: dict[str, int] = {"phash": 6, "ahash": 8, "dhash": 8}


class ImageLoadError(ValueError):
    """Raised when an image cannot be decoded by the supported subset."""


@dataclass(frozen=True)
class GrayscaleImage:
    """A decoded 8-bit grayscale image, row-major."""

    width: int
    height: int
    pixels: tuple[int, ...]

    def at(self, x: int, y: int) -> int:
        return self.pixels[y * self.width + x]


@dataclass(frozen=True)
class ImageHashes:
    """The hash ensemble for one image (hex strings, JSON friendly)."""

    sha256: str
    ahash: str
    dhash: str
    phash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "sha256": self.sha256,
            "ahash": self.ahash,
            "dhash": self.dhash,
            "phash": self.phash,
        }


# ---------------------------------------------------------------------------
# Decoders


def _png_error(detail: str) -> ImageLoadError:
    return ImageLoadError(f"PNG decode failed: {detail}")


def _decode_png(data: bytes) -> GrayscaleImage:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise _png_error("bad signature")
    offset = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    palette: list[tuple[int, int, int]] = []
    seen_ihdr = False
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack(">I4s", data[offset : offset + 8])
        offset += 8
        chunk = data[offset : offset + length]
        if len(chunk) != length:
            raise _png_error("truncated chunk")
        offset += length
        stored_crc = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        if zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF != stored_crc:
            raise _png_error(f"CRC mismatch in {chunk_type!r}")
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = (
                struct.unpack(">IIBBBBB", chunk)
            )
            seen_ihdr = True
            if compression != 0 or filter_method != 0:
                raise _png_error("unknown compression/filter method")
            if interlace != 0:
                raise _png_error("interlaced PNG is not supported by the stdlib subset")
        elif chunk_type == b"PLTE":
            palette = [
                (chunk[i], chunk[i + 1], chunk[i + 2]) for i in range(0, len(chunk) - 2, 3)
            ]
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break
    if not seen_ihdr:
        raise _png_error("missing IHDR")
    if not idat:
        raise _png_error("missing IDAT")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise _png_error(f"unsupported color type {color_type}")
    if color_type in (2, 4, 6) and bit_depth not in (8, 16):
        raise _png_error(f"color type {color_type} requires 8- or 16-bit depth")
    if color_type == 3 and bit_depth not in (1, 2, 4, 8):
        raise _png_error("palette PNG supports 1/2/4/8-bit depth")
    if color_type == 0 and bit_depth not in (1, 2, 4, 8, 16):
        raise _png_error("gray PNG supports 1/2/4/8/16-bit depth")
    stride = (width * channels * bit_depth + 7) // 8
    bpp = max(1, (channels * bit_depth + 7) // 8)
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise _png_error(f"zlib error: {exc}") from exc
    if len(raw) < (stride + 1) * height:
        raise _png_error("truncated image data")
    rows: list[bytearray] = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                up = previous[i]
                up_left = previous[i - bpp] if i >= bpp else 0
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                if pa <= pb and pa <= pc:
                    predictor = left
                elif pb <= pc:
                    predictor = up
                else:
                    predictor = up_left
                row[i] = (row[i] + predictor) & 0xFF
        else:
            raise _png_error(f"unknown filter type {filter_type}")
        rows.append(row)
        previous = row

    def sample(row: bytearray, index: int) -> int:
        """The index-th sample of a row at the PNG bit depth (high byte for 16-bit)."""
        if bit_depth == 16:
            return row[index * 2]
        if bit_depth == 8:
            return row[index]
        per_byte = 8 // bit_depth
        byte = row[index // per_byte]
        shift = (per_byte - 1 - (index % per_byte)) * bit_depth
        return (byte >> shift) & ((1 << bit_depth) - 1)

    pixels: list[int] = []
    for row in rows:
        if color_type == 0:
            for x in range(width):
                sample_value = sample(row, x)
                pixels.append(sample_value * 255 // ((1 << bit_depth) - 1) if bit_depth < 8 else sample_value)
        elif color_type == 3:
            for x in range(width):
                index = sample(row, x)
                if index >= len(palette):
                    raise _png_error("palette index out of range")
                red, green, blue = palette[index]
                pixels.append((299 * red + 587 * green + 114 * blue + 500) // 1000)
        elif color_type == 2:
            for x in range(width):
                if bit_depth == 16:
                    red, green, blue = row[6 * x], row[6 * x + 2], row[6 * x + 4]
                else:
                    red, green, blue = row[3 * x], row[3 * x + 1], row[3 * x + 2]
                pixels.append((299 * red + 587 * green + 114 * blue + 500) // 1000)
        else:  # color types 4 and 6: luminance, alpha ignored (unassociated pixels)
            step = channels * (2 if bit_depth == 16 else 1)
            for x in range(width):
                base = x * step
                if channels == 2:
                    pixels.append(row[base])
                else:
                    if bit_depth == 16:
                        red, green, blue = row[base], row[base + 2], row[base + 4]
                    else:
                        red, green, blue = row[base], row[base + 1], row[base + 2]
                    pixels.append((299 * red + 587 * green + 114 * blue + 500) // 1000)
    if len(pixels) != width * height:
        raise _png_error("pixel count mismatch")
    return GrayscaleImage(width=width, height=height, pixels=tuple(pixels))


def _decode_bmp(data: bytes) -> GrayscaleImage:
    if data[:2] != b"BM":
        raise ImageLoadError("BMP decode failed: bad signature")
    pixel_offset = struct.unpack("<I", data[10:14])[0]
    header_size = struct.unpack("<I", data[14:18])[0]
    if header_size < 40:
        raise ImageLoadError("BMP decode failed: unsupported DIB header")
    width, height = struct.unpack("<ii", data[18:26])
    planes, bpp = struct.unpack("<HH", data[26:30])
    compression = struct.unpack("<I", data[30:34])[0]
    if planes != 1 or compression != 0 or bpp not in (24, 32):
        raise ImageLoadError("BMP decode failed: only uncompressed 24/32-bit BI_RGB is supported")
    top_down = height < 0
    height = abs(height)
    stride = ((width * bpp + 31) // 32) * 4
    needed = pixel_offset + stride * height
    if width <= 0 or len(data) < needed:
        raise ImageLoadError("BMP decode failed: truncated pixel data")
    pixels: list[int] = []
    for row_index in range(height):
        source_row = row_index if top_down else height - 1 - row_index
        base = pixel_offset + source_row * stride
        for x in range(width):
            blue, green, red = data[base + 3 * x : base + 3 * x + 3]
            pixels.append((299 * red + 587 * green + 114 * blue + 500) // 1000)
    return GrayscaleImage(width=width, height=height, pixels=tuple(pixels))


def _decode_ppm(data: bytes) -> GrayscaleImage:
    magic = data[:2]
    if magic not in (b"P5", b"P6"):
        raise ImageLoadError("PPM decode failed: expected P5/P6")
    index = 2
    tokens: list[int] = []
    while len(tokens) < 3:
        while index < len(data) and data[index : index + 1].isspace():
            index += 1
        if data[index : index + 1] == b"#":
            while index < len(data) and data[index : index + 1] not in (b"\n", b"\r"):
                index += 1
            continue
        token = bytearray()
        while index < len(data) and not data[index : index + 1].isspace():
            token.append(data[index])
            index += 1
        if not token:
            raise ImageLoadError("PPM decode failed: truncated header")
        tokens.append(int(token))
    width, height, maxval = tokens
    if maxval < 1 or maxval > 65535 or width < 1 or height < 1:
        raise ImageLoadError("PPM decode failed: bad dimensions or maxval")
    index += 1  # single whitespace after maxval
    sample_bytes = 1 if maxval < 256 else 2
    channels = 1 if magic == b"P5" else 3
    needed = index + width * height * channels * sample_bytes
    if len(data) < needed:
        raise ImageLoadError("PPM decode failed: truncated pixel data")
    pixels: list[int] = []
    for position in range(width * height):
        base = index + position * channels * sample_bytes
        if channels == 1:
            gray = data[base] if sample_bytes == 1 else data[base]
            pixels.append(gray * 255 // maxval if maxval < 255 else gray)
        else:
            if sample_bytes == 1:
                red, green, blue = data[base], data[base + 1], data[base + 2]
            else:
                red, green, blue = data[base], data[base + 2], data[base + 4]
            pixels.append((299 * red + 587 * green + 114 * blue + 500) // 1000)
    return GrayscaleImage(width=width, height=height, pixels=tuple(pixels))


def _decode_with_pillow(data: bytes) -> GrayscaleImage | None:
    """Optional Pillow fallback (present in adapter sidecar images, not required)."""
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    import io

    try:
        with Image.open(io.BytesIO(data)) as image:
            gray = image.convert("L")
            width, height = gray.size
            pixels = tuple(gray.tobytes())
    except Exception as exc:  # Pillow raises many types; convert to ours with the reason
        raise ImageLoadError(f"Pillow could not decode the image: {exc}") from exc
    return GrayscaleImage(width=width, height=height, pixels=pixels)


def load_grayscale(source: str | Path | bytes) -> GrayscaleImage:
    """Decode an image to 8-bit grayscale.

    ``source`` may be a path or the raw bytes. Magic bytes pick the decoder;
    formats outside the stdlib subset fall back to Pillow when importable and
    otherwise raise :class:`ImageLoadError` naming the limitation.
    """
    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        data = bytes(source)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _decode_png(data)
    if data[:2] == b"BM":
        return _decode_bmp(data)
    if data[:2] in (b"P5", b"P6"):
        return _decode_ppm(data)
    fallback = _decode_with_pillow(data)
    if fallback is not None:
        return fallback
    raise ImageLoadError(
        "unsupported image format: the stdlib subset decodes PNG/BMP/PPM and PGM, "
        "and Pillow is not installed for the JPEG-class fallback"
    )


# ---------------------------------------------------------------------------
# Hashing


def _resize(image: GrayscaleImage, target_width: int, target_height: int) -> GrayscaleImage:
    """Area-average resize (nearest sample when upscaling)."""
    if image.width == target_width and image.height == target_height:
        return image
    pixels: list[int] = []
    for y in range(target_height):
        y0 = y * image.height // target_height
        y1 = max(y0 + 1, (y + 1) * image.height // target_height)
        for x in range(target_width):
            x0 = x * image.width // target_width
            x1 = max(x0 + 1, (x + 1) * image.width // target_width)
            total = 0
            count = 0
            for source_y in range(y0, y1):
                base = source_y * image.width
                for source_x in range(x0, x1):
                    total += image.pixels[base + source_x]
                    count += 1
            pixels.append(total // count)
    return GrayscaleImage(width=target_width, height=target_height, pixels=tuple(pixels))


def average_hash(image: GrayscaleImage, size: int = 8) -> int:
    """64-bit average hash: bit set when the pixel exceeds the mean."""
    small = _resize(image, size, size)
    mean = sum(small.pixels) / len(small.pixels)
    bits = 0
    for bit, value in enumerate(small.pixels):
        if value > mean:
            bits |= 1 << bit
    return bits


def difference_hash(image: GrayscaleImage, size: int = 8) -> int:
    """64-bit difference hash: bit set when the left pixel exceeds the right."""
    small = _resize(image, size + 1, size)
    bits = 0
    bit = 0
    for y in range(size):
        base = y * (size + 1)
        for x in range(size):
            if small.pixels[base + x] > small.pixels[base + x + 1]:
                bits |= 1 << bit
            bit += 1
    return bits


def _dct_low(series: list[float], count: int) -> list[float]:
    """First ``count`` DCT-II coefficients of ``series`` (scaling irrelevant here)."""
    length = len(series)
    out: list[float] = []
    for k in range(count):
        total = 0.0
        for n, value in enumerate(series):
            total += value * math.cos(math.pi * k * (2 * n + 1) / (2 * length))
        out.append(total)
    return out


def perceptual_hash(image: GrayscaleImage, size: int = 8, sample: int = 32) -> int:
    """64-bit pHash: DCT-II of the 32x32 downsample, median threshold of the 8x8 block."""
    small = _resize(image, sample, sample)
    rows: list[list[float]] = []
    for y in range(sample):
        base = y * sample
        rows.append(_dct_low([float(value) for value in small.pixels[base : base + sample]], size))
    coefficients: list[float] = []
    for column in range(size):
        transformed = _dct_low([row[column] for row in rows], size)
        coefficients.extend(transformed)
    ordered = sorted(coefficients)
    median = ordered[len(ordered) // 2]
    bits = 0
    for bit, value in enumerate(coefficients):
        if value > median:
            bits |= 1 << bit
    return bits


def hamming(left: int, right: int) -> int:
    """Hamming distance between two 64-bit integer hashes."""
    return (left ^ right).bit_count()


def hamming_text(left_hex: str, right_hex: str) -> int:
    """Hamming distance between two hex-encoded hashes of equal width."""
    if len(left_hex) != len(right_hex):
        raise ValueError("hashes must have the same width")
    return (int(left_hex, 16) ^ int(right_hex, 16)).bit_count()


def hash_ensemble(source: str | Path | bytes) -> ImageHashes:
    """Compute the sha256 + aHash/dHash/pHash ensemble for one image."""
    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        data = bytes(source)
    image = load_grayscale(data)
    return ImageHashes(
        sha256=hashlib.sha256(data).hexdigest(),
        ahash=f"{average_hash(image):016x}",
        dhash=f"{difference_hash(image):016x}",
        phash=f"{perceptual_hash(image):016x}",
    )


def is_match(
    left: ImageHashes,
    right: ImageHashes,
    thresholds: dict[str, int] | None = None,
) -> bool:
    """Provisional v1 match rule: pHash agrees AND one cheap hash agrees.

    Exact sha256 equality is byte-identical media and is reported separately
    by callers as STRONG ("identical media asset"); this function is the
    perceptual path.
    """
    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(thresholds)
    phash_close = hamming_text(left.phash, right.phash) <= limits["phash"]
    cheap_close = (
        hamming_text(left.ahash, right.ahash) <= limits["ahash"]
        or hamming_text(left.dhash, right.dhash) <= limits["dhash"]
    )
    return phash_close and cheap_close
