FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.06.1

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache \
    bash \
    curl \
    jq \
    rsync \
    git \
    tzdata \
    nmap \
    nmap-scripts \
    iproute2 \
    iputils \
    bind-tools \
    avahi-tools \
    netcat-openbsd \
    arp-scan

RUN git clone --depth 1 https://github.com/MasterBals/Homeassistant.git /opt/homeassistant-source \
    && git -C /opt/homeassistant-source fetch --depth 1 origin 3c8dcf6de6b22715603d27be7c8efeae6b5d9867 \
    && git -C /opt/homeassistant-source checkout 3c8dcf6de6b22715603d27be7c8efeae6b5d9867

RUN pip3 install --no-cache-dir \
    "mcp==2.1.1" \
    "httpx>=0.28,<1" \
    "websockets>=15,<16" \
    "PyYAML>=6.0.2,<7" \
    "uvicorn>=0.35,<1"

COPY run.sh /run.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod a+x /run.sh /entrypoint.sh

LABEL \
  io.hass.name="ChatGPT Home Assistant Admin + Intelligence" \
  io.hass.description="Unified MCP administration, inventory and private LAN/VLAN discovery for Home Assistant" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/entrypoint.sh"]
