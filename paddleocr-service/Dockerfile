# paddleocr-service/Dockerfile
FROM paddlepaddle/paddle:3.0.0

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "numpy<2" && \
    pip install --no-cache-dir paddleocr==2.9.1 && \
    pip uninstall -y opencv-python opencv-contrib-python && \
    pip install --no-cache-dir --force-reinstall opencv-python-headless && \
    pip install --no-cache-dir --force-reinstall "numpy<2"

RUN pip install --no-cache-dir "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "python-multipart>=0.0.9"

COPY ocr_engine.py .
COPY app.py .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]