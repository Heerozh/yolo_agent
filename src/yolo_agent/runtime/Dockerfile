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
    locales \
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
    gosu \
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
    sudo \
    tzdata \
    unzip \
    uuid-dev \
    wget \
    xz-utils \
    zip \
    && rm -rf /var/lib/apt/lists/*

# install gh
RUN (type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
    && sudo mkdir -p -m 755 /etc/apt/keyrings \
    && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && sudo mkdir -p -m 755 /etc/apt/sources.list.d \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && sudo apt update \
    && sudo apt install gh -y


RUN git config --system core.whitespace cr-at-eol \
    && git config --system core.autocrlf input

# install utf8
RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen
RUN locale-gen
RUN update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANGUAGE=en_US:en
# speed up python by putting pycache in tmpfs
ENV PYTHONPYCACHEPREFIX=/tmp/pycache

# disable setuptools_scm read git logs, which can be slow in a container
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_HETUDB=0.0.0.dev0

RUN groupadd --gid 1000 agent \
    && useradd --uid 1000 --gid agent --create-home --shell /bin/bash agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent

ARG AGENT_CACHE_BUST=1
RUN echo "${AGENT_CACHE_BUST}" > /tmp/agent-cache-bust
RUN npm i -g @openai/codex
RUN npm install -g @google/gemini-cli

USER agent
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

USER root

COPY agent-entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod +x /usr/local/bin/agent-entrypoint

ENV HOME=/home/agent
ENV PATH=/home/agent/.local/bin:${PATH}

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
CMD ["/bin/bash"]
