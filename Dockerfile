FROM python:3.12-trixie

ENV CLAUDE_CODE_USE_ANTHROPIC_API=1 \
    GH_HOST=github.com \
    GIT_USER_NAME="Imbi Automations" \
    GIT_USER_EMAIL="imbi-automations@aweber.com" \
    IMBI_AUTOMATIONS_CONFIG=/opt/config/config.toml

COPY dist/imbi_automations*.whl /tmp/
COPY docker-entrypoint.sh /usr/local/bin/

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gh \
        git \
        git-lfs \
        gnupg \
        openssh-client \
        ripgrep \
        sudo \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir --upgrade pip \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir /tmp/imbi_automations*.whl \
 && rm /tmp/*.whl \
 && mkdir -p /opt/config /opt/dry-runs /opt/errors /opt/logs /opt/workflows /docker-entrypoint-init.d \
 && groupadd --gid 1000 imbi-automations \
 && useradd --uid 1000 --gid 1000 --shell /bin/bash \
            --home-dir /home/imbi-automations --create-home \
            imbi-automations \
 && echo "imbi-automations ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/rm, /usr/bin/chmod, /usr/bin/chown" >> /etc/sudoers.d/imbi-automations \
 && chmod 440 /etc/sudoers.d/imbi-automations \
 && mkdir -p /home/imbi-automations/.ssh \
 && chmod 700 /home/imbi-automations/.ssh \
 && chown -R imbi-automations:imbi-automations /opt /docker-entrypoint-init.d \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

USER imbi-automations

WORKDIR /opt

VOLUME /opt/config /opt/dry-runs /opt/errors /opt/workflows /docker-entrypoint-init.d

ENTRYPOINT ["docker-entrypoint.sh", "imbi-automations"]

CMD ["--help"]
