FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.06.1

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache bash curl jq rsync git tzdata

COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
