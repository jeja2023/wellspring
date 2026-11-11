"""Bound request parsing and login work before expensive processing."""
import asyncio
from collections import OrderedDict, deque
import hashlib
import math
import os
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse


class RequestBudgetMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        maximum = int(os.getenv("WELLSPRING_MAX_REQUEST_BYTES", "8388608"))
        timeout = float(os.getenv("WELLSPRING_REQUEST_BODY_TIMEOUT", "30"))
        content_length = dict(scope.get("headers", [])).get(b"content-length", b"0")

        async def reject(status, code, message):
            rid = scope.get("state", {}).get("request_id", "unknown-request")
            response = JSONResponse({"code": code, "message": message, "details": [], "request_id": rid}, status_code=status)
            await response(scope, receive, send)

        try:
            if int(content_length) > maximum:
                await reject(413, "REQUEST_TOO_LARGE", "请求内容超过大小限制")
                return
        except ValueError:
            await reject(400, "INVALID_CONTENT_LENGTH", "请求长度无效")
            return
        chunks = []
        size = 0
        deadline = monotonic() + timeout
        while True:
            try:
                message = await asyncio.wait_for(receive(), max(0.001, deadline - monotonic()))
            except asyncio.TimeoutError:
                await reject(408, "REQUEST_TIMEOUT", "读取请求内容超时")
                return
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > maximum:
                await reject(413, "REQUEST_TOO_LARGE", "请求内容超过大小限制")
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        content = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": content, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


class LoginLimiter:
    """Bounded, thread-safe per-process throttle; reverse proxy headers are untrusted.

    Multi-worker deployments must also configure a shared gateway limiter.
    A hashed account key avoids keeping usernames in this operational cache.
    """
    def __init__(self):
        self._entries = OrderedDict()
        self._lock = Lock()

    def clear(self):
        with self._lock:
            self._entries.clear()

    def retry_after_seconds(self):
        return max(1, math.ceil(float(os.getenv("WELLSPRING_LOGIN_WINDOW_SECONDS", "60"))))

    def allow(self, peer, username):
        window = float(os.getenv("WELLSPRING_LOGIN_WINDOW_SECONDS", "60"))
        account_limit = int(os.getenv("WELLSPRING_LOGIN_ACCOUNT_LIMIT", "10"))
        peer_limit = int(os.getenv("WELLSPRING_LOGIN_IP_LIMIT", "30"))
        moment = monotonic()
        keys = (("account:" + hashlib.sha256(username.encode()).hexdigest(), account_limit), ("peer:" + peer, peer_limit))
        with self._lock:
            queues = []
            for key, limit in keys:
                attempts = self._entries.setdefault(key, deque())
                self._entries.move_to_end(key)
                while attempts and attempts[0] <= moment - window:
                    attempts.popleft()
                queues.append((attempts, limit))
            allowed = all(len(attempts) < limit for attempts, limit in queues)
            if allowed:
                for attempts, _limit in queues:
                    attempts.append(moment)
            while len(self._entries) > 10000:
                self._entries.popitem(last=False)
            return allowed


login_limiter = LoginLimiter()
