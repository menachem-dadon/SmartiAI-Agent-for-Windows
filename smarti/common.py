"""Shared imports, constants, and small helpers for Smarti."""
import os
import json
import subprocess
import webbrowser
import platform
import shutil
import urllib.parse
import urllib.request
import zipfile
import threading
import time
import glob
import shlex
import unicodedata
import concurrent.futures
import secrets
import http.server
import socketserver
import socket
import requests
import re
import logging
import warnings
import sys
import io
import base64
import ast
import mimetypes
import importlib.util
import smtplib
import imaplib
import email
import html
import difflib
from email import policy as email_policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parsedate_to_datetime
import copy
import hashlib
import winsound
import tempfile
import uuid
import ctypes
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib3

from .runtime import SMARTI_RUNTIME
from .ssl_compat import (
    SSL_MODE_CUSTOM_CA,
    SSL_MODE_LEGACY_INSECURE,
    SSL_MODE_SYSTEM,
    SSL_TRUST_MIGRATION_VERSION,
    SSL_TRUST_MODES,
    SSLTrustConfigurationError,
    apply_insecure_ssl_compat,
    apply_ssl_trust_environment,
    configure_ssl_from_environment,
    create_ssl_context,
    describe_custom_ca,
    import_custom_ca,
    legacy_insecure_for_url,
    normalize_legacy_hosts,
    normalize_ssl_trust_mode,
    resolve_ssl_trust,
    ssl_request_kwargs as _resolved_ssl_request_kwargs,
    test_https_trust,
    validate_custom_ca,
)
from .api_errors import analyze_api_error, api_validation_message

LITELLM_INSTALLED = importlib.util.find_spec("litellm") is not None
KEYRING_INSTALLED = importlib.util.find_spec("keyring") is not None

def get_url(b64_str):
    return base64.b64decode(b64_str).decode('utf-8')

def get_keyring_module():
    if not KEYRING_INSTALLED:
        return None
    try:
        import keyring
        return keyring
    except Exception:
        return None

URL_OPENROUTER = "aHR0cHM6Ly9vcGVucm91dGVyLmFpL2FwaS92MQ=="
URL_GROQ = "aHR0cHM6Ly9hcGkuZ3JvcS5jb20vb3BlbmFpL3Yx"
URL_GEMINI_GEN = "aHR0cHM6Ly9nZW5lcmF0aXZlbGFuZ3VhZ2UuZ29vZ2xlYXBpcy5jb20vdjFiZXRhL21vZGVscy8="
URL_ANTHROPIC = "aHR0cHM6Ly9hcGkuYW50aHJvcGljLmNvbS92MS9tZXNzYWdlcw=="
URL_NPM = "aHR0cHM6Ly9yZWdpc3RyeS5ucG1qcy5vcmcvLS92MS9zZWFyY2g/dGV4dD0="
URL_TAVILY = "aHR0cHM6Ly9hcGkudGF2aWx5LmNvbS9zZWFyY2g="
URL_DDG = "aHR0cHM6Ly9kdWNrZHVja2dvLmNvbS8/cT0="
URL_GEMINI_MODELS = "aHR0cHM6Ly9nZW5lcmF0aXZlbGFuZ3VhZ2UuZ29vZ2xlYXBpcy5jb20vdjFiZXRhL21vZGVscz9rZXk9"
URL_OPENAI_MODELS = "aHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MS9tb2RlbHM="
URL_OPENROUTER_MODELS = "aHR0cHM6Ly9vcGVucm91dGVyLmFpL2FwaS92MS9tb2RlbHM="
URL_GROQ_MODELS = "aHR0cHM6Ly9hcGkuZ3JvcS5jb20vb3BlbmFpL3YxL21vZGVscw=="
URL_ANTHROPIC_MODELS = "aHR0cHM6Ly9hcGkuYW50aHJvcGljLmNvbS92MS9tb2RlbHM="
URL_DEEPSEEK = "aHR0cHM6Ly9hcGkuZGVlcHNlZWsuY29t"
URL_QWEN = "aHR0cHM6Ly9kYXNoc2NvcGUuYWxpeXVuY3MuY29tL2NvbXBhdGlibGUtbW9kZS92MQ=="
URL_ZHIPU = "aHR0cHM6Ly9vcGVuLmJpZ21vZGVsLmNuL2FwaS9wYWFzL3Y0"
URL_MOONSHOT = "aHR0cHM6Ly9hcGkubW9vbnNob3QuYWkvdjE="
URL_MISTRAL = "aHR0cHM6Ly9hcGkubWlzdHJhbC5haS92MQ=="
URL_TOGETHER = "aHR0cHM6Ly9hcGkudG9nZXRoZXIuYWkvdjE="
URL_PERPLEXITY = "aHR0cHM6Ly9hcGkucGVycGxleGl0eS5haQ=="
URL_XAI = "aHR0cHM6Ly9hcGkueC5haS92MQ=="
URL_NVIDIA = "aHR0cHM6Ly9pbnRlZ3JhdGUuYXBpLm52aWRpYS5jb20vdjE="
URL_CEREBRAS = "aHR0cHM6Ly9hcGkuY2VyZWJyYXMuYWkvdjE="
URL_HUGGINGFACE = "aHR0cHM6Ly9yb3V0ZXIuaHVnZ2luZ2ZhY2UuY28vdjE="
URL_CLAWHUB_API = "aHR0cHM6Ly9jbGF3aHViLmFpL2FwaS92MQ=="

MODEL_PROVIDER_ORDER = [
    "gemini", "openai", "openai_codex_signin", "anthropic", "openrouter", "groq", "nvidia", "cerebras", "huggingface",
    "deepseek", "qwen", "zhipu", "moonshot", "mistral",
    "together", "perplexity", "xai", "local"
]

MODEL_PROVIDER_CONFIGS = {
    "gemini": {
        "label": "Google Gemini",
        "kind": "gemini",
        "secret_key": "gemini_api_key",
        "help_url": "https://aistudio.google.com/apikey",
        "key_instructions": "התחבר ל-Google AI Studio, לחץ Create API key, בחר או צור פרויקט והעתק את המפתח.",
        "default_model": "gemini-3.6-flash",
    },
    "openai": {
        "label": "OpenAI",
        "kind": "openai_compatible",
        "secret_key": "openai_api_key",
        "help_url": "https://platform.openai.com/api-keys",
        "key_instructions": "התחבר ל-OpenAI Platform, לחץ Create new secret key והעתק את המפתח שנוצר.",
        "default_model": "gpt-5.6-sol",
        "base_url": None,
    },
    "openai_codex_signin": {
        "label": "OpenAI Codex Sign-in",
        "kind": "codex_signin",
        "secret_key": None,
        "key_instructions": "החיבור נפתח בדפדפן באמצעות Codex sign-in הרשמי של OpenAI. לא נדרש מפתח API.",
        "default_model": "codex default",
        "fallback_models": [
            "codex default",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "kind": "anthropic",
        "secret_key": "anthropic_api_key",
        "help_url": "https://console.anthropic.com/settings/keys",
        "key_instructions": "התחבר ל-Anthropic Console, בחר Workspace מתאים, לחץ Create Key והעתק את המפתח.",
        "default_model": "claude-opus-5",
        "fallback_models": ["claude-opus-5", "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "openai_compatible",
        "secret_key": "openrouter_api_key",
        "help_url": "https://openrouter.ai/settings/keys",
        "key_instructions": "התחבר ל-OpenRouter, לחץ Create Key, הגדר שם או מגבלת קרדיט אם צריך והעתק.",
        "default_model": "openai/gpt-5.4",
        "base_url": URL_OPENROUTER,
        "validation_path": "/key",
        "models_query": "?output_modalities=text",
    },
    "groq": {
        "label": "Groq",
        "kind": "openai_compatible",
        "secret_key": "groq_api_key",
        "help_url": "https://console.groq.com/keys",
        "key_instructions": "התחבר ל-Groq Console, לחץ Create API Key והעתק את המפתח.",
        "default_model": "openai/gpt-oss-120b",
        "base_url": URL_GROQ,
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "kind": "openai_compatible",
        "secret_key": "nvidia_api_key",
        "help_url": "https://build.nvidia.com/nvidia/",
        "key_instructions": "התחבר ל-NVIDIA Build, פתח מודל ב-Hosted API ולחץ Generate API Key, ואז העתק את המפתח.",
        "default_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "base_url": URL_NVIDIA,
        "fallback_models": [
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "nvidia/llama-3.1-nemotron-nano-8b-v1",
            "nvidia/nemotron-3-nano-30b-a3b",
            "deepseek-ai/deepseek-v4-pro",
        ],
    },
    "cerebras": {
        "label": "Cerebras",
        "kind": "openai_compatible",
        "secret_key": "cerebras_api_key",
        "help_url": "https://cloud.cerebras.ai/",
        "key_instructions": "התחבר ל-Cerebras Cloud, פתח API Keys, צור מפתח חדש והעתק אותו.",
        "default_model": "gpt-oss-120b",
        "base_url": URL_CEREBRAS,
        "fallback_models": ["gpt-oss-120b", "zai-glm-4.7"],
    },
    "huggingface": {
        "label": "Hugging Face",
        "kind": "openai_compatible",
        "secret_key": "huggingface_api_key",
        "help_url": "https://huggingface.co/settings/tokens",
        "key_instructions": "התחבר ל-Hugging Face, פתח Settings > Access Tokens, צור User Access Token והעתק אותו.",
        "default_model": "openai/gpt-oss-120b",
        "base_url": URL_HUGGINGFACE,
        "fallback_models": [
            "openai/gpt-oss-120b",
            "deepseek-ai/DeepSeek-R1:fastest",
            "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "meta-llama/Llama-3.3-70B-Instruct",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "openai_compatible",
        "secret_key": "deepseek_api_key",
        "help_url": "https://platform.deepseek.com/api_keys",
        "key_instructions": "התחבר ל-DeepSeek Platform, פתח API keys, צור מפתח חדש והעתק.",
        "default_model": "deepseek-v4-flash",
        "base_url": URL_DEEPSEEK,
        "fallback_models": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
    },
    "qwen": {
        "label": "Alibaba Qwen / DashScope",
        "kind": "openai_compatible",
        "secret_key": "qwen_api_key",
        "help_url": "https://bailian.console.aliyun.com/?tab=model#/api-key",
        "key_instructions": "התחבר ל-Alibaba Model Studio/Bailian, בחר אזור, לחץ Create API Key והעתק.",
        "default_model": "qwen-plus",
        "base_url": URL_QWEN,
        "fallback_models": ["qwen-plus", "qwen-max", "qwen-turbo"],
    },
    "zhipu": {
        "label": "Zhipu GLM",
        "kind": "openai_compatible",
        "secret_key": "zhipu_api_key",
        "help_url": "https://open.bigmodel.cn/usercenter/proj-mgmt/apikeys",
        "key_instructions": "התחבר ל-Zhipu Open Platform, בחר פרויקט, צור API Key והעתק.",
        "default_model": "glm-5.1",
        "base_url": URL_ZHIPU,
        "fallback_models": ["glm-5.1", "glm-4.7", "glm-4-flash"],
    },
    "moonshot": {
        "label": "Moonshot Kimi",
        "kind": "openai_compatible",
        "secret_key": "moonshot_api_key",
        "help_url": "https://platform.moonshot.ai/console/api-keys",
        "key_instructions": "התחבר ל-Kimi/Moonshot Platform, בחר את הפרויקט, צור API Key והעתק.",
        "default_model": "kimi-k2.6",
        "base_url": URL_MOONSHOT,
        "fallback_models": ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-128k"],
    },
    "mistral": {
        "label": "Mistral AI",
        "kind": "openai_compatible",
        "secret_key": "mistral_api_key",
        "help_url": "https://console.mistral.ai/api-keys",
        "key_instructions": "התחבר ל-Mistral Console, לחץ Create new key והעתק מיד כי המפתח מוצג פעם אחת.",
        "default_model": "mistral-large-latest",
        "base_url": URL_MISTRAL,
        "fallback_models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
    },
    "together": {
        "label": "Together AI",
        "kind": "openai_compatible",
        "secret_key": "together_api_key",
        "help_url": "https://api.together.ai/settings/api-keys",
        "key_instructions": "התחבר ל-Together AI, פתח את Project API keys, לחץ Create API Key והעתק מיד.",
        "default_model": "openai/gpt-oss-20b",
        "base_url": URL_TOGETHER,
        "fallback_models": ["openai/gpt-oss-20b", "Qwen/Qwen3.5-397B-A17B", "zai-org/GLM-5"],
    },
    "perplexity": {
        "label": "Perplexity",
        "kind": "openai_compatible",
        "secret_key": "perplexity_api_key",
        "help_url": "https://console.perplexity.ai/",
        "key_instructions": "התחבר ל-Perplexity API Portal, צור API Group אם צריך, פתח API Keys ולחץ Generate.",
        "default_model": "sonar-pro",
        "base_url": URL_PERPLEXITY,
        "models_path": "/v1/models",
        "fallback_models": ["sonar-pro", "sonar"],
    },
    "xai": {
        "label": "xAI",
        "kind": "openai_compatible",
        "secret_key": "xai_api_key",
        "help_url": "https://console.x.ai/team/default/api-keys",
        "key_instructions": "התחבר ל-xAI Console, פתח API Keys, לחץ Create API Key והעתק את המפתח.",
        "default_model": "grok-4",
        "base_url": URL_XAI,
        "fallback_models": ["grok-4", "grok-3"],
    },
    "local": {
        "label": "Local OpenAI-compatible",
        "kind": "local",
        "secret_key": None,
        "default_model": "",
    },
}

MODEL_SELECTION_SOURCE_DEFAULT = "default"
MODEL_SELECTION_SOURCE_USER = "user"
MODEL_SELECTION_PROVENANCE_VERSION = 1

# Reasoning controls are provider contracts, not a per-model registry. Resolvers
# below attach active model families to the native contract they implement. An
# unknown future model intentionally inherits the provider's current contract.
MODEL_REASONING_CONTRACTS = {
    # Google generateContent contracts.
    "gemini_current_flash": {
        "api_field": "generationConfig.thinkingConfig.thinkingLevel",
        "supported_levels": ("minimal", "low", "medium", "high"),
        "provider_default": "medium",
        "control_kind": "thinking_level",
        "max_output_tokens": 65_536,
    },
    "gemini_current_pro": {
        "api_field": "generationConfig.thinkingConfig.thinkingLevel",
        "supported_levels": ("low", "medium", "high"),
        "provider_default": "high",
        "control_kind": "thinking_level",
        "max_output_tokens": 65_536,
    },
    "gemini_current_flash_lite": {
        "api_field": "generationConfig.thinkingConfig.thinkingLevel",
        "supported_levels": ("minimal", "low", "medium", "high"),
        "provider_default": "minimal",
        "control_kind": "thinking_level",
        "max_output_tokens": 65_536,
    },
    "gemini_current_flash_image": {
        "api_field": "generationConfig.thinkingConfig.thinkingLevel",
        "supported_levels": ("minimal", "high"),
        "provider_default": "minimal",
        "control_kind": "thinking_level",
        "max_output_tokens": 65_536,
    },
    "gemini_3_flash": {
        "api_field": "generationConfig.thinkingConfig.thinkingLevel",
        "supported_levels": ("minimal", "low", "medium", "high"),
        "provider_default": "high",
        "control_kind": "thinking_level",
        "max_output_tokens": 65_536,
    },
    "gemini_25_pro": {
        "api_field": "generationConfig.thinkingConfig.thinkingBudget",
        "supported_levels": ("low", "medium", "high"),
        "provider_default": "dynamic",
        "control_kind": "thinking_budget",
        "budget_by_level": {"low": 1_024, "medium": 8_192, "high": 32_768},
        "max_output_tokens": 65_536,
    },
    "gemini_25_flash": {
        "api_field": "generationConfig.thinkingConfig.thinkingBudget",
        "supported_levels": ("none", "low", "medium", "high"),
        "provider_default": "dynamic",
        "control_kind": "thinking_budget",
        "budget_by_level": {
            "none": 0,
            "low": 1_024,
            "medium": 8_192,
            "high": 24_576,
        },
        "max_output_tokens": 65_536,
    },
    "gemini_25_flash_lite": {
        "api_field": "generationConfig.thinkingConfig.thinkingBudget",
        "supported_levels": ("none", "low", "medium", "high"),
        "provider_default": "none",
        "control_kind": "thinking_budget",
        "budget_by_level": {
            "none": 0,
            "low": 1_024,
            "medium": 8_192,
            "high": 24_576,
        },
        "max_output_tokens": 65_536,
    },

    # OpenAI Chat Completions contracts. The UI keeps "auto" separate so
    # omitting reasoning_effort always preserves the provider default.
    "openai_current": {
        "api_field": "reasoning_effort",
        "supported_levels": ("none", "low", "medium", "high", "xhigh", "max"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_55": {
        "api_field": "reasoning_effort",
        "supported_levels": ("none", "low", "medium", "high", "xhigh"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_55_pro": {
        "api_field": "reasoning_effort",
        "supported_levels": ("medium", "high", "xhigh"),
        "provider_default": "high",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_54_52": {
        "api_field": "reasoning_effort",
        "supported_levels": ("none", "low", "medium", "high", "xhigh"),
        "provider_default": "none",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_54_pro": {
        "api_field": "reasoning_effort",
        "supported_levels": ("medium", "high", "xhigh"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_52_pro": {
        "api_field": "reasoning_effort",
        "supported_levels": ("medium", "high", "xhigh"),
        "provider_default": "provider",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_51": {
        "api_field": "reasoning_effort",
        "supported_levels": ("none", "low", "medium", "high"),
        "provider_default": "none",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_5": {
        "api_field": "reasoning_effort",
        "supported_levels": ("minimal", "low", "medium", "high"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_5_pro": {
        "api_field": "reasoning_effort",
        "supported_levels": ("high",),
        "provider_default": "high",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 272_000,
    },
    "openai_codex_53": {
        "api_field": "reasoning_effort",
        "supported_levels": ("low", "medium", "high", "xhigh"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 128_000,
    },
    "openai_o3": {
        "api_field": "reasoning_effort",
        "supported_levels": ("low", "medium", "high"),
        "provider_default": "medium",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 100_000,
    },
    "openai_o3_pro": {
        "api_field": "reasoning_effort",
        "supported_levels": ("high",),
        "provider_default": "high",
        "control_kind": "reasoning_effort",
        "max_output_tokens": 100_000,
    },

    # Anthropic Messages contracts.
    "anthropic_current_default_on": {
        "api_field": "thinking.type + output_config.effort",
        "supported_levels": ("none", "low", "medium", "high", "xhigh", "max"),
        "provider_default": "high",
        "control_kind": "adaptive_default_on",
        "max_output_tokens": 128_000,
        "default_output_tokens": 64_000,
    },
    "anthropic_current_always_on": {
        "api_field": "output_config.effort",
        "supported_levels": ("low", "medium", "high", "xhigh", "max"),
        "provider_default": "high",
        "control_kind": "adaptive_always_on",
        "max_output_tokens": 128_000,
        "default_output_tokens": 64_000,
    },
    "anthropic_adaptive_47_48": {
        "api_field": "thinking.type + output_config.effort",
        "supported_levels": ("none", "low", "medium", "high", "xhigh", "max"),
        "provider_default": "none",
        "control_kind": "adaptive_opt_in",
        "max_output_tokens": 128_000,
        "default_output_tokens": 64_000,
    },
    "anthropic_adaptive_46": {
        "api_field": "thinking.type + output_config.effort",
        "supported_levels": ("none", "low", "medium", "high", "max"),
        "provider_default": "none",
        "control_kind": "adaptive_opt_in",
        "max_output_tokens": 128_000,
        "default_output_tokens": 64_000,
    },
    "anthropic_manual_opus_45": {
        "api_field": "thinking.budget_tokens + output_config.effort",
        "supported_levels": ("none", "low", "medium", "high"),
        "provider_default": "none",
        "control_kind": "manual_budget_with_effort",
        "budget_by_level": {"low": 1_024, "medium": 8_192, "high": 32_768},
        "max_output_tokens": 64_000,
        "default_output_tokens": 64_000,
    },
    "anthropic_manual_45": {
        "api_field": "thinking.budget_tokens",
        "supported_levels": ("none", "low", "medium", "high", "max"),
        "provider_default": "none",
        "control_kind": "manual_budget",
        "budget_by_level": {
            "low": 1_024,
            "medium": 8_192,
            "high": 16_384,
            "max": 32_768,
        },
        "max_output_tokens": 64_000,
        "default_output_tokens": 64_000,
    },
    "codex_signin": {
        "api_field": "model_reasoning_effort",
        "supported_levels": ("low", "medium", "high", "xhigh", "max"),
        "provider_default": "provider",
        "control_kind": "codex",
    },
}

MODEL_REASONING_LEVEL_LABELS = {
    "auto": "אוטומטית — ברירת הספק",
    "none": "ללא חשיבה",
    "minimal": "מינימלית",
    "low": "נמוכה",
    "medium": "בינונית",
    "high": "גבוהה",
    "xhigh": "גבוהה מאוד",
    "max": "מקסימלית",
}

warnings.filterwarnings("ignore", category=UserWarning, message=".*pkg_resources is deprecated.*")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
WIN_CREATE_NO_WINDOW = 0x08000000
SMARTI_BROWSER_DEBUG_PORT = 49223
SMARTI_BROWSER_PROFILE_NAME = "SmartiChromeProfile"
SMARTI_APP_DISPLAY_NAME = "SmartiAI"
SMARTI_APP_AUMID = "SmartiAI"

class SmartiCancelled(Exception):
    pass

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QBoxLayout,
                             QHBoxLayout, QTextEdit, QPlainTextEdit, QPushButton, QLabel,
                             QScrollArea, QFrame, QMenu, QLineEdit, QTextBrowser, QProgressBar,
                             QCheckBox, QFormLayout, QSizePolicy, QMessageBox, QComboBox, QSystemTrayIcon, QSlider, QStackedWidget, QStyleOptionButton, QStyle, QGraphicsOpacityEffect, QGraphicsEffect, QGraphicsDropShadowEffect, QFileDialog, QDialog, QDialogButtonBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView, QToolTip)
from PyQt6.QtCore import Qt, QEvent, QObject, QThread, pyqtSignal, QSize, QTimer, QPoint, QPropertyAnimation, QEasingCurve, QElapsedTimer, QRectF, QUrl
from PyQt6.QtGui import QIcon, QFont, QFontDatabase, QFontMetrics, QPixmap, QCursor, QColor, QPainter, QPainterPath, QPen, QMovie, QTextOption, QPalette, QTextCursor, QLinearGradient, QBrush, QImage, QDesktopServices

DOCX_INSTALLED = importlib.util.find_spec("docx") is not None
PDF_INSTALLED = importlib.util.find_spec("PyPDF2") is not None
BS4_INSTALLED = importlib.util.find_spec("bs4") is not None
MARKDOWN_INSTALLED = importlib.util.find_spec("markdown") is not None
PILLOW_INSTALLED = importlib.util.find_spec("PIL") is not None
KEYBOARD_INSTALLED = importlib.util.find_spec("keyboard") is not None
SPEECH_INSTALLED = importlib.util.find_spec("speech_recognition") is not None
GTTS_INSTALLED = importlib.util.find_spec("gtts") is not None and importlib.util.find_spec("pygame") is not None
EDGE_TTS_INSTALLED = importlib.util.find_spec("edge_tts") is not None and importlib.util.find_spec("pygame") is not None
TTS_INSTALLED = GTTS_INSTALLED or EDGE_TTS_INSTALLED

GOOGLE_HEBREW_TTS_VOICES = [
    {"id": "co.il", "name": "גוגל (gTTS)", "tld": "co.il"},
]

EDGE_HEBREW_TTS_VOICES = [
    {"id": "edge:he-IL-AvriNeural", "name": "אברי (edge-tts)", "engine": "edge", "voice": "he-IL-AvriNeural"},
    {"id": "edge:he-IL-HilaNeural", "name": "הילה (edge-tts)", "engine": "edge", "voice": "he-IL-HilaNeural"},
]

def _google_hebrew_tts_fallback_voices():
    voices = []
    for voice in GOOGLE_HEBREW_TTS_VOICES:
        item = dict(voice)
        item.setdefault("engine", "gtts")
        voices.append(item)
    return voices

def list_tts_voices(refresh=False):
    voices = []
    if EDGE_TTS_INSTALLED:
        voices.extend(copy.deepcopy(EDGE_HEBREW_TTS_VOICES))
    if GTTS_INSTALLED:
        voices.extend(_google_hebrew_tts_fallback_voices())
    return voices

APP_DIR = SMARTI_RUNTIME.app_dir
RESOURCE_DIR = SMARTI_RUNTIME.resource_dir
RUNTIME_DIR = SMARTI_RUNTIME.runtime_dir

def _resolve_user_data_dir():
    override = os.environ.get("SMARTI_DATA_DIR", "").strip()
    candidates = []
    if override:
        candidates.append(os.path.abspath(os.path.expanduser(os.path.expandvars(override))))
    for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(os.path.join(base, "SmartiAI"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".smarti"))
    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except Exception:
            pass
    return APP_DIR

def _resolve_default_outputs_dir():
    user_profile = os.environ.get("USERPROFILE", "")
    documents = os.path.join(user_profile, "Documents") if user_profile else ""
    if documents and os.path.isdir(documents):
        return os.path.join(documents, "Smarti_Outputs")
    return os.path.join(USER_DATA_DIR, "Smarti_Outputs")

USER_DATA_DIR = _resolve_user_data_dir()

LEGACY_SETTINGS_FILE = os.path.join(APP_DIR, "smarti_settings.json")
LEGACY_USAGE_FILE = os.path.join(APP_DIR, "smarti_usage.json")
LEGACY_MEMORY_FILE = os.path.join(APP_DIR, "smarti_memory.json")
LEGACY_MEMORY_EXPORT_FILE = os.path.join(APP_DIR, "smarti_memory.md")
LEGACY_CHAT_HISTORY_FILE = os.path.join(APP_DIR, "smarti_chats.json")
LEGACY_TOOLS_DIR = os.path.join(APP_DIR, "custom_tools")
LEGACY_MCP_TOOLS_DIR = os.path.join(APP_DIR, "mcp_tools")
LEGACY_SKILLS_DIR = os.path.join(APP_DIR, "skills")
LEGACY_OUTPUTS_DIR = os.path.join(APP_DIR, "Smarti_Outputs")
LEGACY_MCP_CONFIG_FILE = os.path.join(APP_DIR, "mcp_config.json")

AGENT_LOG_FILE = os.path.join(USER_DATA_DIR, "smarti_agent.log")
SETTINGS_FILE = os.path.join(USER_DATA_DIR, "smarti_settings.json")
USAGE_FILE = os.path.join(USER_DATA_DIR, "smarti_usage.json")
MEMORY_FILE = os.path.join(USER_DATA_DIR, "smarti_memory.json")
MEMORY_EXPORT_FILE = os.path.join(USER_DATA_DIR, "smarti_memory.md")
CHAT_HISTORY_FILE = os.path.join(USER_DATA_DIR, "smarti_chats.json")
CHAT_HISTORY_DB_FILE = os.path.join(USER_DATA_DIR, "smarti_chats.sqlite3")
ACTIVE_TASK_CHECKPOINT_FILE = os.path.join(USER_DATA_DIR, "active_task_checkpoint.json")
TOOLS_DIR = os.path.join(USER_DATA_DIR, "custom_tools")
MCP_TOOLS_DIR = os.path.join(USER_DATA_DIR, "mcp_tools")
SKILLS_DIR = os.path.join(USER_DATA_DIR, "skills")
ATTACHMENTS_DIR = os.path.join(USER_DATA_DIR, "attachments")
ASSETS_DIR = SMARTI_RUNTIME.resource_path("assets")
OUTPUTS_DIR = _resolve_default_outputs_dir()
MCP_CONFIG_FILE = os.path.join(USER_DATA_DIR, "mcp_config.json")
SKILL_LOG_FILE = os.path.join(USER_DATA_DIR, "smarti_skills.log")
AUDIT_LOG_FILE = os.path.join(USER_DATA_DIR, "smarti_audit.log")
SETTINGS_SCHEMA_VERSION = 2
APP_VERSION = "V0.87.0"
LEGAL_AGREEMENT_VERSION = "privacy-disclaimer-2026-06-02-v1"
LEGAL_AGREEMENT_EFFECTIVE_DATE = "2026-06-02"
LEGAL_AGREEMENT_TITLE = "מדיניות פרטיות, תנאי שימוש וכתב ויתור - Smarti AI"

logging.basicConfig(filename=AGENT_LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

def migrate_legacy_runtime_state(include_files=True, include_directories=True):
    if os.path.abspath(USER_DATA_DIR) == os.path.abspath(APP_DIR):
        return
    if include_files:
        file_pairs = [
            (LEGACY_SETTINGS_FILE, SETTINGS_FILE),
            (LEGACY_USAGE_FILE, USAGE_FILE),
            (LEGACY_MEMORY_FILE, MEMORY_FILE),
            (LEGACY_MEMORY_EXPORT_FILE, MEMORY_EXPORT_FILE),
            (LEGACY_CHAT_HISTORY_FILE, CHAT_HISTORY_FILE),
            (LEGACY_MCP_CONFIG_FILE, MCP_CONFIG_FILE),
        ]
        for legacy_path, target_path in file_pairs:
            try:
                if os.path.exists(legacy_path) and not os.path.exists(target_path):
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    shutil.copy2(legacy_path, target_path)
                    logging.info(f"Migrated legacy runtime file: {legacy_path} -> {target_path}")
            except Exception as e:
                logging.warning(f"Legacy runtime file migration skipped for {legacy_path}: {e}")

    if include_directories:
        dir_pairs = [
            (LEGACY_TOOLS_DIR, TOOLS_DIR),
            (LEGACY_MCP_TOOLS_DIR, MCP_TOOLS_DIR),
            (LEGACY_SKILLS_DIR, SKILLS_DIR),
        ]
        for legacy_path, target_path in dir_pairs:
            try:
                if os.path.isdir(legacy_path) and not os.path.exists(target_path):
                    shutil.copytree(legacy_path, target_path)
                    logging.info(f"Migrated legacy runtime directory: {legacy_path} -> {target_path}")
            except Exception as e:
                logging.warning(f"Legacy runtime directory migration skipped for {legacy_path}: {e}")

def ensure_ui_svg_asset(filename, svg_text):
    try:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        path = os.path.join(ASSETS_DIR, filename)
        current = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    current = f.read()
            except Exception:
                current = None
        if current != svg_text:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(svg_text)
            except Exception:
                if os.path.exists(path):
                    return path.replace("\\", "/")
                raise
        return path.replace("\\", "/")
    except Exception:
        return ""

MODEL_PROVIDER_SECRET_KEYS = {
    str(config.get("secret_key"))
    for config in MODEL_PROVIDER_CONFIGS.values()
    if config.get("secret_key")
}

SENSITIVE_SETTING_KEYS = MODEL_PROVIDER_SECRET_KEYS | {
    "tavily_api_key", "email_password", "email_address",
    "google_drive_client_id", "google_drive_client_secret",
    "google_drive_refresh_token", "google_drive_access_token"
}
KEYRING_SERVICE = "SmartiAI"
SECRET_PREFIX = "DPAPI:"

SAFE_TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".py", ".pyw", ".log", ".ini", ".yaml",
    ".yml", ".html", ".css", ".js", ".ts", ".xml"
}

BLOCKED_WRITE_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".jscript",
    ".scr", ".com", ".msi", ".reg", ".lnk", ".hta", ".jar"
}

EXECUTABLE_OPEN_EXTENSIONS = BLOCKED_WRITE_EXTENSIONS | {
    ".appref-ms", ".cpl", ".msc", ".pif", ".scf", ".url", ".ws", ".wsf",
    ".wsh", ".ps2", ".ps2xml", ".psc1", ".psc2", ".msh", ".msh1",
    ".msh2", ".mshxml", ".msh1xml", ".msh2xml"
}

SAFE_OPEN_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".log", ".ini", ".yaml", ".yml",
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".mp3", ".wav", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".html", ".htm", ".css", ".xml"
}

DEFAULT_MCP_ENV_ALLOWLIST = [
    "PATH", "Path", "PATHEXT", "SystemRoot", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramData", "PROCESSOR_ARCHITECTURE"
]

HIGH_RISK_TOOLS = {
    "document_manager",
    "system_command", "create_python_tool", "install_mcp", "run_mcp",
    "browser_automation", "computer_automation", "email_manager",
    "capture_screen", "save_screenshot_to_disk", "save_text_file",
    "read_local_document", "install_skill",
    "install_skill_requirements", "run_skill",
    "system_manager", "file_manager", "screen_manager",
    "automation_manager", "extension_manager", "memory_manager"
}

CAPABILITY_LABELS = {
    "office_automation": "אוטומציית Microsoft Word מקומית",
    "file_read": "קריאת קבצים מקומיים",
    "file_search": "חיפוש קבצים ותוכן",
    "file_write": "כתיבת קבצים",
    "shell": "הרצת פקודות מערכת",
    "python_tool_create": "יצירת כלי מותאם אישית",
    "python_tool_run": "הרצת כלי מותאם אישית",
    "mcp_search": "חיפוש כלי MCP",
    "mcp_install": "התקנת כלי MCP",
    "mcp_run": "הרצת כלי MCP",
    "skill_search": "חיפוש מיומנויות",
    "skill_install": "התקנת מיומנויות",
    "skill_run": "הרצת מיומנויות",
    "network": "גישה לאינטרנט",
    "browser_open": "פתיחת דפדפן גלוי",
    "file_open": "פתיחת קבצים ותיקיות",
    "software_run": "הרצת תוכנה וקבצים",
    "browser_automation": "אוטומציית דפדפן",
    "computer_control": "אוטומציית מחשב דרך עץ הנגישות של Windows",
    "email": "דואר אלקטרוני",
    "screenshot": "צילום מסך",
    "software_open": "פתיחת תוכנות",
    "background_task": "משימות רקע",
    "background_task_cancel": "ביטול משימות רקע",
    "notification_send": "שליחת התראות Windows",
    "calendar_write": "יצירת אירועי יומן",
    "app_open": "פתיחת יישומי Windows",
    "settings_open": "פתיחת הגדרות Windows",
    "audio": "שמע והקראה"
}

DEFAULT_POLICY_MATRIX = {
    "office_automation": "ask",
    "file_read": "ask",
    "file_search": "allow",
    "file_write": "ask",
    "shell": "ask",
    "python_tool_create": "ask",
    "python_tool_run": "ask",
    "mcp_search": "allow",
    "mcp_install": "ask",
    "mcp_run": "ask",
    "skill_search": "allow",
    "skill_install": "ask",
    "skill_run": "ask",
    "network": "ask",
    "browser_open": "allow",
    "file_open": "ask",
    "software_run": "ask",
    "browser_automation": "ask",
    "computer_control": "ask",
    "email": "ask",
    "screenshot": "ask",
    "software_open": "allow",
    "background_task": "ask",
    "background_task_cancel": "ask",
    "notification_send": "allow",
    "calendar_write": "ask",
    "app_open": "allow",
    "settings_open": "ask",
    "audio": "allow"
}

AUTONOMY_PROFILES = {
    "locked_down": {
        "permission_level": 1,
        "policy_matrix": copy.deepcopy(DEFAULT_POLICY_MATRIX),
        "raw_shell_requires_approval": True,
        "marketplace_install_requires_approval": True,
        "require_approval_for_cloud_upload": True,
        "write_outside_allowed_dirs_requires_approval": True
    },
    "balanced": {
        "permission_level": 2,
        "policy_matrix": copy.deepcopy(DEFAULT_POLICY_MATRIX),
        "raw_shell_requires_approval": True,
        "marketplace_install_requires_approval": True,
        "require_approval_for_cloud_upload": True,
        "write_outside_allowed_dirs_requires_approval": True
    },
    "max_autonomy": {
        "permission_level": 3,
        "policy_matrix": {cap: "allow" for cap in DEFAULT_POLICY_MATRIX},
        "raw_shell_requires_approval": False,
        "marketplace_install_requires_approval": False,
        "require_approval_for_cloud_upload": False,
        "write_outside_allowed_dirs_requires_approval": False
    }
}

POLICY_ACTIONS = {"allow", "ask", "deny"}

DESTRUCTIVE_COMMAND_HINTS = [
    "remove-item", " rmdir", " del ", " rm ", " erase ", "format ",
    "diskpart", "bcdedit", "reg delete", "set-executionpolicy", "takeown ",
    "icacls ", "cipher /w", "stop-computer", "restart-computer"
]

SELF_PROTECTED_NAMES = {
    "mcp_tools", "custom_tools", "skills", "assets", "smarti_outputs",
    "smarti_core.pyw", "smarti_settings.json", "smarti_memory.json",
    "smarti_chats.json",
    "smarti_memory.md", "smarti_agent.log"
}

_CURRENT_SETTINGS_REF = {"settings": None}

def normalize_provider_name(provider):
    value = str(provider or "").strip().lower()
    aliases = {
        "openai codex sign-in": "openai_codex_signin",
        "openai codex signin": "openai_codex_signin",
    }
    return aliases.get(value, value)

def provider_config(provider):
    return MODEL_PROVIDER_CONFIGS.get(normalize_provider_name(provider), {})

def provider_display_name(provider):
    provider = normalize_provider_name(provider)
    config = provider_config(provider)
    return config.get("label") or provider or "provider"

def provider_secret_key(provider):
    return provider_config(provider).get("secret_key")

def provider_help_url(provider=None, secret_key=None):
    if secret_key == "tavily_api_key":
        return "https://app.tavily.com/home"
    if secret_key:
        for config in MODEL_PROVIDER_CONFIGS.values():
            if config.get("secret_key") == secret_key:
                return config.get("help_url", "")
    return provider_config(provider).get("help_url", "")

def provider_key_instructions(provider=None, secret_key=None):
    if secret_key == "tavily_api_key":
        return "התחבר ל-Tavily Platform והעתק מפתח מהדשבורד. אם אין מפתח, צור מפתח חדש והעתק אותו לכאן."
    if secret_key:
        for config in MODEL_PROVIDER_CONFIGS.values():
            if config.get("secret_key") == secret_key:
                return config.get("key_instructions", "")
    return provider_config(provider).get("key_instructions", "")

def provider_default_model(provider):
    return provider_config(provider).get("default_model", "")

def _reasoning_contract(contract_id):
    contract = copy.deepcopy(MODEL_REASONING_CONTRACTS.get(contract_id, {}))
    if contract:
        contract["contract_id"] = contract_id
        contract["sampling_parameters"] = False
        contract["reasoning_efforts"] = tuple(contract.get("supported_levels") or ())
        if contract.get("control_kind") == "thinking_level":
            contract["thinking_levels"] = tuple(contract.get("supported_levels") or ())
    return contract

def model_reasoning_contract(provider, model):
    """Resolve an active model family to its native reasoning API contract.

    Deliberately unknown/future model names inherit the provider's current
    contract. Known non-reasoning OpenAI models return no contract.
    """
    provider = normalize_provider_name(provider)
    name = str(model or "").strip().lower()
    if provider == "openai_codex_signin":
        return _reasoning_contract("codex_signin")
    if provider == "gemini":
        if re.match(r"^(?:text-embedding|embedding|imagen|veo|aqa)", name):
            return {}
        if name.startswith("gemini-2.5"):
            if "flash-lite" in name:
                return _reasoning_contract("gemini_25_flash_lite")
            if "pro" in name:
                return _reasoning_contract("gemini_25_pro")
            return _reasoning_contract("gemini_25_flash")
        if "flash-image" in name or ("flash-lite" in name and "image" in name):
            return _reasoning_contract("gemini_current_flash_image")
        if "flash-lite" in name:
            return _reasoning_contract("gemini_current_flash_lite")
        if "pro" in name:
            return _reasoning_contract("gemini_current_pro")
        if re.match(r"^gemini-3(?:\.0)?-flash(?:-|$)", name):
            return _reasoning_contract("gemini_3_flash")
        return _reasoning_contract("gemini_current_flash")
    if provider == "anthropic":
        if any(token in name for token in ("embedding", "moderation")):
            return {}
        if re.search(r"claude-(?:fable|mythos)(?:-|$)", name):
            return _reasoning_contract("anthropic_current_always_on")
        if re.search(r"claude-(?:opus|sonnet)-5(?:-|$)", name):
            return _reasoning_contract("anthropic_current_default_on")
        if re.search(r"claude-opus-4-(?:8|7)(?:-|$)", name):
            return _reasoning_contract("anthropic_adaptive_47_48")
        if re.search(r"claude-(?:opus|sonnet)-4-6(?:-|$)", name):
            return _reasoning_contract("anthropic_adaptive_46")
        if re.search(r"claude-opus-4-5(?:-|$)", name):
            return _reasoning_contract("anthropic_manual_opus_45")
        if re.search(r"claude-(?:sonnet|haiku)-4-5(?:-|$)", name):
            return _reasoning_contract("anthropic_manual_45")
        return _reasoning_contract("anthropic_current_default_on")
    if provider == "openai":
        if re.match(
            r"^(?:gpt-4(?:\.1|o)|chatgpt|chat-latest|text-embedding|"
            r"omni-moderation|gpt-image|dall-e|sora|whisper|tts|"
            r"gpt-audio|gpt-realtime|computer-use)",
            name,
        ):
            return {}
        if name.startswith("gpt-5.6"):
            return _reasoning_contract("openai_current")
        if name.startswith("gpt-5.5-pro"):
            return _reasoning_contract("openai_55_pro")
        if name.startswith("gpt-5.5"):
            return _reasoning_contract("openai_55")
        if name.startswith("gpt-5.4-pro"):
            return _reasoning_contract("openai_54_pro")
        if name.startswith("gpt-5.4"):
            return _reasoning_contract("openai_54_52")
        if re.match(r"^gpt-5\.3-codex(?:-|$)", name):
            return _reasoning_contract("openai_codex_53")
        if name.startswith("gpt-5.2-pro"):
            return _reasoning_contract("openai_52_pro")
        if name.startswith("gpt-5.2"):
            return _reasoning_contract("openai_54_52")
        if name.startswith("gpt-5.1"):
            return _reasoning_contract("openai_51")
        if name.startswith("gpt-5-pro"):
            return _reasoning_contract("openai_5_pro")
        if re.match(r"^gpt-5(?:-|$)", name):
            return _reasoning_contract("openai_5")
        if name.startswith("o3-pro"):
            return _reasoning_contract("openai_o3_pro")
        if re.match(r"^o3(?:-|$)", name):
            return _reasoning_contract("openai_o3")
        return _reasoning_contract("openai_current")
    return {}

def normalize_model_reasoning_level(provider, model, level, fallback="auto"):
    contract = model_reasoning_contract(provider, model)
    supported = tuple(contract.get("supported_levels") or ())
    value = str(level or "").strip().lower()
    aliases = {"off": "none"}
    value = aliases.get(value, value)
    if value == "auto":
        return "auto"
    return value if value in supported else fallback

def model_reasoning_setting(settings, provider, model):
    provider = normalize_provider_name(provider)
    if provider == "openai_codex_signin":
        return normalize_model_reasoning_level(
            provider,
            model,
            (settings or {}).get("codex_reasoning_effort", "auto"),
            fallback="auto",
        )
    provider_values = (settings or {}).get("model_reasoning_efforts", {})
    if not isinstance(provider_values, dict):
        provider_values = {}
    model_values = provider_values.get(provider, {})
    if not isinstance(model_values, dict):
        model_values = {}
    value = model_values.get(str(model or "").strip().lower(), "auto")
    return normalize_model_reasoning_level(provider, model, value)

def set_model_reasoning_setting(settings, provider, model, level):
    provider = normalize_provider_name(provider)
    normalized = normalize_model_reasoning_level(provider, model, level)
    if provider == "openai_codex_signin":
        settings["codex_reasoning_effort"] = normalized
        return settings["codex_reasoning_effort"]
    all_values = settings.setdefault("model_reasoning_efforts", {})
    model_values = all_values.setdefault(provider, {})
    model_values[str(model or "").strip().lower()] = normalized
    return normalized

def model_reasoning_options(provider, model):
    contract = model_reasoning_contract(provider, model)
    if not contract:
        return []
    values = list(contract.get("supported_levels") or ())
    values.insert(0, "auto")
    return [
        (value, MODEL_REASONING_LEVEL_LABELS.get(value, value))
        for value in values
    ]

def model_reasoning_api_parameters(provider, model, level):
    provider = normalize_provider_name(provider)
    contract = model_reasoning_contract(provider, model)
    normalized = normalize_model_reasoning_level(provider, model, level)
    if not contract or normalized == "auto":
        return {}
    kind = contract.get("control_kind")
    if provider == "openai":
        return {"reasoning_effort": normalized}
    if provider == "gemini":
        if kind == "thinking_level":
            return {
                "generationConfig": {
                    "thinkingConfig": {"thinkingLevel": normalized}
                }
            }
        budget = (contract.get("budget_by_level") or {}).get(normalized)
        if budget is not None:
            return {
                "generationConfig": {
                    "thinkingConfig": {"thinkingBudget": int(budget)}
                }
            }
        return {}
    if provider == "anthropic":
        if normalized == "none":
            return {"thinking": {"type": "disabled"}}
        result = {}
        if kind == "adaptive_opt_in":
            result["thinking"] = {"type": "adaptive", "display": "omitted"}
            result["output_config"] = {"effort": normalized}
        elif kind in {"adaptive_default_on", "adaptive_always_on"}:
            result["output_config"] = {"effort": normalized}
        elif kind in {"manual_budget", "manual_budget_with_effort"}:
            budget = (contract.get("budget_by_level") or {}).get(normalized)
            if budget is not None:
                result["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": int(budget),
                    "display": "omitted",
                }
            if kind == "manual_budget_with_effort":
                result["output_config"] = {"effort": normalized}
        return result
    return {}

def provider_fallback_models(provider):
    config = provider_config(provider)
    models = list(config.get("fallback_models") or [])
    default_model = config.get("default_model", "")
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return models

def is_openai_compatible_provider(provider):
    return provider_config(provider).get("kind") == "openai_compatible"

def provider_requires_api_key(provider):
    return bool(provider_secret_key(provider))

def provider_base_url(provider, local_url=""):
    provider = normalize_provider_name(provider)
    if provider == "local":
        return str(local_url or "http://localhost:1234/v1").strip().rstrip("/")
    raw = provider_config(provider).get("base_url")
    if not raw:
        return None
    return get_url(raw).rstrip("/")

def model_provider_secret_keys():
    return set(MODEL_PROVIDER_SECRET_KEYS)

def sanitize_secret_value(value):
    return re.sub(r"\s+", "", str(value or ""))

def mask_secret_value(value, visible=4):
    value = sanitize_secret_value(value)
    if not value:
        return ""
    visible = max(1, int(visible or 4))
    tail = value[-visible:]
    hidden_len = max(8, len(value) - len(tail))
    return ("•" * min(hidden_len, 24)) + tail

_TEXT_MODEL_REJECT_RE = re.compile(
    r"(?i)("
    r"embedding|embed|rerank|moderation|omni-moderation|guard|"
    r"whisper|transcrib|translate|tts|speech|audio|voice|realtime|"
    r"dall[-_ ]?e|image|imagen|gpt-image|flux|stable[-_ ]?diffusion|sdxl|"
    r"ocr|clip|vision-?embed"
    r")"
)

def _metadata_terms(metadata):
    if not isinstance(metadata, dict):
        return ""
    terms = []
    for key in ("id", "name", "displayName", "display_name", "description", "owned_by", "type"):
        value = metadata.get(key)
        if value:
            terms.append(str(value))
    return " ".join(terms)

def is_text_generation_model(provider, model_id, metadata=None):
    model_id = str(model_id or "").strip()
    if not model_id:
        return False
    data = metadata if isinstance(metadata, dict) else {}
    arch = data.get("architecture") if isinstance(data.get("architecture"), dict) else {}
    output_modalities = arch.get("output_modalities") or data.get("output_modalities") or data.get("outputs")
    if isinstance(output_modalities, str):
        output_modalities = [output_modalities]
    if output_modalities:
        normalized = {str(item).strip().lower() for item in output_modalities}
        if "text" not in normalized:
            return False
    input_modalities = arch.get("input_modalities") or data.get("input_modalities") or data.get("inputs")
    if isinstance(input_modalities, str):
        input_modalities = [input_modalities]
    if input_modalities:
        normalized = {str(item).strip().lower() for item in input_modalities}
        if "text" not in normalized:
            return False
    combined = f"{model_id} {_metadata_terms(data)}"
    return not _TEXT_MODEL_REJECT_RE.search(combined)

def _extract_model_id(provider, item):
    if isinstance(item, str):
        model_id = item
    elif isinstance(item, dict):
        model_id = item.get("id") or item.get("name") or item.get("model") or ""
    else:
        model_id = ""
    model_id = str(model_id or "").strip()
    if provider == "gemini" and model_id.startswith("models/"):
        model_id = model_id.replace("models/", "", 1)
    return model_id

def _dedupe_sorted_models(models):
    seen = set()
    cleaned = []
    for model in models:
        model = str(model or "").strip()
        if model and model not in seen:
            cleaned.append(model)
            seen.add(model)
    return sorted(cleaned, key=lambda value: value.lower(), reverse=True)

def _normalize_model_items(provider, items):
    provider = normalize_provider_name(provider)
    models = []
    for item in items or []:
        model_id = _extract_model_id(provider, item)
        if provider == "gemini" and isinstance(item, dict):
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
        if is_text_generation_model(provider, model_id, item if isinstance(item, dict) else None):
            models.append(model_id)
    return _dedupe_sorted_models(models)

def _models_from_response(provider, payload):
    provider = normalize_provider_name(provider)
    if not isinstance(payload, dict):
        return []
    if provider == "gemini":
        return _normalize_model_items(provider, payload.get("models", []))
    return _normalize_model_items(provider, payload.get("data", []))

def _coerce_ssl_settings(ssl_settings=None):
    if isinstance(ssl_settings, dict):
        return ssl_settings
    # A legacy boolean is migration input only. It must never re-enable the
    # historical global verification bypass.
    return {
        "ssl_trust_mode": SSL_MODE_SYSTEM,
        "allow_insecure_ssl_compat": bool(ssl_settings),
    }


def ssl_request_kwargs(ssl_settings=None, *, url="", allow_legacy=True, data_dir=None):
    return _resolved_ssl_request_kwargs(
        _coerce_ssl_settings(ssl_settings),
        url=url,
        allow_legacy=allow_legacy,
        data_dir=data_dir,
    )

def _bearer_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}

def _models_url_for_provider(provider, local_url=""):
    provider = normalize_provider_name(provider)
    if provider == "gemini":
        return get_url(URL_GEMINI_MODELS).split("?key=", 1)[0]
    if provider == "anthropic":
        return get_url(URL_ANTHROPIC_MODELS)
    base_url = provider_base_url(provider, local_url)
    if not base_url:
        return get_url(URL_OPENAI_MODELS)
    path = provider_config(provider).get("models_path", "/models")
    query = provider_config(provider).get("models_query", "")
    return f"{base_url}{path}{query}"

def _validation_url_for_provider(provider, local_url=""):
    provider = normalize_provider_name(provider)
    config = provider_config(provider)
    if config.get("validation_path"):
        base_url = provider_base_url(provider, local_url)
        return f"{base_url}{config['validation_path']}"
    return _models_url_for_provider(provider, local_url)

def fetch_text_models_for_provider(provider, api_key="", local_url="", ssl_settings=None, validate_key=False):
    provider = normalize_provider_name(provider)
    api_key = sanitize_secret_value(api_key)
    headers = {}
    try:
        if provider == "openai_codex_signin":
            return provider_fallback_models(provider), False, "נדרשת התחברות עם ChatGPT / Codex."
        if provider == "local":
            url = _models_url_for_provider(provider, local_url)
            kwargs = ssl_request_kwargs(ssl_settings, url=url)
            response = requests.get(url, timeout=5, **kwargs)
            if response.status_code == 200:
                return _models_from_response(provider, response.json()), True, ""
            return [], False, f"שרת מקומי החזיר {response.status_code}"

        if provider_requires_api_key(provider) and not api_key:
            models = provider_fallback_models(provider)
            return models, False, "לא הוזן מפתח API"

        if provider == "gemini":
            headers = {"x-goog-api-key": api_key}
        elif provider == "anthropic":
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        else:
            headers = _bearer_headers(api_key)

        if validate_key:
            validation_url = _validation_url_for_provider(provider, local_url)
            kwargs = ssl_request_kwargs(ssl_settings, url=validation_url)
            validation_response = requests.get(
                validation_url,
                headers=headers,
                timeout=12,
                **kwargs,
            )
            if validation_response.status_code in {401, 403}:
                analysis = analyze_api_error(provider, response=validation_response)
                return [], False, api_validation_message(analysis)
            if validation_response.status_code >= 400:
                analysis = analyze_api_error(provider, response=validation_response)
                return [], False, api_validation_message(analysis)
            if provider_config(provider).get("validation_path"):
                models_url = _models_url_for_provider(provider, local_url)
                kwargs = ssl_request_kwargs(ssl_settings, url=models_url)
                model_response = requests.get(
                    models_url,
                    headers=headers,
                    timeout=12,
                    **kwargs,
                )
                models = _models_from_response(provider, model_response.json()) if model_response.status_code == 200 else provider_fallback_models(provider)
                return models, True, ""
            models = _models_from_response(provider, validation_response.json())
            return models or provider_fallback_models(provider), True, ""

        models_url = _models_url_for_provider(provider, local_url)
        kwargs = ssl_request_kwargs(ssl_settings, url=models_url)
        response = requests.get(models_url, headers=headers, timeout=10, **kwargs)
        if response.status_code == 200:
            models = _models_from_response(provider, response.json())
            return models or provider_fallback_models(provider), True, ""
        if response.status_code in {401, 403}:
            analysis = analyze_api_error(provider, response=response)
            return provider_fallback_models(provider), False, api_validation_message(analysis)
        analysis = analyze_api_error(provider, response=response)
        return provider_fallback_models(provider), False, api_validation_message(analysis)
    except Exception as e:
        analysis = analyze_api_error(provider, error=e)
        return provider_fallback_models(provider), False, api_validation_message(analysis)

def redact_sensitive_text(text, settings=None):
    if text is None: return ""
    safe = str(text)
    settings = settings or {}
    for key in SENSITIVE_SETTING_KEYS:
        value = str(settings.get(key, "") or "")
        if len(value) >= 4:
            safe = safe.replace(value, f"[REDACTED:{key}]")
    safe = re.sub(r'(?i)(api[_-]?key|token|password|secret|authorization)["\':=\s]+[^\s,;"]+', r'\1=[REDACTED]', safe)
    safe = re.sub(r'(?i)(key=)[^&\s]+', r'\1[REDACTED]', safe)
    safe = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED:email]', safe)
    safe = re.sub(r'C:\\Users\\[^\\\r\n]+', r'C:\\Users\\[USER]', safe)
    return safe

class SmartiRedactingFilter(logging.Filter):
    def filter(self, record):
        settings = _CURRENT_SETTINGS_REF.get("settings") or {}
        if settings.get("privacy_redact_logs", True):
            record.msg = redact_sensitive_text(record.getMessage(), settings)
            record.args = ()
        return True

logging.getLogger().addFilter(SmartiRedactingFilter())

def normalize_bool_text(value):
    return str(value).strip().lower() in {"כן", "true", "yes", "y", "1"}

def strip_code_fences(code):
    code = re.sub(r'^```[a-zA-Z0-9_-]*\n', '', str(code or ''))
    code = re.sub(r'\n```$', '', code).strip()
    return code

def safe_filename(name, default="tool"):
    raw = str(name or default).strip().replace(".pyw", "").replace(".py", "")
    raw = re.sub(r'[\\/:*?"<>|]+', "_", raw)
    raw = raw.strip(" ._") or default
    return raw[:80]

def mcp_pkg_to_file_stem(pkg_name):
    return safe_filename(str(pkg_name).replace("@", "").replace("/", "_"), "mcp_tool")

def guess_mime_type(path):
    mime, _ = mimetypes.guess_type(str(path or ""))
    return mime if mime and mime.startswith("image/") else "image/png"

def _dpapi_blob(data):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf, DATA_BLOB

def dpapi_protect_text(text):
    if os.name != "nt":
        return None
    try:
        raw = str(text).encode("utf-8")
        blob_in, keepalive, DATA_BLOB = _dpapi_blob(raw)
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "Smarti secret", None, None, None, 0x01, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        try:
            protected = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            return SECRET_PREFIX + base64.b64encode(protected).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None

def dpapi_unprotect_text(value):
    if os.name != "nt" or not isinstance(value, str) or not value.startswith(SECRET_PREFIX):
        return value
    try:
        encrypted = base64.b64decode(value[len(SECRET_PREFIX):])
        blob_in, keepalive, DATA_BLOB = _dpapi_blob(encrypted)
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)
        )
        if not ok:
            return ""
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8", "replace")
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return ""

def parse_npm_package_spec(spec):
    spec = str(spec or "").strip()
    if not spec:
        return None, None, False
    version = None
    package = spec
    if spec.startswith("@"):
        slash = spec.find("/")
        if slash == -1:
            return None, None, False
        at_version = spec.rfind("@")
        if at_version > slash:
            package, version = spec[:at_version], spec[at_version + 1:]
    elif "@" in spec:
        package, version = spec.rsplit("@", 1)
    pkg_re = r'^(?:@[a-z0-9._-]+/)?[a-z0-9._-]+$'
    ver_re = r'^[0-9A-Za-z._~+:-]+$'
    if not re.match(pkg_re, package, flags=re.IGNORECASE):
        return None, None, False
    if version is not None and not re.match(ver_re, version):
        return None, None, False
    return package, version, version is not None


def file_sha256(path, max_bytes=None):
    h = hashlib.sha256()
    read_total = 0
    with open(path, "rb") as f:
        while True:
            if max_bytes and read_total >= max_bytes:
                break
            chunk_size = 1024 * 1024
            if max_bytes:
                chunk_size = min(chunk_size, max_bytes - read_total)
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            read_total += len(chunk)
    return h.hexdigest()


def deep_merge_defaults(defaults, loaded):
    result = copy.deepcopy(defaults)
    if not isinstance(loaded, dict):
        return result
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


def estimate_text_tokens(text):
    text = str(text or "")
    if not text.strip():
        return 0
    return max(1, int(len(text) / 4))


def markdown_to_plain_text(text, limit=None, fallback=""):
    """Convert common Markdown to readable plain text for native OS surfaces."""
    cleaned = html.unescape(str(text or ""))
    cleaned = re.sub(r"```[\s\S]*?```", " קטע קוד ", cleaned)
    cleaned = re.sub(r"~~~[\s\S]*?~~~", " קטע קוד ", cleaned)
    cleaned = re.sub(
        r"!\[([^\]]*)\]\([^)]+\)",
        lambda match: match.group(1).strip() or "תמונה",
        cleaned,
    )
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", cleaned)
    cleaned = re.sub(r"<((?:https?|mailto):[^>\s]+)>", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|>+)\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*(?:[-*_]\s*){3,}$", " ", cleaned)
    cleaned = re.sub(r"`([^`\n]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_\n]+)__", r"\1", cleaned)
    cleaned = re.sub(r"~~([^~\n]+)~~", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", cleaned)
    cleaned = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>])", r"\1", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    try:
        max_length = int(limit) if limit is not None else 0
    except (TypeError, ValueError):
        max_length = 0
    if max_length > 0 and len(cleaned) > max_length:
        cleaned = cleaned[:max(0, max_length - 3)].rstrip() + "..."
    return cleaned or str(fallback or "")



__all__ = [name for name in globals() if not name.startswith("__")]
