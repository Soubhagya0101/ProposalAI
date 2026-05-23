FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

WORKDIR /app

COPY server.py ./
COPY public ./public
COPY README.md ./

CMD ["python", "server.py"]
