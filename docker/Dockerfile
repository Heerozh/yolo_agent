FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        docker.io \
        git \
        iproute2 \
        iptables \
        jq \
        less \
        make \
        openssh-client \
        python3 \
        python3-pip \
        python3-venv \
        sudo \
        tini \
        unzip \
        vim \
        wget \
        xz-utils \
        zip \
    && rm -rf /var/lib/apt/lists/*

COPY docker/agent-container-entrypoint.sh /usr/local/bin/agent-container-entrypoint
RUN chmod +x /usr/local/bin/agent-container-entrypoint

WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/agent-container-entrypoint"]
CMD ["bash"]
