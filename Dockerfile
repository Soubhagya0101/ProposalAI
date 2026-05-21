FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY revenue_ops ./revenue_ops
COPY README.md ./

RUN useradd --create-home --shell /usr/sbin/nologin proposalai \
  && mkdir -p /app/revenue_ops_data \
  && chown -R proposalai:proposalai /app

USER proposalai

CMD ["python", "-m", "revenue_ops", "cloud-scheduler"]
