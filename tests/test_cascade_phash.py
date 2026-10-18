"""Tests for stdlib perceptual image hashing (P17.4).

The fixtures here are hand-built per the container specs (PNG bytes with
explicit filters and CRCs, BMP with a 40-byte DIB header, PPM/PGM headers),
so the decoder is exercised against byte layouts written from the specs, not
against its own encoder.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

import pytest

from aletheia.cascade.phash import (
    GrayscaleImage,
    ImageLoadError,
    average_hash,
    difference_hash,
    hash_ensemble,
    hamming,
    hamming_text,
    is_match,
    load_grayscale,
    perceptual_hash,
)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _png(
    width: int,
    height: int,
    rows: list[bytes],
    *,
    color_type: int = 0,
    bit_depth: int = 8,
    palette: bytes | None = None,
    interlace: int = 0,
) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, interlace)
    raw = b"".join(b"\x00" + row for row in rows)
    payload = _chunk(b"IHDR", ihdr)
    if palette is not None:
        payload += _chunk(b"PLTE", palette)
    payload += _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + payload


def _gray_png(pixels: list[list[int]]) -> bytes:
    return _png(len(pixels[0]), len(pixels), [bytes(row) for row in pixels])


def test_decode_png_gray_pixels_exact():
    data = _png(2, 2, [bytes([0, 255]), bytes([128, 64])])
    image = load_grayscale(data)
    assert (image.width, image.height) == (2, 2)
    assert image.pixels == (0, 255, 128, 64)
    assert image.at(1, 0) == 255


def test_decode_png_rgb_uses_integer_luminance():
    data = _png(1, 3, [bytes([255, 0, 0]), bytes([0, 255, 0]), bytes([0, 0, 255])], color_type=2)
    assert load_grayscale(data).pixels == (76, 150, 29)


def test_decode_png_palette_indexes_plte():
    data = _png(1, 2, [bytes([0]), bytes([1])], color_type=3, palette=bytes([255, 0, 0, 0, 255, 0]))
    assert load_grayscale(data).pixels == (76, 150)


def test_decode_png_gray_bit_depth_one():
    data = _png(2, 1, [bytes([0b10000000])], bit_depth=1)
    assert load_grayscale(data).pixels == (255, 0)


def test_decode_png_up_filter_reconstructs_rows():
    # Row 0 unfiltered [10, 20]; row 1 stored as delta [5, 5] with filter 2.
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 0, 0, 0, 0)
    raw = b"\x00" + bytes([10, 20]) + b"\x02" + bytes([5, 5])
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    assert load_grayscale(data).pixels == (10, 20, 15, 25)


def test_decode_png_rejects_crc_corruption():
    data = bytearray(_gray_png([[1, 2]]))
    index = data.index(b"IDAT")
    data[index + 4] ^= 0xFF
    with pytest.raises(ImageLoadError, match="CRC"):
        load_grayscale(bytes(data))


def test_decode_png_rejects_interlaced():
    data = _png(2, 2, [bytes([0, 1]), bytes([2, 3])], interlace=1)
    with pytest.raises(ImageLoadError, match="interlaced"):
        load_grayscale(data)


def _bmp_2x2() -> bytes:
    width = height = 2
    bpp = 24
    stride = ((width * bpp + 31) // 32) * 4
    pixels = bytearray()
    pixels += bytes([255, 0, 0, 255, 255, 255, 0, 0])  # bottom row: blue, white
    pixels += bytes([0, 0, 255, 0, 255, 0, 0, 0])  # top row: red, green
    header = b"BM" + struct.pack("<IHHI", 14 + 40 + len(pixels), 0, 0, 14 + 40)
    dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, bpp, 0, len(pixels), 0, 0, 0, 0)
    return header + dib + bytes(pixels)


def test_decode_bmp_bottom_up_rows():
    image = load_grayscale(_bmp_2x2())
    assert (image.width, image.height) == (2, 2)
    assert image.pixels == (76, 150, 29, 255)


def test_decode_ppm_p6_and_pgm_p5_16bit():
    ppm = b"P6\n2 1\n255\n" + bytes([255, 0, 0, 0, 255, 0])
    assert load_grayscale(ppm).pixels == (76, 150)
    pgm = b"P5\n1 1\n65535\n" + b"\x80\x00"
    assert load_grayscale(pgm).pixels == (128,)


def test_unsupported_format_raises_with_reason(tmp_path):
    junk = b"\xff\xd8\xff\xe0not-a-real-jpeg"
    with pytest.raises(ImageLoadError):
        load_grayscale(junk)
    path = tmp_path / "avatar.jpg"
    path.write_bytes(junk)
    with pytest.raises(ImageLoadError):
        load_grayscale(path)


def _gradient(width: int = 16, height: int = 16, offset: int = 0) -> GrayscaleImage:
    pixels = tuple(
        min(255, x * 16 + offset) for _ in range(height) for x in range(width)
    )
    return GrayscaleImage(width=width, height=height, pixels=pixels)


def test_hashes_are_deterministic_and_brightness_stable():
    dark = _gradient()
    bright = _gradient(offset=10)
    assert hamming(average_hash(dark), average_hash(dark)) == 0
    assert hamming(average_hash(dark), average_hash(bright)) == 0
    assert hamming(difference_hash(dark), difference_hash(dark)) == 0


def test_difference_hash_flips_on_inverted_gradient():
    left = _gradient()
    inverted = GrayscaleImage(
        width=left.width,
        height=left.height,
        pixels=tuple(255 - value for value in left.pixels),
    )
    assert hamming(difference_hash(left), difference_hash(inverted)) == 64


def test_perceptual_hash_distinguishes_inverted_patterns():
    def checkerboard(invert: bool) -> GrayscaleImage:
        pixels = tuple(
            255 if ((x + y) % 2 == 0) != invert else 0 for y in range(16) for x in range(16)
        )
        return GrayscaleImage(width=16, height=16, pixels=pixels)

    plain = checkerboard(False)
    inverse = checkerboard(True)
    assert hamming(perceptual_hash(plain), perceptual_hash(plain)) == 0
    assert hamming(perceptual_hash(plain), perceptual_hash(inverse)) > 20


def test_hash_ensemble_sha256_and_json_shape(tmp_path):
    data = _gray_png([[0, 255], [128, 64]])
    path = tmp_path / "thumb.png"
    path.write_bytes(data)
    hashes = hash_ensemble(path)
    assert hashes.sha256 == hashlib.sha256(data).hexdigest()
    assert hashes == hash_ensemble(data)
    payload = hashes.to_dict()
    assert set(payload) == {"sha256", "ahash", "dhash", "phash"}
    assert all(len(payload[key]) == 16 for key in ("ahash", "dhash", "phash"))


def test_is_match_identical_and_different():
    gradient_png = _gray_png([list(range(16)) for _ in range(16)])
    identical = hash_ensemble(gradient_png)
    assert is_match(identical, identical) is True
    inverted_png = _gray_png([[255 - value for value in range(16)] for _ in range(16)])
    different = hash_ensemble(inverted_png)
    assert is_match(identical, different) is False


def test_hamming_text_requires_equal_widths():
    assert hamming_text("0" * 16, "0" * 16) == 0
    with pytest.raises(ValueError):
        hamming_text("0" * 16, "0" * 8)
