# Runs the web demo locally so documents never leave your machine:
#   docker build -t pii-redaction .
#   docker run --rm -p 8501:8501 pii-redaction
FROM python:3.13-slim

# lxml and spaCy ship manylinux wheels, so no build toolchain is needed.
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY streamlit_app.py ./

EXPOSE 8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HOME=/tmp

CMD ["streamlit", "run", "streamlit_app.py"]
