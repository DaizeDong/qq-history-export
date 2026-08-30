# qq-history-export

把经典版手机 QQ（`com.tencent.mobileqq`，QQ NT 之前的 8.x 系）留在设备上的本地聊天记录，从一台已 root 的安卓机或模拟器里导出成结构化 JSON。

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![基于 Frida](https://img.shields.io/badge/%E5%9F%BA%E4%BA%8E-Frida%2016.x-green?style=flat)](https://frida.re)
[![语言](https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-EN%20%2F%20CN-blue?style=flat)](#语言)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.0-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## ⭐ 先读这个, 设计理念

经典版手机 QQ 的消息库就是一个普通的 SQLite 文件，任何 SQLite 阅读器都能打开、列出表。真正拦路的只有一件事：每条消息的正文列和账号列都被一段很短的、循环复用的密钥做了 XOR 混淆。所以这个 skill 的核心价值，不在于"它导出了聊天记录"，而在于**它把那段密钥从正在运行的客户端里现取回来**，然后剩下的一切都在离线完成。

密钥不是硬编码的，也不该硬编码，因为它按机器、按安装而变。恢复它的办法很直接：客户端自己在 Java 堆里保存着每条消息的明文（`com.tencent.mobileqq.data.MessageFor*` 实例的 `msg` 字段），同时数据库里存着同一条消息的密文。用 Frida 挂上运行中的进程，把某条消息的 uniseq 对上数据库里那一行，拿明文和密文逐字节 XOR，密钥就直接读出来了。一次取到，全程复用。

它对**边界**也是诚实的。聊天记录是一个人最私密的东西，一对一的对话、群里的每句话都在里面。这个 skill 从头到尾把这些当作 DATA：拉下来的数据库、解出来的每一条消息，都绝不进入这个仓库，只落在仓库之外的私有目录里。仓库里能公开的只有代码、文档，和一份纯合成的测试数据。

## 定位与边界

**它是** 一个一次性的本地取证式导出工具：指向一台你有 root 权限、且装着经典版手机 QQ 的设备，把它本地的消息库拉出来，用现取的密钥离线解码，得到一份按会话组织好的 JSON。

**它不是** 云端抓取、不是登录别人账号的办法、也不碰 QQ NT。QQ NT 换成了另一套基于 SQLCipher 的存储（`nt_msg.db`），不在本工具范围内。它只处理你自己设备上、你自己账号本来就存着的那份本地记录。

## 安装

```
/plugin install github:DaizeDong/qq-history-export
```

或手动 clone 到 Claude 插件目录：

```bash
git clone https://github.com/DaizeDong/qq-history-export.git \
  ~/.claude/plugins/qq-history-export
```

## 环境要求

- 一台已 root 的安卓设备或模拟器（在 MEmu 上验证过）
- `adb`，且 `adb shell` 能拿到 root（模拟器上通常默认就是）
- `python`，其中 `frida` 这个包**必须钉在 16.x**（16.7.19 在 MEmu 上验证过）
- 设备上跑着 **16.x 版的 frida-server**

**为什么 frida 必须是 16.x**：frida 17 把内置的 Java bridge 拿掉了，而堆读取正是靠它去读 `MessageFor*` 实例的明文字段。用 frida 17，密钥就取不出来。设备端的 frida-server 和你本机的 `frida` 包要**同为 16.x**。

## 三步流程

不变量：只有第二步需要客户端在跑、需要联机；第一步只读，第三步纯离线。所有产物路径都写在仓库之外。

**第一步，拉库（只读）。** 用 `adb` 把 `/data/data/com.tencent.mobileqq/databases/<uin>.db` 拷出来。它只读，不改设备上任何东西；用的是普通 `adb shell`（模拟器上它已是 root），而不是 `su -c`，因为后者可能挂住。跑完会打印出这个库属于哪个 uin。

```bash
python tools/qq_pull.py --serial <adb serial> [--uin <n>] --out <仓库之外的路径>
```

**第二步，取密钥（需要客户端在运行、需要联机）。** 用 Frida 挂上正在跑的 QQ，从 Java 堆里读出已解码的消息，把每条的 uniseq 对到数据库里那条密文行，拿对齐的明文/密文逐字节 XOR，直接读出循环密钥。跑完打印 `recovered key: <key> (period N, coverage M%)`。这一步之后就全离线了。

```bash
python tools/qq_keyfind.py --db <拉下来的 db> --host 127.0.0.1:27044 [--pid 0] [--seconds 20]
```

**第三步，解码（纯离线）。** 打开那份明文 SQLite 库，用密钥把 `msgData` 和几个账号列解开，逐条分类，每条文本消息写成一个 JSON 对象。它**拒绝往仓库里写**，而且如果密钥覆盖不到 90% 的消息就中止（防止把只解对了前几个字符的半吊子结果当成成品）。

```bash
python tools/qq_decode.py --db <db> --key <key> --owner <uin> --out <仓库之外的 jsonl>
```

密钥的周期是关键：实测是 15 个字节，把一段更短的前缀当成整段密钥，只会解对每条消息开头的几个字。所以密钥是每次运行现取的，由 `qq_keyfind` 负责，不写死。

## 工作原理

完整的逆向记录在 [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) 里，这里只讲骨架。数据库是普通 SQLite，前十六字节就是字面量 `SQLite format 3\0`，没有整库加密。每个会话一张表，按对端标识的 md5 命名：私聊是 `mr_friend_<大写 md5(好友账号)>_New`，群聊是 `mr_troop_<大写 md5(群号)>_New`。一条文本消息的 `msgtype` 是 `-1000`，正文在 `msgData` 里。`msgData` 和账号列（`senderuin`、`selfuin`、`frienduin`）都是明文 XOR 那段循环密钥。密码学细节、逐字节的对照、以及为什么周期是 15，都在那份文档里，不在这里复述。

## 测试与合成数据

`tools/make_fixtures.py` 造一个合成数据库（假账号 10000/10001、合成密钥 `SYNTHKEY01234AB`、一眼假的文本），让 `tools/test_qq.py` 在零真实数据的前提下跑完整个往返。仓库里公开的、跟数据沾边的东西，只有这一份合成 fixture。

## 数据边界（不可让步）

拉下来的数据库、解出来的每一条消息，都是 DATA，在 `.dataclass.json` 里声明过，**永远不进这个仓库**。仓库里只发合成 fixture。所有会落数据的目录（`qq_db_pull/`、`qq_export/`、`qq_json/`、`qq_organized/`）都已声明并封死，就算 `git add -f` 也进不来。真实产物只落在仓库之外的私有目录（`~/.qq-history-export-config/data/`，可用 `$QQ_HISTORY_EXPORT_DATA_DIR` 覆盖）。

这条规则连文档和示例也一起管：任何文档、任何例子里，都**绝不**出现真实的账号、真实的消息、或任何真实的个人信息。需要举例，就用仓库里已有的合成值：账号 `123456789` 或 `10000`、好友 `10001`、群 `20001`；需要一条示例消息，就编一条一眼假的。

## 语言

English (`README.md`) · 中文 (`README_CN.md`)

## Roadmap · 更新日志 · License

见 [ROADMAP.md](ROADMAP.md) · [CHANGELOG.md](CHANGELOG.md) · [LICENSE](LICENSE)（MIT）。
