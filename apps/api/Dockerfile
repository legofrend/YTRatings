# https://fastapi.tiangolo.com/ru/deployment/docker/
# Exports only [tool.poetry.dependencies] (main) — no ingest/dev optional groups.
FROM python:3.12 AS requirements-stage

WORKDIR /tmp

RUN pip install --no-cache-dir "poetry>=1.8,<3" poetry-plugin-export

COPY ./pyproject.toml ./poetry.lock* /tmp/

# main only: optional groups (ingest, dev) are excluded by default
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

FROM python:3.12

RUN mkdir /code

WORKDIR /code

COPY --from=requirements-stage /tmp/requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app
COPY ./.env-docker /code/.env

RUN mkdir -p /code/logs
