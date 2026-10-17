"""Structured logging configuration and stdlib integration using structlog.

Provides:
- Environment-aware structured logging (JSON for production/staging, Console for local/dev/test)
- Request-ID and contextvars propagation
- Recursive sensitive field scrubbing (passwords, tokens, secrets, authorization headers)
- Standard library logging bridge via structlog.stdlib.ProcessorFormatter
- Duplicate access log silencing for uvicorn
"""

import logging
import logging.config
import re
from collections.abc import MutableMapping
from typing import Any

import structlog
from payload_redactor import Policy, redact_event_dict, redact_traceback

from open_enterprise_ai.core.config import Settings

_REDACTION_POLICY = Policy(
    sensitive_keywords=[
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "set-cookie",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
    ],
    excluded_keywords=[
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "max_tokens",
        "token_count",
        "tokens_per_second",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cached_tokens",
    ],
    string_rules=[
        re.compile(r"(?<=:)[^@/\s]+(?=@)"),
        re.compile(r"(?<=://)[^@/:\s]+(?=@)"),
        re.compile(r"(?<=Bearer\s)[A-Za-z0-9_\-\.~+/]+=*", re.IGNORECASE),
        re.compile(r"(?<=Basic\s)[A-Za-z0-9_\-\.~+/]+=*", re.IGNORECASE),
    ],
)


def scrub_sensitive_data(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor delegating to payload_redactor with enterprise security policy."""
    redacted = redact_event_dict(
        logger,
        method_name,
        dict(event_dict),
        policy=_REDACTION_POLICY,
        replacement="[REDACTED]",
    )
    if "exception" in redacted and isinstance(redacted["exception"], str):
        redacted["exception"] = redact_traceback(
            redacted["exception"],
            policy=_REDACTION_POLICY,
            replacement="[REDACTED]",
        )
    return redacted


def configure_logging(settings: Settings) -> None:
    """Configure structlog and standard library logging pipeline.

    Supports environment-aware formatting:
    - Production and staging: Structured JSON logs
    - Local, development, and test: Colorized human-readable console output
    """
    is_json = settings.APP_ENV in ("production", "staging")
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        scrub_sensitive_data,
    ]

    formatter_processor: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if is_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    logging_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": formatter_processor,
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "structured",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": [],
                "level": logging.CRITICAL,
                "propagate": False,
            },
            "open_enterprise_ai": {
                "handlers": [],
                "level": log_level,
                "propagate": True,
            },
        },
    }

    logging.config.dictConfig(logging_config)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog BoundLogger."""
    return structlog.get_logger(name)
