FROM python:3.12-slim AS base

# AWS CLI v2 and Docker CLI (client only — no daemon)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        unzip \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip \
    && unzip /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
    
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

FROM base AS develop

CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080} --reload

FROM base AS production

CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}
