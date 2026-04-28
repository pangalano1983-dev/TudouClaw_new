# LLM Provider Quirk Overlay

每个文件覆盖一个 provider 的类属性，文件名 = `<provider.name>.yaml`。

例如 `glm.yaml` 覆盖 `GLMProvider` 的字段。启动时如发现该 YAML 存在，会把里面声明的字段写到 provider 实例上。

## 可覆盖字段（白名单 `LLMProvider._OVERLAY_KEYS`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `hosts` | list[str] | URL 子串匹配关键词 |
| `drop_reasoning_content` | bool | 发送前删除 `reasoning_content` |
| `backfill_reasoning_content` | bool | 给每条 assistant 补 `reasoning_content: ""`（DeepSeek thinking-mode 必需） |
| `drop_empty_content_with_tools` | bool | assistant 同时有 tool_calls 且 content 为空时,把 content 字段删掉 |
| `coerce_list_content_to_string` | bool | list 形式的 content 强制转字符串 |
| `drop_assistant_name` | bool | 删 assistant 上的 `name` 字段 |
| `supports_parallel_tool_calls_param` | bool | 是否在 payload 里发 `parallel_tool_calls: true` |
| `max_tool_call_rounds` | int | 历史里最多保留几轮 `(asst+tool_calls, tool*)`,超过的折叠成 user 文本 |

## 例：用 YAML 临时给 Qwen 关闭并行 tool_call 字段

`qwen.yaml`：

```yaml
supports_parallel_tool_calls_param: false
max_tool_call_rounds: 1
```

不需要改 Python 代码。重启进程即生效。

## 适用场景

- 接到一个新的模型变体（如 `glm-4.5-air-vL` 行为变了），快速试改
- 操作员临时关闭某个怪癖修复来验证它是否还在生效
- 不同部署环境的同一 provider 行为略有差别

## 不适用场景

- 复杂逻辑（自定义 transform_message / 合成 content 等）——这些必须改 Python
- 加新 provider——必须写 Python class
