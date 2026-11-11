"""Bounded OpenAI-compatible text calls, using an operator-approved destination."""
import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import httpx

MAX_RESPONSE_BYTES = 1_048_576
MAX_OUTPUT_CHARS = 64_000
MAX_INPUT_CHARS = 20_000


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(code)


def allowed_hosts():
    return sorted({host.strip().lower().rstrip(".") for host in os.getenv("WELLSPRING_AI_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,host.docker.internal").split(",") if host.strip()})


def base_url(value: str):
    if any(ord(char) < 33 for char in value) or "\\" in value:
        raise ProviderError("AI_INVALID_URL", "模型地址包含无效字符")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProviderError("AI_INVALID_URL", "模型服务地址格式无效") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError("AI_INVALID_URL", "请使用不含账号、查询参数或片段的 HTTP/HTTPS 接口根地址")
    if port is not None and not 1 <= port <= 65535:
        raise ProviderError("AI_INVALID_URL", "模型服务端口无效")
    if parsed.hostname.lower().rstrip(".") not in allowed_hosts():
        raise ProviderError("AI_HOST_NOT_ALLOWED", "模型地址不在服务端允许名单中，请先配置 WELLSPRING_AI_ALLOWED_HOSTS")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions") or any(part in {".", ".."} for part in path.split("/")):
        raise ProviderError("AI_INVALID_URL", "请填写接口根地址（例如 /v1），不要包含 /chat/completions")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def api_key(reference=None):
    if reference is not None:
        from . import ai_secrets
        try:
            value = ai_secrets.read(reference)
            if len(value) > 16_384 or any(char in value for char in "\r\n\x00"):
                raise ValueError()
            return value
        except (OSError, UnicodeError, ValueError):
            raise ProviderError("AI_INVALID_KEY", "已保存的模型密钥不可读取，请重新填写并保存") from None
    value, filename = os.getenv("WELLSPRING_AI_API_KEY", ""), os.getenv("WELLSPRING_AI_API_KEY_FILE", "")
    if value and filename:
        raise ProviderError("AI_INVALID_KEY", "模型密钥环境变量与密钥文件只能配置其中一种")
    if filename:
        try:
            path = Path(filename)
            if path.stat().st_size > 16_384:
                raise ValueError()
            raw = path.read_bytes()
            if raw.endswith(b"\r\n"): raw = raw[:-2]
            elif raw.endswith(b"\n"): raw = raw[:-1]
            if not raw or raw.startswith(b"\xef\xbb\xbf") or any(char in raw for char in (b"\r", b"\n", b"\x00")):
                raise ValueError()
            value = raw.decode("utf-8")
        except (OSError, UnicodeError, ValueError):
            raise ProviderError("AI_INVALID_KEY", "模型密钥文件不可读取或不是有效的 UTF-8 单行内容") from None
    if len(value) > 16_384 or any(char in value for char in "\r\n\x00"):
        raise ProviderError("AI_INVALID_KEY", "模型密钥格式无效")
    return value


@dataclass(frozen=True)
class Configuration:
    url: str
    model: str
    timeout: int
    max_tokens: int
    token_parameter: str
    key: str = field(repr=False)
    version: int = 0


def configuration(values):
    if not values["enabled"] or not values["base_url"] or not values["model"]:
        raise ProviderError("AI_NOT_CONFIGURED", "模型服务尚未启用或配置不完整，请联系管理员")
    return Configuration(base_url(values["base_url"]), values["model"], values["timeout_seconds"], values["max_output_tokens"], values["token_parameter"], api_key(values.get("api_key_ref")), values["version"])


async def request_json(config: Configuration, method: str, path: str, payload=None):
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity"}
    if config.key:
        headers["Authorization"] = "Bearer " + config.key
    try:
        async with asyncio.timeout(config.timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(config.timeout, connect=min(10, config.timeout)),
                                         follow_redirects=False, trust_env=False) as client:
                async with client.stream(method, config.url + path, headers=headers, **({"json":payload} if payload is not None else {})) as response:
                    if response.status_code != 200:
                        code, message = {
                            401: ("AI_AUTH_FAILED", "模型服务鉴权失败，请检查 API Key"),
                            403: ("AI_AUTH_FAILED", "模型服务拒绝访问，请检查 API Key 及服务端授权"),
                            404: ("AI_MODEL_NOT_FOUND", "模型服务地址、模型名称或模型列表接口不存在"),
                            429: ("AI_RATE_LIMITED", "模型服务请求过于频繁，请稍后重试"),
                        }.get(response.status_code, ("AI_SERVICE_ERROR", "模型服务暂时不可用，请联系管理员检查连接"))
                        raise ProviderError(code, message)
                    chunks, size = [], 0
                    async for chunk in response.aiter_raw(chunk_size=65_536):
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ProviderError("AI_RESPONSE_TOO_LARGE", "模型服务返回内容超过接收上限")
                        chunks.append(chunk)
        result = json.loads(b"".join(chunks))
        if not isinstance(result,dict):raise ValueError()
        return result
    except (TimeoutError, httpx.TimeoutException):
        raise ProviderError("AI_TIMEOUT", "模型服务处理超时；服务端可能已收到请求") from None
    except httpx.HTTPError:
        raise ProviderError("AI_CONNECTION_FAILED", "无法连接模型服务，请检查地址、网络与证书") from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError("AI_INVALID_RESPONSE", "模型服务返回格式与兼容接口约定不符") from None


async def complete(config: Configuration, messages: list[dict], token_limit: int | None = None):
    payload = {"model": config.model, "messages": messages, "stream": False,
        config.token_parameter: token_limit or config.max_tokens}
    data = await request_json(config, "POST", "/chat/completions", payload)
    try:
        choice = data["choices"][0]
        content = choice["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("AI_EMPTY_RESPONSE", "模型未返回可用文本，请检查模型能力或更换输入")
        if len(content) > MAX_OUTPUT_CHARS:
            raise ProviderError("AI_RESPONSE_TOO_LARGE", "模型输出文本过长，请降低输出长度")
        usage = data.get("usage") or {}
        def tokens(key):
            value = usage.get(key)
            return value if type(value) is int and 0 <= value <= 100_000_000 else None
        return {"text": content, "truncated": choice.get("finish_reason") == "length",
                "prompt_tokens": tokens("prompt_tokens"), "completion_tokens": tokens("completion_tokens")}
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError("AI_INVALID_RESPONSE", "模型服务返回格式与兼容接口约定不符") from None


async def list_models(config: Configuration):
    data = await request_json(config, "GET", "/models")
    rows = data.get("data")
    if not isinstance(rows,list):
        raise ProviderError("AI_INVALID_RESPONSE", "模型列表格式无效，仍可手动填写模型 ID")
    ids = sorted({row["id"] for row in rows if isinstance(row,dict) and isinstance(row.get("id"),str)
        and 0 < len(row["id"]) <= 200 and not any(ord(char)<32 for char in row["id"])})
    if len(ids)>500:
        raise ProviderError("AI_TOO_MANY_MODELS", "模型列表超过 500 项，请收敛服务范围或手动填写 ID")
    return ids
