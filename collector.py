#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 V2Ray Smart Collector v2.2 — Production Edition (Fixed + Reliable Rename)
اجرا در Termux، GitHub Actions، یا هر محیط Python 3.10+

تغییرات نسبت به v2.0:
  - پارس درست میزبان/پورت برای vmess:// و ss:// (باگ قبلی: هر دو همیشه رد می‌شدند)
  - GeoIP به‌صورت async و موازی + کش persistent در دیتابیس (قبلاً سریالی و in-memory بود)
  - خطاها به‌جای بلعیده‌شدن، در سطح debug لاگ می‌شوند
  - dedup بر اساس host:port قبل از تست (نه فقط رشته‌ی کامل کانفیگ)
  - اعتبارسنجی host با idna/ipaddress به‌جای replace/isalnum دستی
  - تفکیک تست Reality (CERT_NONE منطقی است) از تست TLS معمولی

تغییرات v2.2:
  - CFG.INCLUDE_VMESS (پیش‌فرض False): vmess اصلاً استخراج/تست نمی‌شود.
  - rename تضمینی و پروتکل‌آگاه: برای vmess فیلد JSON "ps" مستقیماً بازنویسی
    می‌شود (نه فقط فرگمنت #)، چون کلاینت‌ها نام را از همان‌جا می‌خوانند.
    برای vless/trojan/hysteria2/ss هم فرگمنت قبلی کامل با نام کانال جایگزین
    می‌شود (نه append) تا هیچ نام قدیمی باقی نماند.
"""

import os
import sys
import time
import socket
import ssl
import random
import asyncio
import base64
import gzip
import zlib
import json
import ipaddress
import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, unquote, quote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import aiohttp
except ImportError:
    os.system(f"{sys.executable} -m pip install aiohttp -q")
    import aiohttp

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# =============================================================================
# تنظیمات
# =============================================================================

@dataclass(frozen=True)
class Config:
    BOT_TOKEN: str = field(default_factory=lambda: os.environ.get("BOT_TOKEN", ""))
    CHAT_ID: str = field(default_factory=lambda: os.environ.get("CHAT_ID", ""))
    MY_CHANNEL_ID: str = "Goodbaye_filtering"
    TELEGRAM_LINK: str = "https://t.me/Goodbaye_filtering"
    CHAT_GROUP_LINK: str = "https://t.me/CONFIG_V2RAY_VIP"

    SOURCES: tuple = (
        "https://raw.githubusercontent.com/iboxz/free-v2ray-collector/main/main/vless.txt",
        "https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/top100.txt",
        "https://raw.githubusercontent.com/mohamadfg-dev/telegram-v2ray-configs-collector/main/category/vless.txt",
        "https://raw.githubusercontent.com/SoliSpirit/SolVPN/main/Protocols/vless.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no1.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no2.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no3.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no4.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no5.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no6.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no7.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no8.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no9.txt",
        "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/main/v2ray_configs_no10.txt",
        "https://raw.githubusercontent.com/Q3dlaXpoaQ/Q3dlaXpoaQ.github.io/main/APIs/cg1.txt",
        "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/mci/sub_1.txt",
        "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/mtn/sub_1.txt",
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
        "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/ir/vless.txt",
        "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/splitted/hysteria2",
    )

    MAX_WORKERS: int = 50
    GEO_MAX_CONCURRENT: int = 20
    GEO_TIMEOUT: float = 3.0
    GEO_MAX_CALLS_PER_RUN: int = 800
    TCP_TIMEOUT: float = 1.5
    TLS_TIMEOUT: float = 2.5
    MAX_PING_MS: int = 400
    MAX_TLS_PING_MS: int = 600
    MAX_CANDIDATES: int = 1500
    TOP_N_FINAL: int = 500
    CHUNK_SIZE: int = 150
    STABILITY_ROUNDS: int = 2

    # vmess عمداً حذف شد: نام کانال داخل JSON پنهان (فیلد "ps") است و با فرگمنت
    # ساده قابل بازنویسی تضمینی نبود. اگر بعداً خواستی روشنش کنی:
    # INCLUDE_VMESS=True کن؛ rename برای vmess حالا به‌صورت واقعی روی JSON کار می‌کند.
    INCLUDE_VMESS: bool = False

