# 📦 miyu-pm-index

> miyu 第三方扩展标准索引仓库

[![Collect Registry](https://github.com/yxxbc/miyu-pm-index/actions/workflows/collect.yml/badge.svg)](https://github.com/yxxbc/miyu-pm-index/actions/workflows/collect.yml)
[![License: MIT](https://img.shields.io/github/license/yxxbc/miyu-pm-index)](LICENSE)

---

## 这是什么

这是 [`miyu-pm`](https://github.com/yxxbc/miyu-pm) 的官方扩展索引仓库。

GitHub Actions 每天自动扫描仓库名以 **`miyu-pm`** 开头的 GitHub 仓库：

1. 读取仓库根目录的 `miyu-package.yaml`
2. 按标准格式校验
3. 运行静态安全预检
4. 生成 `index.json` 与 `packages/<name>.json`
5. **自动创建 PR**，由维护者审核合并

`miyu-pm` 用户通过本仓库的 `index.json` 搜索和安装扩展。

## 📖 文档

- [📖 插件作者指南](PACKAGE_AUTHOR_GUIDE.md)
- [📦 可用包聚合列表](PACKAGES.md)（自动生成，方便人看）

---

## ⚡ 在线安装 miyu-pm

如果还没安装 `miyu-pm`，一行命令即可安装：

```bash
curl -fsSL https://raw.githubusercontent.com/yxxbc/miyu-pm/main/install.sh | sh
```

安装后 `miyu-pm` 默认会自动连接本仓库的线上索引，无需手动配置。

---

## ✍️ 如何发布你的扩展

### 1. 仓库命名

仓库名必须以 **`miyu-pm`** 开头，例如：

```text
miyu-pm-bili-summary
miyu-pm-some-skill
```

### 2. 添加 `miyu-package.yaml`

放在仓库默认分支根目录。最小示例（Script 包）：

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

更多类型示例：

```bash
# 克隆本仓库后可以查看 examples/
ls examples/
```

完整字段说明见 [`schemas/miyu-package.schema.json`](schemas/miyu-package.schema.json)。

### 3. 等待自动收录

每天 UTC 02:00 自动扫描；也可以到
[Actions](https://github.com/yxxbc/miyu-pm-index/actions)
手动触发 `collect-registry` 立即收录。

收录结果会以 PR 形式出现，合并后即可被 `miyu-pm` 安装：

```bash
miyu-pm source add --name official \
  https://raw.githubusercontent.com/yxxbc/miyu-pm-index/main/index.json
miyu-pm update
miyu-pm search your-package
miyu-pm install your-package
```

### 没被收录 / PR 没合并怎么办？

可以直接使用**自建源（tap 思路）**：

1. Fork 本仓库，或新建一个自己的索引仓库；
2. 按相同格式加入你要分发的包；
3. 把 `index.json` 的 raw 地址给用户：

```bash
miyu-pm source add --name my-source \
  https://raw.githubusercontent.com/<owner>/<repo>/main/index.json
miyu-pm update
miyu-pm install your-package
```

---

## 🔒 安全模型

自动收录**不代表官方背书**。

每个包收录时都会经过静态预检：

- ✅ `miyu-package.yaml` 符合 Schema
- ✅ 路径没有绝对路径 / `..` 逃逸
- ✅ env 没有疑似明文密钥
- ✅ setup 命令没有常见危险关键字

预检结果写入包记录的：

```json
{
  "security": {
    "trust": "community",
    "static_checks": {
      "status": "passed"
    }
  }
}
```

社区 miyu 自动安全分析报告（`miyu-pm audit` / `report submit`）后续将汇总到
`security/reviews/`。

---

## 📁 目录结构

```text
.
├── .github/workflows/collect.yml   # 自动收录工作流
├── tools/collect.py                # 扫描 / 校验 / 生成索引
├── schemas/
│   └── miyu-package.schema.json    # 包描述格式规范
├── index.json                      # 聚合索引（自动生成）
├── packages/<name>.json            # 每个包的详情（自动生成）
├── security/reviews/               # 社区安全分析报告
└── _errors/                        # 收录失败记录
```

---

## 🧑‍💻 本地开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt

# 用本地示例生成索引
.venv/bin/python tools/collect.py \
  --schema schemas/miyu-package.schema.json \
  --out /tmp/index-out \
  --local ../examples/bili-summary ../examples/some-skill
```

---

## 📄 License

[MIT](LICENSE)
