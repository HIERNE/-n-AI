"""Inference-only fallback for PaddleOCR when native lmdb is blocked on Windows.

PaddleOCR imports lmdb while loading its dataset modules, but the invoice
inference path does not use LMDB. Dataset access remains unavailable here.
"""


def open(*args, **kwargs):
    raise RuntimeError(
        "LMDB dataset access is unavailable in this inference environment."
    )
