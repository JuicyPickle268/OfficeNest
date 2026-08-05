"""
Model Skill —— LLM 可自主搜索、添加、切换模型。
"""
import yaml
from pathlib import Path
from skills.base import BaseSkill


class ModelSkill(BaseSkill):

    def __init__(self, config_path: str = "config/models.yaml",
                 main_config_path: str = "config/default.yaml"):
        self._path = Path(config_path)
        self._main_config = Path(main_config_path)
        if not self._path.is_absolute():
            self._path = Path(__file__).parent.parent / self._path
        if not self._main_config.is_absolute():
            self._main_config = Path(__file__).parent.parent / self._main_config
        self._llm_client = None

    def set_llm_client(self, client):
        self._llm_client = client

    @property
    def name(self) -> str:
        return "model"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "model_list", "fn": self.model_list,
             "schema": self._s("列出所有可用模型", {})},
            {"name": "model_add", "fn": self.model_add,
             "schema": self._s("添加新模型到注册表（联网搜到新模型时使用）。如知道provider的base_url也一并提供", {
                 "provider": {"type": "string", "description": "提供商，如 openai / deepseek / groq"},
                 "name": {"type": "string", "description": "模型名，如 gpt-4o"},
                 "base_url": {"type": "string", "description": "API 地址，如 https://api.openai.com/v1"},
                 "api_key_env": {"type": "string", "description": "环境变量名，如 OPENAI_API_KEY"},
                 "tags": {"type": "string", "description": "逗号分隔标签，如 fast,cheap,vision"},
             }, ["provider", "name"])},
            {"name": "key_set", "fn": self.key_set,
             "schema": self._s("保存 API Key 到配置——用户给你 Key 时直接写入，不用让用户手动填设置页", {
                 "provider": {"type": "string", "description": "提供商：deepseek / openai / glm / groq 等"},
                 "api_key": {"type": "string", "description": "API Key"},
             }, ["provider", "api_key"])},
        ]

    def _load(self) -> dict:
        if not self._path.exists():
            return {"providers": {}}
        with open(str(self._path), "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _save(self, data: dict):
        with open(str(self._path), "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def model_list(self) -> str:
        data = self._load()
        current = data.get("current", "未知")
        lines = [f"当前: {current}", ""]
        for prov_name, prov in data.get("providers", {}).items():
            lines.append(f"📡 {prov_name} ({prov.get('base_url', '?')[:40]})")
            for m in prov.get("models", []):
                mark = " ← 当前" if m["name"] == current else ""
                tags = ", ".join(m.get("tags", []))
                lines.append(f"  {'⭐' if mark else '  '} {m['name']} [{tags}]{mark}")
        return "\n".join(lines)

    def model_add(self, provider: str, name: str, base_url: str = "",
                  api_key_env: str = "", tags: str = "") -> str:
        data = self._load()
        provs = data.setdefault("providers", {})
        prov = provs.setdefault(provider, {"models": []})
        if base_url:
            prov["base_url"] = base_url
        if api_key_env:
            prov["api_key_env"] = api_key_env
        # 去重
        existing = [m for m in prov["models"] if m["name"] == name]
        if existing:
            return f"⚠️ {provider}/{name} 已存在"
        prov["models"].append({
            "name": name,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
        })
        self._save(data)
        return f"✅ 已添加 {provider}/{name}" + (f" [{tags}]" if tags else "")

    def key_set(self, provider: str, api_key: str) -> str:
        """保存 API Key 到 default.yaml。"""
        # provider → config key 映射
        key_map = {
            "deepseek": "api_key",
            "openai": "openai_api_key",
            "glm": "glm_api_key",
            "zhipu": "glm_api_key",
            "zhihu": "zhihu_api_key",
        }
        config_key = key_map.get(provider.lower(), f"{provider.lower()}_api_key")

        try:
            if not self._main_config.exists():
                return f"❌ 配置文件不存在: {self._main_config}"
            data = yaml.safe_load(open(str(self._main_config), "r", encoding="utf-8")) or {}
            data.setdefault("llm", {})[config_key] = api_key
            yaml.dump(data, open(str(self._main_config), "w", encoding="utf-8"),
                     allow_unicode=True, default_flow_style=False, sort_keys=False)
            return f"✅ {provider} Key 已保存到配置（键: llm.{config_key}）"
        except Exception as e:
            return f"❌ 保存失败: {e}"
