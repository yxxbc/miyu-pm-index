# yxxbc/miyu-pm-index template

这是 miyu-pm 的**标准索引仓库模板**，目标发布到：

```text
https://github.com/yxxbc/miyu-pm-index
```

## 结构

```text
.
├── .github/workflows/collect.yml   # 定时扫描 + 生成索引
├── tools/
│   ├── collect.py                  # 发现/校验/生成逻辑
│   └── requirements.txt
├── schemas/
│   └── miyu-package.schema.json    # miyu-package.yaml 规范
├── index.json                      # 聚合索引（Actions 自动生成）
├── packages/<name>.json            # 每包完整规范化信息
├── security/reviews/<name>/        # 社区 miyu 安全分析报告
└── _errors/<repo>.json             # 收录失败原因
```

## 收录约定

插件作者只需：

1. 在 GitHub 仓库默认分支根目录放 `miyu-package.yaml`；
2. 仓库名以 **`miyu-pm`** 开头（例如 `miyu-pm-bili-summary`）。

索引仓库的 GitHub Actions 每天 UTC 02:00 自动搜索名称以 `miyu-pm` 开头的
仓库，拉取并校验 `miyu-package.yaml`，重新生成 `index.json` 与
`packages/*.json`，然后**自动创建 PR**；由仓库维护者审核后手动合并。

## 本地生成/测试

```bash
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt

# 从本地目录生成（每个目录含 miyu-package.yaml）
.venv/bin/python tools/collect.py \
  --schema schemas/miyu-package.schema.json \
  --out /tmp/miyu-index-out \
  --local ../examples/bili-summary ../examples/mi-fitness-mcp
```

## 安全

自动收录**不代表官方背书**。`collect.py` 会做静态预检：

- manifest 是否符合 JSON Schema；
- 路径是否包含绝对路径 / `..` 逃逸；
- env 是否出现疑似明文密钥；
- setup 命令是否含常见危险关键字。

预检结果写入 `security.static_checks`；更深入的社区 miyu 分析报告后续通过
`miyu-pm report submit` 汇总到 `security/reviews/`。
