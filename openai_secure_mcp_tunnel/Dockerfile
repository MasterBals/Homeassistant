FROM ghcr.io/openai/tunnel-client:v0.0.14 AS tunnel_client

FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

COPY --from=tunnel_client /usr/bin/tunnel-client /usr/bin/tunnel-client

COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.name="OpenAI Secure MCP Tunnel" \
  io.hass.description="Outbound-only OpenAI Secure MCP Tunnel for Home Assistant MCP servers" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
