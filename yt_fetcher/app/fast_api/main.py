import time

from fastapi import FastAPI, applications
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

from starlette.requests import Request

from app.logger import logger
from app.report.dao import ReportDAO
from contextlib import asynccontextmanager


def swagger_monkey_patch(*args, **kwargs):
    return get_swagger_ui_html(
        *args,
        **kwargs,
        swagger_js_url="https://cdn.staticfile.net/swagger-ui/5.1.0/swagger-ui-bundle.min.js",
        swagger_css_url="https://cdn.staticfile.net/swagger-ui/5.1.0/swagger-ui.min.css"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация кэша
    FastAPICache.init(InMemoryBackend())
    yield  # Здесь можно выполнить код при завершении работы приложения
    FastAPICache.clear()  # Очистка кэша (если требуется)


applications.get_swagger_ui_html = swagger_monkey_patch

app = FastAPI(title="End-Up API", version="0.1.0", root_path="/api", lifespan=lifespan)

origins = [
    "http://localhost:8080",
    "http://localhost:5000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://o2t4.ru",
    "http://*.o2t4.ru",
]
# Разрешите все источники CORS, разрешите все методы, разрешите заголовки и разрешите с куки
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Set-Cookie",
        "Access-Control-Allow-Headers",
        "Access-Control-Allow-Origin",
        "Authorization",
    ],
)


# Эндпоинт для отдачи страницы index.html при заходе на домен
@app.get("/ytr/report")
@cache(expire=600)  # Кэшировать ответ на xxx секунд
async def get_report(period: str, category_id: int):
    return await ReportDAO.get(period, category_id)


@app.get("/ytr/metadata")
@cache(expire=3600)  # Кэшировать ответ на xxx секунд
async def get_report():
    return await ReportDAO.metadata()


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    # При подключении Prometheus + Grafana подобный лог не требуется
    logger.info("Request handling time", extra={"process_time": round(process_time, 4)})
    return response


if __name__ == "__main__":
    import uvicorn
    import os.path
    import sys

    # print(os.getcwd())
    # os.chdir("..")
    # print(os.getcwd())
    # exit(0)

    sys.path.append(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
    )
    uvicorn.run(
        app="app.fast_api.main:app",
        port=5000,
        reload=True,
    )
