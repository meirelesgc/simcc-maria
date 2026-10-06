FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install "poetry>=2,<3"

# extra dependency groups, e.g. "dev,docs" for the tools image (compose.yaml)
ARG POETRY_GROUPS=""

WORKDIR /app
# dependencies first: this layer is reused while only the code changes
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main${POETRY_GROUPS:+,$POETRY_GROUPS} --no-root

COPY src ./src
RUN poetry install --only main${POETRY_GROUPS:+,$POETRY_GROUPS}

ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT}

RUN useradd --create-home --uid 1000 maria && mkdir -p logs && chown maria logs
USER maria

CMD ["maria-web"]
