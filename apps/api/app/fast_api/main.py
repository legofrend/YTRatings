import time

from fastapi import FastAPI, Request, applications
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import RedirectResponse

from app.logger import logger
from app.fast_api.ytr import router as ytr_router


def swagger_monkey_patch(*args, **kwargs):
    return get_swagger_ui_html(
        *args,
        **kwargs,
        swagger_js_url="https://cdn.staticfile.net/swagger-ui/5.1.0/swagger-ui-bundle.min.js",
        swagger_css_url="https://cdn.staticfile.net/swagger-ui/5.1.0/swagger-ui.min.css",
    )


applications.get_swagger_ui_html = swagger_monkey_patch

app = FastAPI(title="YTRatings API", version="1.0.0", root_path="/api")

origins = [
    "http://localhost:8080",
    "http://localhost:5000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://o2t4.ru",
    "https://o2t4.ru",
    "http://ytr.o2t4.ru",
    "https://ytr.o2t4.ru",
    "http://www.ytr.o2t4.ru",
    "https://www.ytr.o2t4.ru",
]
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

app.include_router(ytr_router)


def _v2_redirect_url(path: str, request: Request) -> str:
    # External URL includes root_path (/api); keep query string.
    suffix = path.strip("/")
    target = f"/api/ytr/{suffix}" if suffix else "/api/ytr"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return target


@app.api_route("/ytr/v2", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/ytr/v2/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_ytr_v2(request: Request, path: str = ""):
    """Compat: old /ytr/v2/* → /ytr/* (308 preserves method)."""
    return RedirectResponse(url=_v2_redirect_url(path, request), status_code=308)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info("Request handling time", extra={"process_time": round(process_time, 4)})
    return response


if __name__ == "__main__":
    import uvicorn
    import os.path
    import sys

    sys.path.append(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
    )
    uvicorn.run(
        app="app.fast_api.main:app",
        port=5000,
        reload=True,
    )
