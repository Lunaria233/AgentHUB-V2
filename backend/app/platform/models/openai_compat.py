from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from app.platform.core.errors import ModelInvocationError
from app.platform.models.base import BaseModelClient, ModelChunk, ModelRequest, ModelResponse


class OpenAICompatClient(BaseModelClient):
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0),
            http2=True,
        )

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = self._build_payload(request)
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            response_obj = getattr(exc, "response", None)
            status_code = response_obj.status_code if response_obj is not None else "unknown"
            body_preview = self._summarize_response_text(response_obj.text) if response_obj is not None else ""
            request_id = self._extract_request_id(response_obj) if response_obj is not None else ""
            details = f"Model call failed for requested model '{request.model}' (HTTP {status_code})"
            if request_id:
                details += f", request_id={request_id}"
            if body_preview:
                details += f". Provider response: {body_preview}"
            else:
                details += f": {exc}"
            raise ModelInvocationError(details) from exc

        raw_text = response.text
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = self._decode_json_payload(raw_text)
        provider_error = self._extract_provider_error(data)
        if provider_error:
            raise ModelInvocationError(
                self._format_provider_error(
                    request_model=request.model,
                    response=response,
                    message=provider_error,
                    raw_text=raw_text,
                )
            )
        try:
            choices = data["choices"]
            if not choices:
                raise ModelInvocationError(
                    self._format_empty_choices_error(
                        request_model=request.model,
                        response=response,
                        data=data,
                        raw_text=raw_text,
                    )
                )
            text = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelInvocationError(
                self._format_malformed_response_error(
                    request_model=request.model,
                    response=response,
                    data=data,
                    raw_text=raw_text,
                )
            ) from exc
        return ModelResponse(text=str(text or ""), raw=data)

    def stream_generate(self, request: ModelRequest) -> Iterator[ModelChunk]:
        payload = self._build_payload(request)
        payload["stream"] = True
        try:
            with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    raw_chunk = line[len("data:") :].strip()
                    if raw_chunk == "[DONE]":
                        return
                    data = json.loads(raw_chunk)
                    provider_error = self._extract_provider_error(data)
                    if provider_error:
                        raise ModelInvocationError(
                            self._format_provider_error(
                                request_model=request.model,
                                response=response,
                                message=provider_error,
                                raw_text=raw_chunk,
                            )
                        )
                    content = self._extract_stream_text(data)
                    if content:
                        yield ModelChunk(text=content, raw=data)
        except httpx.HTTPError as exc:
            response_obj = getattr(exc, "response", None)
            status_code = response_obj.status_code if response_obj is not None else "unknown"
            body_preview = self._summarize_response_text(response_obj.text) if response_obj is not None else ""
            request_id = self._extract_request_id(response_obj) if response_obj is not None else ""
            details = f"Streaming model call failed for requested model '{request.model}' (HTTP {status_code})"
            if request_id:
                details += f", request_id={request_id}"
            if body_preview:
                details += f". Provider response: {body_preview}"
            else:
                details += f": {exc}"
            raise ModelInvocationError(details) from exc

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        payload.update(request.extra)
        return payload

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ModelInvocationError("LLM_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    @staticmethod
    def _extract_stream_text(payload: dict[str, Any]) -> str:
        try:
            return str(payload["choices"][0]["delta"].get("content", "") or "")
        except (KeyError, IndexError, AttributeError, TypeError):
            return ""

    @staticmethod
    def _decode_json_payload(raw_text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        payload = raw_text.strip()
        if payload.startswith("data:"):
            for line in payload.splitlines():
                candidate = line.strip()
                if not candidate or not candidate.startswith("data:"):
                    continue
                candidate = candidate[len("data:") :].strip()
                if candidate == "[DONE]":
                    continue
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        parsed, _ = decoder.raw_decode(payload)
        if not isinstance(parsed, dict):
            raise ModelInvocationError(f"Unexpected model response payload: {payload[:400]}")
        return parsed

    @staticmethod
    def _extract_provider_error(payload: dict[str, Any]) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("msg") or error.get("detail")
            if message:
                return str(message)
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip() and payload.get("choices") is None:
            return message.strip()
        return ""

    @staticmethod
    def _extract_request_id(response: httpx.Response) -> str:
        return (
            response.headers.get("x-request-id")
            or response.headers.get("request-id")
            or response.headers.get("x-ms-request-id")
            or ""
        )

    @classmethod
    def _format_provider_error(
        cls,
        *,
        request_model: str,
        response: httpx.Response,
        message: str,
        raw_text: str,
    ) -> str:
        request_id = cls._extract_request_id(response)
        details = f"Provider returned an explicit error for requested model '{request_model}' (HTTP {response.status_code})"
        if request_id:
            details += f", request_id={request_id}"
        details += f": {message}"
        preview = cls._summarize_response_text(raw_text)
        if preview:
            details += f" | raw={preview}"
        return details

    @classmethod
    def _format_empty_choices_error(
        cls,
        *,
        request_model: str,
        response: httpx.Response,
        data: dict[str, Any],
        raw_text: str,
    ) -> str:
        provider_model = str(data.get("model") or request_model)
        request_id = cls._extract_request_id(response)
        details = (
            f"Provider returned HTTP {response.status_code} but no completion choices for requested model "
            f"'{request_model}' (provider model='{provider_model}')"
        )
        if request_id:
            details += f", request_id={request_id}"
        details += ". This usually indicates provider-side model unavailability, exhausted quota, or incompatible API behavior."
        preview = cls._summarize_response_text(raw_text)
        if preview:
            details += f" Raw preview: {preview}"
        return details

    @classmethod
    def _format_malformed_response_error(
        cls,
        *,
        request_model: str,
        response: httpx.Response,
        data: dict[str, Any],
        raw_text: str,
    ) -> str:
        provider_model = str(data.get("model") or request_model)
        request_id = cls._extract_request_id(response)
        details = (
            f"Provider returned a malformed completion payload for requested model '{request_model}' "
            f"(provider model='{provider_model}', HTTP {response.status_code})"
        )
        if request_id:
            details += f", request_id={request_id}"
        preview = cls._summarize_response_text(raw_text)
        if preview:
            details += f". Raw preview: {preview}"
        return details

    @staticmethod
    def _summarize_response_text(raw_text: str, limit: int = 500) -> str:
        if not raw_text:
            return ""
        compact = " ".join(raw_text.split())
        if len(compact) > limit:
            return compact[:limit] + "..."
        return compact
