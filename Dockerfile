FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash openssh-client ca-certificates git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . /workspace

ENV PYTHON_BIN=python
ENTRYPOINT ["bash", "scripts/zt.sh"]
CMD ["validate", "--config", "configs/environments/connected.example.yaml"]
