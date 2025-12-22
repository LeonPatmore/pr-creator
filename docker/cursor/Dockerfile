FROM debian:bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl bash git && rm -rf /var/lib/apt/lists/*
RUN curl https://cursor.com/install -fsS | bash
ENV PATH="/root/.local/bin:${PATH}"
RUN cursor-agent --version || true
CMD ["bash"]

