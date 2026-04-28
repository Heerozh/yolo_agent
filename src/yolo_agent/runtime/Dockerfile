FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
RUN apt-get install -y nodejs

RUN apt-get install -y bubblewrap socat

RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list

RUN curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb

RUN apt-get update && apt-get install -y --no-install-recommends \
    bzr=2.7.* \
    dnsutils \
    docker-buildx-plugin \
    docker-ce-cli \
    docker-compose-plugin \
    dotnet-sdk-10.0 \
    fd-find \
    gettext \
    git \
    git-lfs \
    vim \
    inotify-tools \
    iputils-ping \
    jq \
    moreutils \
    netcat-openbsd \
    openssh-client \
    ripgrep \
    rsync \
    sqlite3 \
    tzdata \
    unzip \
    uuid-dev \
    wget \
    xz-utils \
    zip \
    && rm -rf /var/lib/apt/lists/*

RUN git config --global core.whitespace cr-at-eol \
    && git config --global core.autocrlf input

ARG AGENT_CACHE_BUST=1
RUN echo "${AGENT_CACHE_BUST}" > /tmp/agent-cache-bust
RUN npm i -g @openai/codex
RUN npm install -g @google/gemini-cli
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

ENV HOME=/root

WORKDIR /workspace

CMD ["/bin/bash"]
