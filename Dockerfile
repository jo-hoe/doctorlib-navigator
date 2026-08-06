FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install --upgrade pip && \
    pip install -r requirements.txt

RUN adduser --uid 10001 --disabled-password --gecos "" appuser

COPY app/ ./app/
COPY main.py .

USER appuser

CMD ["python", "main.py"]
