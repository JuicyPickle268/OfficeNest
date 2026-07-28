# config/ — 配置层

## 文件

| 文件 | 说明 |
|------|------|
| `default.yaml` | 默认配置模板，所有配置项都在这里定义 |
| `schema.py` | dataclass 配置模型 + YAML 加载函数 |

## 使用方式

```python
from config.schema import load_config

cfg = load_config("config/default.yaml")
print(cfg.app.name)         # "Mother"
print(cfg.llm.model)        # "deepseek-chat"
print(cfg.office.workbooks_dir)  # "./workbooks"
```

## 环境变量覆盖

所有配置项都可以用环境变量覆盖：

```
MOTHER_LLM_API_KEY=sk-xxx
MOTHER_FEISHU_APP_ID=cli_xxx
MOTHER_OFFICE_WORKBOOKS_DIR=D:\MyDocs
```

命名规则：`MOTHER_{SECTION}_{KEY}`（全大写）。

## 添加新配置项

1. 在 `default.yaml` 中增加配置项
2. 在 `schema.py` 中对应的 dataclass 增加字段
3. 在 `load_config()` 中增加对应的 `_get()` 调用
