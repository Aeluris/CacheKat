# CacheKat 🐈

[English](README.md) | [中文](README.zh-CN.md)

[![ci](https://github.com/Aeluris/CacheKat/actions/workflows/ci.yml/badge.svg)](https://github.com/Aeluris/CacheKat/actions/workflows/ci.yml)
[![pypi](https://img.shields.io/pypi/v/cachekat?label=PyPI)](https://pypi.org/project/cachekat/)
[![python](https://img.shields.io/pypi/pyversions/cachekat)](https://pypi.org/project/cachekat/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> 一条 TUI 看清开发机的磁盘都被哪些缓存吃了——按风险分级安全回收。
> **永远不碰你的数据。**

**主界面**（左：可清项，`space` 勾选、`c` 执行；右：只报不动的事实，
看得见摸不得——布局本身就在讲安全模型）与**确认门**（不点头绝不清理；
每条写明后果；干跑 `d` 彩排，磁盘分毫不动）：

| 主界面 | 确认门 |
|:---:|:---:|
| ![主界面](https://raw.githubusercontent.com/Aeluris/CacheKat/main/docs/screenshots/zh-main.png) | ![确认门](https://raw.githubusercontent.com/Aeluris/CacheKat/main/docs/screenshots/zh-confirm.png) |

## 为什么做

每台开发机都在默默囤缓存：pip 下载包、npm 缓存、playwright 浏览器
（每升一版就多一套）、docker 构建缓存、悬空镜像、停着的容器……
一次扫描回答唯一要紧的问题：**谁在吃磁盘？哪些真可以安全回收？**

## 安全模型（这是本命特性）

| 类别 | 行为 |
|---|---|
| 真缓存（pip、npm、playwright 孤儿、docker 构建缓存） | 可勾选清理——每条在执行前都写明白人话后果 |
| **docker 卷（你的数据）** | **只报不动，永不清理，没有旗标能解锁** |
| docker 停止容器／未用镜像 | 容器：**逐个勾选**，每条警示 `docker rm` 删除的是容器**本体**而非缓存（可用 `docker run`/`compose up` 重建，卷不受影响）。镜像：逐镜像勾选上线前只报不动。 |
| 探针判不了的 | 诚实只报（“判不了活性”），绝不瞎猜 |

- 扫描永远只读；清理必须是显式勾选＋确认门。
- 干跑模式（`d`）：先彩排会发生什么——磁盘分毫不动。
- 探针失败以可见错误行浮出，绝不吞掉装绿。

## 安装

```
pipx install cachekat
```

或从源码直装：`pipx install git+https://github.com/Aeluris/CacheKat.git`

## 使用

```
cachekat tui             # 交互式：扫描 -> 勾选 -> 确认 -> 清理
cachekat scan            # 只读报告：谁在吃磁盘
cachekat scan --json     # 机器可读
# 所有命令支持 --lang auto|en|zh（auto 跟随系统语言）
```

docker 相关行需要守护进程在运行——TUI 显示 `docker daemon unreachable`
时，启动 Docker Desktop 后按 `r` 重扫即可。

## 路线图

- [x] 内核：探针注册表、`scan` CLI、pip 探针、CI（Windows + Linux）
- [x] docker / npm / playwright 探针（孤儿检测、卷红线）
- [x] Textual TUI：勾选、确认、清理、干跑
- [x] 逐容器勾选＋“本体非缓存”警示
- [x] i18n：en/zh 全量，`--lang auto|en|zh`
- [ ] 逐镜像勾选、更多缓存家族（cargo、gradle、…）

详见 [CHANGELOG.md](CHANGELOG.md)；想参与看 [CONTRIBUTING.md](CONTRIBUTING.md)
（中文版待补）；工程规则在 [AGENTS.md](AGENTS.md)。

## 许可

[MIT](LICENSE) — © 2026 Aeluris
