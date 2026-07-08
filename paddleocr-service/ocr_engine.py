# paddleocr-service/ocr_engine.py
from paddleocr import PaddleOCR

_ocr_instance = None


def get_ocr_engine() -> PaddleOCR:
    global _ocr_instance

    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_gpu=False,
            show_log=False,
            det_limit_side_len=3000,
        )

    return _ocr_instance