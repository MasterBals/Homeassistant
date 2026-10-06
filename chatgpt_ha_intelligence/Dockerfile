FROM ghcr.io/openai/tunnel-client:v0.0.14@sha256:41d7c85dab37797a3eaa17c41b94a7206dd0bc186fd361034c9ec3863596ff6c AS openai_tunnel

FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.06.1

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache \
    bash \
    ca-certificates \
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
    arp-scan \
    ffmpeg \
    bluez \
    hostapd \
    dnsmasq \
    iw \
    usbutils \
    libusb \
    tcpdump

RUN echo "Bundling Homeassistant source for ${BUILD_VERSION}" \
    && git clone --depth 1 --branch main https://github.com/MasterBals/Homeassistant.git /opt/homeassistant-source

RUN pip3 install --no-cache-dir \
    "mcp==2.1.1" \
    "httpx>=0.28,<1" \
    "websockets>=15,<16" \
    "PyYAML>=6.0.2,<7" \
    "uvicorn>=0.35,<1" \
    "pyusb>=1.3,<2"

WORKDIR /app

# The official OpenAI v0.0.14 image ships these two runtime binaries.
COPY --from=openai_tunnel /usr/bin/tunnel-client /usr/bin/tunnel-client
COPY --from=openai_tunnel /usr/bin/cloudflared /usr/bin/cloudflared

COPY unified_mcp.py /app/unified_mcp.py
COPY state_store.py /app/state_store.py
COPY migrate_second_brain.py /app/migrate_second_brain.py
COPY bootstrap_second_brain.py /app/bootstrap_second_brain.py
COPY audit_ui.py /app/audit_ui.py
COPY arlo_voice_listener.py /app/arlo_voice_listener.py
COPY yealink_usb_probe.py /app/yealink_usb_probe.py
COPY OPENAI_TUNNEL_CLIENT_LICENSE.txt /licenses/openai-tunnel-client-LICENSE
COPY OPENAI_TUNNEL_CLIENT_NOTICE.txt /licenses/openai-tunnel-client-NOTICE
COPY run_v2.sh /run.sh
COPY entrypoint.sh /entrypoint.sh

# Keep the public diagnostic version aligned with the add-on release without
# duplicating build-time version constants in multiple Python source files.
RUN sed -i 's/VERSION = "2.2.0"/VERSION = "2.5.0"/' /app/unified_mcp.py \
    && chmod a+x /run.sh /entrypoint.sh /usr/bin/tunnel-client /usr/bin/cloudflared \
    && ln -sf /usr/bin/tunnel-client /usr/local/bin/tunnel-client-runtime

LABEL \
  io.hass.name="ChatGPT Home Assistant Admin + Intelligence" \
  io.hass.description="Unified Home Assistant MCP administration, intelligence, revisioned persistent knowledge, Yealink VCM36-W lab, filtered audit protocol, network discovery and OpenAI Secure MCP Tunnel" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/entrypoint.sh"]
