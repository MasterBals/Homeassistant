FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.06.1

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache bash curl jq rsync git tzdata

RUN git clone --depth 1 https://github.com/MasterBals/Homeassistant.git /opt/homeassistant-source

RUN pip3 install --no-cache-dir \
    "mcp==2.1.1" \
    "httpx>=0.28,<1" \
    "websockets>=15,<16" \
    "PyYAML>=6.0.2,<7" \
    "uvicorn>=0.35,<1"

COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
