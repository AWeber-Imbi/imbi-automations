FROM python:3.12-trixie

ENV GIT_USER_NAME="Imbi Automations" \
    GIT_USER_EMAIL="imbi-automations@aweber.com" \
    IMBI_AUTOMATIONS_CACHE_DIR=/home/imbi-automations/cache \
    IMBI_AUTOMATIONS_CONFIG=/home/imbi-automations/config/config.toml

COPY dist/imbi_automations*.whl /tmp/

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gh \
        git \
        gnupg \
        openssh-client \
        ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://claude.ai/install.sh | bash  \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir --upgrade pip \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir /tmp/imbi_automations*.whl \
 && rm /tmp/*.whl \
 && mkdir -p /opt/config /opt/errors /opt/workflows  \
 && groupadd --gid 1000 imbi-automations \
 && useradd --uid 1000 --gid 1000 --shell /bin/bash \
            --home-dir /home/imbi-automations --create-home \
            imbi-automations \
 && mkdir -p /home/imbi-automations/.ssh \
 && chmod 700 /home/imbi-automations/.ssh \
 && chown -R imbi-automations:imbi-automations /opt \
 && git config --global user.name "${GIT_USER_NAME}" && \
    git config --global user.email "${GIT_USER_EMAIL}"

USER imbi-automations

WORKDIR /opt

VOLUME /opt/config /opt/errors /opt/workflows

ENTRYPOINT ["imbi-automations"]

CMD ["--help"]
