ARG PYTHON_VERSION=3.10-slim-buster

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN --mount=type=cache,target=/root/.cache,id=pip \
    set -ex && pip install --upgrade pip pip-tools

COPY requirements.txt /tmp/requirements.txt

RUN --mount=type=cache,target=/root/.cache,id=pip \
    set -ex && pip install -r /tmp/requirements.txt

COPY . /code/

WORKDIR /code

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "automation.wsgi"]
