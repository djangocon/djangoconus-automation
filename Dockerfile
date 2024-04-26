ARG PYTHON_VERSION=3.10-slim-buster

FROM python:${PYTHON_VERSION}

ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONPATH /code
ENV PYTHONUNBUFFERED 1

RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install --upgrade pip uv

COPY requirements.txt /tmp/requirements.txt

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip install --system --requirement /tmp/requirements.txt

COPY . /code/

WORKDIR /code

RUN python -m manage collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "automation.wsgi"]
