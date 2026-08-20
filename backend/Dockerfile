FROM python:3.11-slim AS builder

ARG PYTORCH_VERSION=2.13.0
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-production.txt .

RUN python -m venv "$VIRTUAL_ENV" \
    && python -m pip install --no-cache-dir \
        --index-url "$PYTORCH_CPU_INDEX_URL" \
        "torch==${PYTORCH_VERSION}+cpu" \
    && python -m pip install --no-cache-dir -r requirements-production.txt \
    && python -c "import torch; assert torch.__version__ == '${PYTORCH_VERSION}+cpu'; assert torch.version.cuda is None; assert not torch.cuda.is_available(); print(f'PyTorch runtime: {torch.__version__}')"

FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY . .

RUN python -c "import torch; assert torch.__version__.endswith('+cpu'); assert torch.version.cuda is None; assert not torch.cuda.is_available()"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
