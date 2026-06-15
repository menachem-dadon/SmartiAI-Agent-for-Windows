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
try:
    import winsound
except ImportError:
    winsound = None
import tempfile
import uuid
import ctypes
import ssl
from datetime import datetime, timedelta
from pathlib import Path
import urllib3

from .runtime import SMARTI_RUNTIME
from .ssl_compat import apply_insecure_ssl_compat
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
    "gemini", "openai", "anthropic", "openrouter", "groq", "nvidia", "cerebras", "huggingface",
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
        "default_model": "gemini-3.1-flash-lite",
    },
    "openai": {
        "label": "OpenAI",
        "kind": "openai_compatible",
        "secret_key": "openai_api_key",
        "help_url": "https://platform.openai.com/api-keys",
        "key_instructions": "התחבר ל-OpenAI Platform, לחץ Create new secret key והעתק את המפתח שנוצר.",
        "default_model": "gpt-5.4",
        "base_url": None,
    },
    "anthropic": {
        "label": "Anthropic",
        "kind": "anthropic",
        "secret_key": "anthropic_api_key",
        "help_url": "https://console.anthropic.com/settings/keys",
        "key_instructions": "התחבר ל-Anthropic Console, בחר Workspace מתאים, לחץ Create Key והעתק את המפתח.",
        "default_model": "claude-opus-4-7",
        "fallback_models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
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

warnings.filterwarnings("ignore", category=UserWarning, message=".*pkg_resources is deprecated.*")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
if platform.system() == "Windows":
    WIN_CREATE_NO_WINDOW = 0x08000000
else:
    WIN_CREATE_NO_WINDOW = 0
SMARTI_BROWSER_DEBUG_PORT = 49223
SMARTI_BROWSER_PROFILE_NAME = "SmartiChromeProfile"
SMARTI_APP_DISPLAY_NAME = "SmartiAI"
SMARTI_APP_AUMID = "SmartiAI"

class SmartiCancelled(Exception):
    pass

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
                             QHBoxLayout, QTextEdit, QPlainTextEdit, QPushButton, QLabel,
                             QScrollArea, QFrame, QMenu, QLineEdit, QTextBrowser, QProgressBar,
                             QCheckBox, QFormLayout, QSizePolicy, QMessageBox, QComboBox, QSystemTrayIcon, QSlider, QStackedWidget, QStyleOptionButton, QStyle, QGraphicsOpacityEffect, QGraphicsEffect, QGraphicsDropShadowEffect, QFileDialog, QDialog, QDialogButtonBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QEvent, QThread, pyqtSignal, QSize, QTimer, QPoint, QPropertyAnimation, QEasingCurve, QElapsedTimer, QRectF, QUrl
from PyQt6.QtGui import QIcon, QFont, QFontMetrics, QPixmap, QCursor, QColor, QPainter, QPainterPath, QPen, QMovie, QTextOption, QPalette, QTextCursor, QLinearGradient, QBrush, QImage, QDesktopServices

DOCX_INSTALLED = importlib.util.find_spec("docx") is not None
PDF_INSTALLED = importlib.util.find_spec("PyPDF2") is not None
BS4_INSTALLED = importlib.util.find_spec("bs4") is not None
MARKDOWN_INSTALLED = importlib.util.find_spec("markdown") is not None
PILLOW_INSTALLED = importlib.util.find_spec("PIL") is not None
KEYBOARD_INSTALLED = True if platform.system() == "Darwin" else (importlib.util.find_spec("keyboard") is not None or importlib.util.find_spec("pynput") is not None)
SPEECH_INSTALLED = importlib.util.find_spec("speech_recognition") is not None
if platform.system() == "Darwin":
    GTTS_INSTALLED = importlib.util.find_spec("gtts") is not None
else:
    GTTS_INSTALLED = importlib.util.find_spec("gtts") is not None and importlib.util.find_spec("pygame") is not None
TTS_INSTALLED = GTTS_INSTALLED

GOOGLE_HEBREW_TTS_VOICES = [
    {"id": "co.il", "name": "Google עברית - ישראל", "tld": "co.il"},
    {"id": "com", "name": "Google עברית - כללי", "tld": "com"},
    {"id": "co.uk", "name": "Google עברית - UK", "tld": "co.uk"},
    {"id": "com.au", "name": "Google עברית - Australia", "tld": "com.au"},
    {"id": "ca", "name": "Google עברית - Canada", "tld": "ca"},
    {"id": "co.in", "name": "Google עברית - India", "tld": "co.in"},
]

def list_tts_voices(refresh=False):
    return copy.deepcopy(GOOGLE_HEBREW_TTS_VOICES if GTTS_INSTALLED else [])

APP_DIR = SMARTI_RUNTIME.app_dir
RESOURCE_DIR = SMARTI_RUNTIME.resource_dir
RUNTIME_DIR = SMARTI_RUNTIME.runtime_dir

def _resolve_user_data_dir():
    override = os.environ.get("SMARTI_DATA_DIR", "").strip()
    candidates = []
    if override:
        candidates.append(os.path.abspath(os.path.expanduser(os.path.expandvars(override))))
    if platform.system() == "Darwin":
        candidates.append(os.path.join(os.path.expanduser("~"), "Library", "Application Support", "SmartiAI"))
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
    user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
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
APP_VERSION = "V0.69.0"
LEGAL_AGREEMENT_VERSION = "privacy-disclaimer-2026-06-02-v1"
LEGAL_AGREEMENT_EFFECTIVE_DATE = "2026-06-02"
LEGAL_AGREEMENT_TITLE = "מדיניות פרטיות, תנאי שימוש וכתב ויתור - Smarti AI"

logging.basicConfig(filename=AGENT_LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

def migrate_legacy_runtime_state():
    if os.path.abspath(USER_DATA_DIR) == os.path.abspath(APP_DIR):
        return
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
    "system_command", "create_python_tool", "install_mcp", "run_mcp",
    "browser_automation", "computer_automation", "email_manager",
    "capture_screen", "save_screenshot_to_disk", "save_text_file",
    "read_local_document", "install_skill",
    "install_skill_requirements", "run_skill",
    "system_manager", "file_manager", "screen_manager",
    "automation_manager", "extension_manager", "memory_manager"
}

CAPABILITY_LABELS = {
    "file_read": "קריאת קבצים מקומיים",
    "file_search": "חיפוש קבצים ותוכן",
    "file_write": "כתיבת קבצים",
    "shell": "הרצת פקודות מערכת",
    "python_tool_create": "יצירת כלי מותאם אישית",
    "python_tool_run": "הרצת כלי מותאם אישית",
    "mcp_search": "חיפוש כלים חיצוניים",
    "mcp_install": "התקנת כלים חיצוניים",
    "mcp_run": "הרצת כלים חיצוניים",
    "skill_search": "חיפוש Skills",
    "skill_install": "התקנת Skills",
    "skill_run": "הרצת Skills",
    "network": "גישה לאינטרנט",
    "browser_open": "פתיחת דפדפן גלוי",
    "file_open": "פתיחת קבצים ותיקיות",
    "software_run": "הרצת תוכנה וקבצים",
    "browser_automation": "אוטומציית דפדפן",
    "computer_control": f"אוטומציית מחשב דרך עץ הנגישות של {'macOS' if platform.system() == 'Darwin' else 'Windows'}",
    "email": "דואר אלקטרוני",
    "screenshot": "צילום מסך",
    "software_open": "פתיחת תוכנות",
    "background_task": "משימות רקע",
    "audio": "שמע והקראה"
}

DEFAULT_POLICY_MATRIX = {
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
    return str(provider or "").strip().lower()

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

def ssl_request_kwargs(allow_insecure_ssl=False):
    if allow_insecure_ssl:
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        return {"verify": False}
    return {}

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

def fetch_text_models_for_provider(provider, api_key="", local_url="", allow_insecure_ssl=False, validate_key=False):
    provider = normalize_provider_name(provider)
    api_key = sanitize_secret_value(api_key)
    kwargs = ssl_request_kwargs(allow_insecure_ssl)
    headers = {}
    try:
        if provider == "local":
            url = _models_url_for_provider(provider, local_url)
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
            validation_response = requests.get(
                _validation_url_for_provider(provider, local_url),
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
                model_response = requests.get(
                    _models_url_for_provider(provider, local_url),
                    headers=headers,
                    timeout=12,
                    **kwargs,
                )
                models = _models_from_response(provider, model_response.json()) if model_response.status_code == 200 else provider_fallback_models(provider)
                return models, True, ""
            models = _models_from_response(provider, validation_response.json())
            return models or provider_fallback_models(provider), True, ""

        response = requests.get(_models_url_for_provider(provider, local_url), headers=headers, timeout=10, **kwargs)
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



__all__ = [name for name in globals() if not name.startswith("__")]
