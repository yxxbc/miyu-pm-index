# 📖 miyu-pm 插件作者指南

> 面向想发布 miyu 扩展（MCP / Skill / Script）的仓库作者。

---

## 1. 仓库命名

想让 GitHub Actions **自动收录**，仓库名必须以 `miyu-pm` 开头：

```text
miyu-pm-bili-summary
miyu-pm-some-skill
```

如果仓库名不符合规则，也可以走 **curated / 自建源**，见第 6 节。

---

## 2. 放一个 `miyu-package.yaml`

放在仓库**默认分支根目录**。这是唯一必须遵守的机器可读规范。

### 最小示例：Script 包

```yaml
name: miyu-pm-demo-hello
display_name: Demo Hello
description: A short English description of what this tool does.
type: script
version: 0.1.0
license: MIT

script:
  files:
    - hello.py
```

### 最小示例：Skill 包

```yaml
name: miyu-pm-some-skill
display_name: 某技能
description: A short English description of when to use this skill.
type: skill
version: 0.1.0
license: MIT

skill:
  entry: SKILL.md
```

### 最小示例：MCP 包

```yaml
name: miyu-pm-some-mcp
display_name: Some MCP
description: A short English description of this MCP server.
type: mcp
version: 0.1.0
license: MIT

install:
  method: git
  runtime: python
  setup:
    - python3 -m venv .venv
    - .venv/bin/pip install -r requirements.txt

mcp:
  id: some-mcp
  command: "{root}/.venv/bin/python"
  args:
    - "{root}/server.py"
  env: {}
```

完整字段见 `schemas/miyu-package.schema.json`。

---

## 3. 必填字段

| 字段 | 说明 |
|---|---|
| `name` | 全小写，`^[a-z0-9][a-z0-9._-]*$` |
| `type` | `mcp` / `skill` / `script` / `plugin` |
| `version` | 语义化版本 `0.1.0` |
| `license` | 开源许可证 |
| `description` | 英文一句话说明 |

---

## 4. Script 包注意事项

- 每个要注册成工具的文件都要有 shebang 和头部注释契约；
- 示例：

```python
#!/usr/bin/env python3
# Display name: Hello
# Description: Print hello from miyu-pm demo.
print("hello")
```

- `script.files` 里的文件会复制到 `~/.miyu/data/scripts/` 并设为可执行。

---

## 5. 安全要求

不要做这些事：

- ❌ 在 `miyu-package.yaml` 里提交真实密钥；
- ❌ 在 `setup` 里写危险命令；
- ❌ manifest 路径使用 `..` 或绝对路径。

索引收录时会自动静态检查这些问题。

---

## 6. 没被自动收录 / PR 没合并怎么办

使用**自建源（tap 思路）**：

1. Fork `yxxbc/miyu-pm-index`；
2. 把你的包加入索引（或保留 `curated.json` 白名单机制）；
3. 用户添加你的源：

```bash
miyu-pm source add --name my-source \
  https://raw.githubusercontent.com/<owner>/<repo>/main/index.json
miyu-pm update
miyu-pm install your-package
```

---

## 7. 本地验证 manifest

```bash
git clone https://github.com/yxxbc/miyu-pm
cd miyu-pm

python3 -m venv .venv
.venv/bin/pip install -r registry-template/tools/requirements.txt

.venv/bin/python registry-template/tools/collect.py \
  --schema registry-template/schemas/miyu-package.schema.json \
  --out /tmp/validate \
  --local /path/to/your/repo
```

如果没有报错，说明 manifest 格式正确。
