FROM ghcr.io/openai/tunnel-client:v0.0.14@sha256:41d7c85dab37797a3eaa17c41b94a7206dd0bc186fd361034c9ec3863596ff6c AS openai_tunnel

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
    && git -C /opt/homeassistant-source fetch --depth 1 origin 87f0bdd3d3bb6be6b9cafb3208b64cbbf78705ee \
    && git -C /opt/homeassistant-source checkout 87f0bdd3d3bb6be6b9cafb3208b64cbbf78705ee

RUN pip3 install --no-cache-dir \
    "mcp==2.1.1" \
    "httpx>=0.28,<1" \
    "websockets>=15,<16" \
    "PyYAML>=6.0.2,<7" \
    "uvicorn>=0.35,<1"

WORKDIR /app

COPY --from=openai_tunnel /usr/bin/tunnel-client-runtime /usr/local/bin/tunnel-client-runtime
COPY unified_mcp.py /app/unified_mcp.py
COPY OPENAI_TUNNEL_CLIENT_LICENSE.txt /licenses/openai-tunnel-client-LICENSE
COPY OPENAI_TUNNEL_CLIENT_NOTICE.txt /licenses/openai-tunnel-client-NOTICE
COPY run_v2.sh /run.sh
COPY entrypoint.sh /entrypoint.sh
RUN chmod a+x /run.sh /entrypoint.sh /usr/local/bin/tunnel-client-runtime

LABEL \
  io.hass.name="ChatGPT Home Assistant Admin + Intelligence" \
  io.hass.description="Unified Home Assistant MCP administration, intelligence, network discovery and OpenAI Secure MCP Tunnel" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/entrypoint.sh"]
