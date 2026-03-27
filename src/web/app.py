from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith((".css", ".js")) and not path.startswith("/api"):
            response.headers["Cache-Control"] = "public, max-age=300"
        return response


from src.web.routes import router

app = FastAPI(title="AITSOK Web App")
app.add_middleware(CacheStaticMiddleware)
app.include_router(router)

static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
