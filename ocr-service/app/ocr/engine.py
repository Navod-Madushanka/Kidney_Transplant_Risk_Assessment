import os

# Must run before importing paddleocr — same fix you already discovered.
os.environ["FLAGS_use_mkl"] = "0"
os.environ["FLAGS_use_onednn"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

from paddleocr import PaddleOCR

class OCREngine:
    """
    Thin wrapper around PaddleOCR, constructed exactly once and reused
    across every request. Loading model weights is expensive — we pay
    that cost a single time at startup, not per-request.
    """
    def __init__(self) -> None:
        self._ocr = PaddleOCR(use_textline_orientation=True, lang="en")

    def extract_raw(self, image_path: str) -> dict:
        """Runs the OCR pipeline on a saved image file, returns PaddleX's raw result dict."""
        result = self._ocr.predict(image_path)
        return result[0]  # predict() returns a list with one entry per page; we only handle single images for now