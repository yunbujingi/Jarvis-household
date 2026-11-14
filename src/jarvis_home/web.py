import argparse
import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import ValidationError

from .models import Command
from .router import command
from .store import Store, Conflict


def create_app(directory, port=18600):
    store = Store(Path(directory))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    token = secrets.token_urlsafe(32)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + h for h in hosts}
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def private_only(request: Request, call_next):
        if request.headers.get("host") not in hosts:
            return JSONResponse({"message": "不允许的主机"}, status_code=403)
        if request.method != "GET":
            if request.headers.get("origin") not in origins or not secrets.compare_digest(request.headers.get("x-home-token", ""), token):
                return JSONResponse({"message": "请从本机页面提交"}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                size = -1
            if not 0 < size <= 12000:
                return JSONResponse({"message": "请求大小不符合要求"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (static / "index.html").read_text().replace("__TOKEN__", token)

    @app.get("/app.js")
    def script():
        return FileResponse(static / "app.js", media_type="application/javascript")

    @app.get("/style.css")
    def style():
        return FileResponse(static / "style.css", media_type="text/css")

    @app.get("/api/state")
    def state():
        return {**store.snapshot(), "history": store.history()}

    @app.post("/api/command")
    def run(body: Command):
        try:
            return command(store, body.request_id, body.text)
        except (Conflict, ValidationError, ValueError) as exc:
            return JSONResponse({"message": str(exc)}, status_code=409)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.environ.get("JWS_DATA_DIR", ".runtime"))
    parser.add_argument("--port", type=int, default=18600)
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir, args.port), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
