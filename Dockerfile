FROM python:3.12-trixie

ENV GIT_USER_NAME="Imbi Automations" \
    GIT_USER_EMAIL="imbi-automations@aweber.com" \
    IMBI_AUTOMATIONS_CACHE_DIR=/home/imbi-automations/cache \
    IMBI_AUTOMATIONS_CONFIG=/home/imbi-automations/config/config.toml

COPY dist/imbi-automations-*.whl /tmp/

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://claude.ai/install.sh | bash  \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir --upgrade pip && \
 && pip install --root-user-action ignore --break-system-packages --no-cache-dir /tmp/imbi-automations*.whl \
 && rm /tmp/*.whl \
 && groupadd --gid 1000 imbi-automations \
 && useradd --uid 1000 --gid 1000 \
            --home-dir /home/imbi-automations--create-home \
            --shell /bin/bash \
            imbi-automations

USER imbi-automations
WORKDIR /home/imbi-automations

RUN mkdir -p /home/imbi-automations/config \
             /home/imbi-automations/errors \
             /home/imbi-automations/workflows \
          /home/imbi-automations/root/.ssh \
 && chmod 700 /home/imbi-automations/.ssh \
 && git config --global user.name ${GIT_USER_NAME} && \
    git config --global user.email ${GIT_USER_EMAIL}

VOLUME [
  "/home/imbi-automations/config",
  "/home/imbi-automations/errors",
  "/home/imbi-automations/workflows"
]

ENTRYPOINT ["imbi-automations"]

CMD ["--help"]
