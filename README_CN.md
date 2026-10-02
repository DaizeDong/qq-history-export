# qq-history-export

导出经典移动版 QQ 的文本记录，先验证数据库快照和密钥证据，全部解码成功后再替换归档。

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#languages)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.0-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

## ⭐ 先读这里，设计理念

SQLite 文件能打开，不代表消息解码正确。错误的短 XOR 密钥也可能得到合法 UTF-8。
工具要求两条不同的已知明文，每条覆盖完整密钥周期，再核对解码后的账号和发送者字段。
UTF-8 合法率只表示解码覆盖率，不能证明密钥正确。

原始数据库、恢复证据和消息都属于私有运行数据，存放在独立的 PRIVATE 伴生仓并纳入版本管理。
写入前会验证目标仓。传输或解码失败时保留原归档。

## 适用范围和依赖

支持经典移动版 QQ（`com.tencent.mobileqq`，NT 之前的 8.x）文档所述结构。QQ NT 和其他结构会被拒绝。
需要已有 root 的 Android 设备或模拟器、adb、正在运行的 QQ，以及两端匹配的 Frida 16.x Java bridge。
工具不会安装 root，也不会启动或停止应用。具体设备的兼容性需要单独验证。

本机需要 Python 3.11 或更新版本、Git 和已认证的 `gh`；设备需要 `sha256sum`。
存在非空 WAL 或回滚日志时不能直接复制，须先取得稳定快照。

## 安装

```bash
git clone --recurse-submodules https://github.com/DaizeDong/qq-history-export.git
```

从真实克隆位置加载 `skills/qq-history-export/SKILL.md`，以下命令在仓库根目录运行。

## Config

将 `QQ_HISTORY_EXPORT_CONFIG` 指向单独克隆的 PRIVATE 伴生仓，先创建其中的 `data/` 目录。
也可用 `QQ_HISTORY_EXPORT_DATA_DIR` 直接指定该数据目录。路径由固定版本的 guard 解析，
Git 和 `gh` 验证实际目标仓。公开、未知可见性、未纳入版本管理的目录均拒绝写入。
真实记录在私有伴生仓提交，凭据仍留在 Git 之外。

## 快速开始

说“帮我导出经典 QQ 聊天记录”即可开始。技能先复用已保存的存储和设备选择，只集中补问缺失信息。
设备操作遵循当前导出请求的授权范围。完整步骤和失败恢复方式见 [工作流](docs/WORKFLOW.md)。

下面的输出路径相对于私有数据目录；账号 `10000` 是合成示例，请使用本次选定的账号。

```bash
python tools/qq_pull.py --uin 10000 --out qq_db_pull/candidate.db
python tools/qq_keyfind.py --db qq_db_pull/candidate.db --owner 10000 --out qq_keys/recovery.json
python tools/qq_decode.py --db qq_db_pull/candidate.db --evidence qq_keys/recovery.json --out qq_json/messages.jsonl
```

拉取必须使用新路径。每次 adb 调用都检查退出状态和超时，比较源文件与本地快照哈希，验证 SQLite，
再清理设备上的唯一临时文件。此时 `owner_verified=false`，账号字段会在密钥恢复后验证。
密钥保存在私有证据包，不打印到终端，也不需要粘贴进命令参数。

证据包包含密钥和已知明文，应视作私有聊天数据。恢复和解码先在私有目录冻结数据库副本，
校验、账号核对和导出使用同一份字节。原始数据库发生变化或出现新的日志活动时，拒绝替换归档。
消息标识必须是有符号 64 位整数，并在支持的文本记录中保持唯一。输出及其锁文件不能占用
数据库、SQLite 旁文件或恢复证据的位置。

替换前的证据错误、数据库损坏、部分解码和写入失败都会保留旧归档。若替换已经成功，但锁文件
清理失败，命令返回非零状态及 JSON 回执 `committed_cleanup_required`、`committed: true`。
此时新产物已经存在，应先检查回执列出的清理路径。`failed_cleanup_required` 且
`committed: false` 表示尚未替换。

## 输出和限制

每行记录含 `text`、`is_me`、`ctx`、`ts`、`sender`、`conv` 和 `uniseq`。终端输出数量、
账号验证、密钥证据状态、数据库哈希与解码覆盖率。附件及非文本消息不在范围内。

证据包是本地观察记录，不是 QQ 签名证明。使用外来证据包前应确认来源。
合成测试通过不代表真实账号历史完整，也不能证明任意客户端版本或设备都能成功恢复密钥。

## 离线测试

```bash
python -m pytest tools -q
python tools/test_qq.py
```

测试数据库全部由 `tools/make_fixtures.py` 生成，设备和 Frida 调用均由测试替身接管。
无需真实账号。[逆向说明](docs/REVERSE_ENGINEERING.md) 记录数据库结构与混淆模型。

## Languages

中文 (`README_CN.md`) 和 English (`README.md`，权威版)。

## 路线图和许可

[ROADMAP.md](ROADMAP.md) · [CHANGELOG.md](CHANGELOG.md) · [MIT](LICENSE)。
