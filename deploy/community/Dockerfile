FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 JWS_DATA_DIR=/data/ledger JWS_ENDPOINT_FILE=/data/endpoint
WORKDIR /opt/jws
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock . \
    && useradd --uid 10001 --create-home jws \
    && mkdir /data && chown 10001:10001 /data && chmod 700 /data
USER 10001:10001
WORKDIR /home/jws
CMD ["jarvis-home-bridge"]
