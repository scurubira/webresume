FROM python:3.12-slim

ENV HOST=0.0.0.0 \
    PORT=7003 \
    CV_DATA_DIR=/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir /data \
    && chown app:app /data

COPY --chown=app:app server.py index.html app.js styles.css ./

USER app

EXPOSE 7003

CMD ["python3", "server.py"]
