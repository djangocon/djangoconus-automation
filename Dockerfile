ARG PYTHON_VERSION=3.10-slim-buster

FROM python:${PYTHON_VERSION}

ENV PATH /venv/bin:$PATH
ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONPATH /code
ENV PYTHONUNBUFFERED 1
ENV VIRTUAL_ENV /venv

RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install --upgrade pip uv

RUN python -m uv venv $VIRTUAL_ENV

COPY requirements.txt /tmp/requirements.txt

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip install --requirement /tmp/requirements.txt

COPY . /code/

WORKDIR /code

RUN python -m manage collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "automation.wsgi"]
