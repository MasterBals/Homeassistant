FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.06.1

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache \
    bash \
    curl \
    jq \
    nmap \
    nmap-scripts \
    iproute2 \
    iputils \
    bind-tools \
    avahi-tools \
    netcat-openbsd \
    arp-scan \
    tzdata

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.name="HA Intelligence Bridge" \
  io.hass.description="MCP bridge for Home Assistant and local-network intelligence" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
