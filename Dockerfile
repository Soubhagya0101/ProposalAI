FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./
COPY public ./public
COPY README.md ./

RUN useradd --create-home --shell /usr/sbin/nologin proposalai \
  && chown -R proposalai:proposalai /app

USER proposalai

CMD ["python", "server.py"]
