"""Explicit opt-in: exactly two remote calls; never part of offline regression.

Only synthetic text/tool schema is sent. No uploaded dataset is opened or sent.
API key values are accepted only through ProviderConfig.api_key_env.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from providers import ProviderConfig, ProviderConfigError, ProviderError, create_provider
from agent import AgentLoop


class StatusOnlyOpener:
    """Probe telemetry: count attempts and HTTP status; never retain request/response."""

    def __init__(self, opener) -> None:
        self.opener = opener
        self.attempts = 0
        self.status = None

    def open(self, request, **kwargs):
        self.attempts += 1
        self.status = None
        try:
            response = self.opener.open(request, **kwargs)
        except HTTPError as error:
            self.status = error.code
            raise
        self.status = response.status
        return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Two opt-in OpenAI-compatible smoke requests")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint, "model_name": args.model,
        "requests": [], "http_attempts": 0, "passed": False,
    }
    try:
        provider = create_provider(ProviderConfig(
            provider_id="openai-compatible", model_name=args.model,
            endpoint=args.endpoint, api_key_env=args.api_key_env,
        ))
    except ProviderConfigError as error:
        report["configuration_error"] = error.to_dict()
        report["requests"] = [
            {"request": label, "http_attempted": False, "passed": False, "status": "not_executed"}
            for label in ("text", "tools")
        ]
    else:
        telemetry = StatusOnlyOpener(provider._opener)
        provider._opener = telemetry
        tool = {"type": "function", "function": {
            "name": "emit_probe_status", "description": "Return the requested synthetic connectivity status.",
            "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}},
                           "required": ["status"], "additionalProperties": False},
        }}
        for label, question, tools in (
            ("text", "Reply with exactly OK. This is a synthetic connectivity check.", []),
            ("tools", "Call emit_probe_status exactly once with status ok. Do not answer in prose. This is a synthetic check.", [tool]),
        ):
            item = {"request": label, "passed": False}
            attempts_before = telemetry.attempts
            try:
                decision = provider.complete(messages=[{"role": "user", "content": question}], tools=tools)
                item["decision_type"] = decision["type"]
                parsed = AgentLoop._normalize_decision(decision, 1)
                if label == "text":
                    item["agentloop_parse_passed"] = parsed == {"type": "final_answer", "content": decision.get("content")}
                    item["passed"] = decision["type"] == "final_answer" and decision["content"].strip() == "OK" and item["agentloop_parse_passed"]
                else:
                    item["agentloop_parse_passed"] = parsed.get("type") == "tool_calls" and parsed.get("tool_calls") == [{
                        "id": decision.get("id"), "name": "emit_probe_status", "arguments": {"status": "ok"},
                    }]
                    item["passed"] = decision["type"] == "tool_call" and decision["name"] == "emit_probe_status" and decision["arguments"] == {"status": "ok"} and item["agentloop_parse_passed"]
                # Do not log model output, IDs, arguments, response bodies or config.
            except (ProviderError, ProviderConfigError) as error:
                item["error"] = error.to_dict()
            except (ValueError, TypeError, KeyError, AttributeError):
                item["error"] = {"code": "agentloop_parse_failed", "message": "existing AgentLoop could not parse the provider decision"}
            item["http_attempted"] = telemetry.attempts > attempts_before
            item["http_status"] = telemetry.status
            report["requests"].append(item)
        report["http_attempts"] = telemetry.attempts
        report["passed"] = all(item["passed"] for item in report["requests"])
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
