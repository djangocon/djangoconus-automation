ARG PYTHON_VERSION=3.12-slim-bookworm

FROM python:${PYTHON_VERSION}

ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONPATH /code
ENV PYTHONUNBUFFERED 1

RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install --upgrade pip uv

WORKDIR /code

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache,id=uv \
    uv pip sync --system --requirement <(uv pip compile --no-header pyproject.toml)

COPY . .

RUN python -m manage collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "automation.wsgi"]
