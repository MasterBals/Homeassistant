FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache curl jq rsync

COPY payload /opt/chatgpt-ha-admin/payload
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
