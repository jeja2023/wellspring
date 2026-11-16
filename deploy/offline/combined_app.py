"""部署容器入口：同一来源提供静态前端及既有 API。"""
import os
from starlette.staticfiles import StaticFiles
from wellspring.main import app


@app.middleware("http")
async def deployment_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https://*.is.autonavi.com https://*.amap.com; "
        "connect-src 'self' https://*.is.autonavi.com https://*.amap.com; "
        "font-src 'self'; worker-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# 最后挂载静态文件，API 路由始终优先；不存在的资源返回 404。
app.mount("/", StaticFiles(directory=os.environ.get("WELLSPRING_STATIC_DIR", "/app/static"), html=True), name="frontend")
