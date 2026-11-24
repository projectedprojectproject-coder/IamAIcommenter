"""Claude API 호출 래퍼. 모든 에이전트가 JSON(구조화 출력)으로 답하게 한다."""
from __future__ import annotations

import json

import anthropic


class LLMError(Exception):
    pass


class LLMRefusal(LLMError):
    """Claude 가 안전상 이유로 답을 거절한 경우 → 사람에게 넘긴다."""


class LLM:
    def __init__(self, model: str = "claude-opus-5-5", use_fallbacks: bool = True):
        # API 키는 환경변수 ANTHROPIC_API_KEY 에서 읽는다.
        self.client = anthropic.Anthropic()
        self.model = model
        self.use_fallbacks = use_fallbacks

    def json_call(self, system: str, user: str, schema: dict,
                  effort: str = "medium", max_tokens: int = 16000) -> dict:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        try:
            if self.use_fallbacks:
                # 안전 분류기가 거절하면 서버가 다른 모델로 자동 재시도한다.
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    **kwargs,
                )
            else:
                resp = self.client.messages.create(**kwargs)
        except TypeError as e:
            if "authentication" not in str(e):
                raise
            raise SystemExit(
                "Claude API 키가 설정되지 않았습니다. PowerShell 에서 다음을 실행한 뒤 다시 시도하세요:\n"
                '  $env:ANTHROPIC_API_KEY = "sk-ant-..."'
            ) from None
        except anthropic.RateLimitError as e:
            raise LLMError(f"요청 한도 초과(429). 잠시 후 다시 실행하세요: {e.message}") from e
        except anthropic.AuthenticationError as e:
            raise LLMError("API 키가 올바르지 않습니다. ANTHROPIC_API_KEY 를 확인하세요.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API 오류 {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("네트워크 오류로 Claude API 에 연결하지 못했습니다.") from e

        if resp.stop_reason == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            raise LLMRefusal(f"Claude 가 응답을 거절했습니다 (분류: {category})")
        if resp.stop_reason == "max_tokens":
            raise LLMError("출력이 max_tokens 에서 잘렸습니다.")

        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("응답에 텍스트가 없습니다.")
        return json.loads(text)
