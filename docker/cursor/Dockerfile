FROM debian:bookworm-slim
WORKDIR /app

# Avoid any apt prompts in Docker builds
ENV DEBIAN_FRONTEND=noninteractive

# Install system deps + JDK 21 (Temurin)
ARG JDK_MAJOR=21

RUN set -eux \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      bash \
      git \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
         amd64) adoptium_arch="x64" ;; \
         arm64) adoptium_arch="aarch64" ;; \
         *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
       esac \
    && mkdir -p /opt/java \
    && curl -fsSL -o /tmp/jdk.tar.gz \
         "https://api.adoptium.net/v3/binary/latest/${JDK_MAJOR}/ga/linux/${adoptium_arch}/jdk/hotspot/normal/eclipse" \
    && tar -xzf /tmp/jdk.tar.gz -C /opt/java \
    && rm -f /tmp/jdk.tar.gz \
    && JDK_DIR="$(ls -1 /opt/java | head -n 1)" \
    && ln -sfn "/opt/java/${JDK_DIR}" /opt/java/current

ENV JAVA_HOME=/opt/java/current
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN java -version
RUN curl https://cursor.com/install -fsS | bash
ENV PATH="/root/.local/bin:${PATH}"
RUN cursor-agent --version || true
CMD ["bash"]
