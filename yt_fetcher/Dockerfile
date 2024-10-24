# https://fastapi.tiangolo.com/ru/deployment/docker/
FROM python:3.12 as requirements-stage

WORKDIR /tmp

RUN pip install poetry

# COPY ./pyproject.toml ./poetry.lock* /tmp/
COPY ./pyproject_fastapi.toml /tmp/pyproject.toml

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

FROM python:3.12

RUN mkdir /code

WORKDIR /code

COPY --from=requirements-stage /tmp/requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app
COPY ./.env-docker /code/.env

