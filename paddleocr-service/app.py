# paddleocr-service/app.py
import os
import shutil
import tempfile

from fastapi import FastAPI, UploadFile

from ocr_engine import get_ocr_engine

app = FastAPI(title="PaddleOCR Service")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/ocr")
async def run_ocr(file: UploadFile):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = temp_file.name

    try:
        ocr = get_ocr_engine()
        result = ocr.ocr(temp_path, cls=True)

        detections = []
        for line in result:
            for detection in line:
                box = detection[0]
                text = detection[1][0]
                confidence = detection[1][1]
                print(f"BOX: {box} | TEXT: {text}")
                detections.append({"text": text, "confidence": confidence, "box": box})

        return {"detections": detections}
    finally:
        os.remove(temp_path)