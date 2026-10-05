# Dev environment for Codespaces: same OS and packages as the station.
FROM debian:trixie

ARG USERNAME=vscode

# Python and tools from Debian packages (no pip), ClamAV daemon.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        sudo \
        python3 \
        python3-pytest \
        python3-setuptools \
        python3-venv \
        python3-fastapi \
        python3-uvicorn \
        python3-jinja2 \
        python3-httpx \
        python3-pyudev \
        procps \
        clamav-daemon \
        clamav-freshclam \
        clamdscan \
    && rm -rf /var/lib/apt/lists/*

# clamd settings required by Februus (encrypted files, limits).
COPY deploy/clamav/ /tmp/februus-clamav/
RUN /tmp/februus-clamav/apply-clamd-settings.sh && rm -rf /tmp/februus-clamav

# Non-root user with sudo, as usual for devcontainers.
RUN useradd --create-home --shell /bin/bash "$USERNAME" \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$USERNAME" \
    && chmod 0440 "/etc/sudoers.d/$USERNAME"

USER $USERNAME
