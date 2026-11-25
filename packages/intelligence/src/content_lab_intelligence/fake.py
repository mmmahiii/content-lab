"""Scripted LLM client for tests. Never touches the network."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from content_lab_intelligence.client import StructuredLLMClient
from content_lab_intelligence.types import LLMUsage, RawCompletion, StructuredRequest

ScriptedResponse = str | Mapping[str, Any] | BaseModel | Exception | RawCompletion
ResponseHandler = Callable[[StructuredRequest[Any], int], ScriptedResponse]


@dataclass(frozen=True)
class FakeCall:
    purpose: str
    prompt: str
    system: str
    messages: list[dict[str, Any]]
    schema: Mapping[str, Any]


class FakeLLMClient(StructuredLLMClient):
    """Returns scripted responses in order, or whatever ``handler`` produces.

    A ``str`` is used as raw model text (so malformed JSON can be tested), a mapping or
    model is serialised to JSON, an exception is raised, and a ``RawCompletion`` is
    returned as-is (e.g. to simulate a refusal or ``max_tokens`` stop).
    """

    def __init__(
        self,
        responses: Sequence[ScriptedResponse] = (),
        *,
        handler: ResponseHandler | None = None,
        max_output_attempts: int = 2,
        model: str = "fake-model",
    ) -> None:
        super().__init__(max_output_attempts=max_output_attempts)
        self._responses = list(responses)
        self._handler = handler
        self.model = model
        self.calls: list[FakeCall] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _complete(
        self,
        request: StructuredRequest[Any],
        *,
        schema: Mapping[str, Any],
        messages: list[dict[str, Any]],
    ) -> RawCompletion:
        self.calls.append(
            FakeCall(
                purpose=request.purpose,
                prompt=request.prompt,
                system=request.system,
                messages=[dict(message) for message in messages],
                schema=schema,
            )
        )
        if self._handler is not None:
            scripted = self._handler(request, len(self.calls))
        elif self._responses:
            scripted = self._responses.pop(0)
        else:
            raise AssertionError(f"FakeLLMClient has no scripted response for {request.purpose}")

        if isinstance(scripted, Exception):
            raise scripted
        if isinstance(scripted, RawCompletion):
            return scripted
        if isinstance(scripted, BaseModel):
            text = scripted.model_dump_json()
        elif isinstance(scripted, Mapping):
            text = json.dumps(scripted)
        else:
            text = scripted
        usage = LLMUsage(model=self.model, input_tokens=100, output_tokens=50, cost_usd=0.0)
        return RawCompletion(text=text, stop_reason="end_turn", usage=usage, assistant_content=text)
