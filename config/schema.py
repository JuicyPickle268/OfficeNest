"""
配置模型：dataclass + YAML 加载。
不依赖 pydantic，只用标准库。
"""
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import os


@dataclass
class AppConfig:
    name: str = "Mother"
    env: str = "dev"
    log_level: str = "INFO"


@dataclass
class FeishuConfig:
    app_id: str = ""
    app_secret: str = ""
    enable_websocket: bool = False


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    max_rounds: int = 20  # 工具调用最大轮次，0=无限（靠用户中断兜底）
    context_rounds: int = 0  # 上下文轮数，0=无限
    temperature: float = 0.3
    glm_api_key: str = ""  # 智谱 GLM 视觉模型
    sense_api_key: str = ""  # 商汤 SenseTime 视觉（备用）
    zhihu_api_key: str = ""  # 知乎搜索 API
    kb_use_deepseek: bool = False
    lang: str = "zh"  # zh/en


@dataclass
class OfficeConfig:
    workbooks_dir: str = "./workbooks"
    templates_dir: str = "./templates"
    output_dir: str = "./output"
    auto_backup: bool = True
    confirm_dangerous: bool = True
    auto_preview_word: bool = True  # Word操作后自动预览


@dataclass
class StorageConfig:
    db_path: str = "./data/mother.db"


@dataclass
class PanelConfig:
    window_title: str = "Mother 控制台"
    window_size: tuple = (900, 600)
    refresh_interval_ms: int = 1000


@dataclass
class Config:
    """聚合配置根"""
    app: AppConfig = field(default_factory=AppConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    office: OfficeConfig = field(default_factory=OfficeConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    panel: PanelConfig = field(default_factory=PanelConfig)


def load_config(yaml_path: str = "config/default.yaml") -> Config:
    """
    加载 YAML 配置文件，环境变量可覆盖。
    优先级：环境变量 > YAML > dataclass 默认值
    """
    raw = {}
    config_path = Path(yaml_path)
    # 配置文件不存在时从模板创建
    if not config_path.exists():
        example = config_path.with_suffix(".yaml.example")
        if example.exists():
            import shutil
            shutil.copy(example, config_path)
            raw = yaml.safe_load(open(yaml_path, "r", encoding="utf-8")) or {}
    else:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    def _get(section: str, key: str, default):
        env_key = f"MOTHER_{section.upper()}_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return type(default)(env_val)
        return raw.get(section, {}).get(key, default)

    # 处理 window_size 的 YAML 列表 → tuple 转换
    raw_panel = raw.get("panel", {})
    window_size = tuple(raw_panel.get("window_size", [900, 600]))

    return Config(
        app=AppConfig(
            name=_get("app", "name", "Mother"),
            env=_get("app", "env", "dev"),
            log_level=_get("app", "log_level", "INFO"),
        ),
        feishu=FeishuConfig(
            app_id=_get("feishu", "app_id", ""),
            app_secret=_get("feishu", "app_secret", ""),
            enable_websocket=_get("feishu", "enable_websocket", False),
        ),
        llm=LLMConfig(
            provider=_get("llm", "provider", "deepseek"),
            api_key=_get("llm", "api_key", ""),
            model=_get("llm", "model", "deepseek-chat"),
            base_url=_get("llm", "base_url", "https://api.deepseek.com/v1"),
            max_rounds=int(_get("llm", "max_rounds", 8)),
            context_rounds=int(_get("llm", "context_rounds", 0)),
            temperature=float(_get("llm", "temperature", 0.3)),
            glm_api_key=_get("llm", "glm_api_key", ""),
            sense_api_key=_get("llm", "sense_api_key", ""),
            zhihu_api_key=_get("llm", "zhihu_api_key", ""),
        ),
        office=OfficeConfig(
            workbooks_dir=_get("office", "workbooks_dir", "./workbooks"),
            templates_dir=_get("office", "templates_dir", "./templates"),
            output_dir=_get("office", "output_dir", "./output"),
            auto_backup=_get("office", "auto_backup", True),
        ),
        storage=StorageConfig(
            db_path=_get("storage", "db_path", "./data/mother.db"),
        ),
        panel=PanelConfig(
            window_title=_get("panel", "window_title", "Mother 控制台"),
            window_size=window_size,
            refresh_interval_ms=int(_get("panel", "refresh_interval_ms", 1000)),
        ),
    )
