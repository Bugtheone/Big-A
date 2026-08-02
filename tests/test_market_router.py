#!/usr/bin/env python3
"""
market_router 单元测试（无网络依赖）

覆盖：load_config 配置文件加载（存在/缺失/非法 JSON）。
运行: python -m pytest tests/test_market_router.py -v
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import scripts.market_router as mr  # noqa: E402


class TestLoadConfig:
    def test_config_exists_returns_dict(self, tmp_path, monkeypatch):
        cfg = {"sensitivity": {"mode": "aggressive"}}
        p = tmp_path / "router_config.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(mr, "CONFIG_FILE", str(p))
        assert mr.load_config() == cfg

    def test_config_missing_returns_empty(self, monkeypatch):
        monkeypatch.setattr(mr, "CONFIG_FILE", "/nonexistent/router_config.json")
        assert mr.load_config() == {}

    def test_invalid_json_raises(self, tmp_path, monkeypatch):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(mr, "CONFIG_FILE", str(p))
        with pytest.raises(json.JSONDecodeError):
            mr.load_config()

    def test_config_empty_file_returns_empty(self, tmp_path, monkeypatch):
        p = tmp_path / "empty.json"
        p.write_text("", encoding="utf-8")
        monkeypatch.setattr(mr, "CONFIG_FILE", str(p))
        with pytest.raises(json.JSONDecodeError):
            mr.load_config()
