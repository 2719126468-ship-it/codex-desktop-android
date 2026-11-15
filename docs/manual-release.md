# 手动构建包含环境的 APK

工作流为 `.github/workflows/manual-full-apk.yml`，只有 `workflow_dispatch`。
推送代码、提交 PR、创建标签和定时任务都不会触发；本地修改工作流也不会启动构建。

首次使用时，在仓库 **Settings → Secrets and variables → Actions** 配置：

| Secret | 内容 |
| --- | --- |
| `CODEX_KEYSTORE_BASE64` | 原签名 keystore 文件的 Base64 内容，必填；不要提交密钥文件 |
| `CODEX_SIGNING_STORE_PASSWORD` | keystore 密码；省略时使用 Android 标准 debug 密码 |
| `CODEX_SIGNING_KEY_ALIAS` | 签名条目别名；省略时为 `androiddebugkey` |
| `CODEX_SIGNING_KEY_PASSWORD` | 条目密码；省略时使用 Android 标准 debug 密码 |

签名证书须匹配 `config/android/native-baseline.json`，以便覆盖升级现有安装。
发布使用工作流自己的 `GITHUB_TOKEN`，无需把个人 GitHub token 写进源码或 Secret。

进入 **Actions → Build full APK (manual) → Run workflow**，选择：

| 参数 | 含义 |
| --- | --- |
| `engine_ref` | `latest` 解析上游最新稳定后端标签；`supported` 采用当前恢复清单；也可指定版本号或 `rust-v…` 标签 |
| `desktop_version` | `latest` 采用官方签名 ARM64 软件索引中的最新版本；也可指定索引中仍提供的版本 |
| `rust_toolchain` | 默认安装当前 Rust 稳定版；也可指定所选后端需要的精确编译器版本，实际版本写入构建记录 |
| `version_code` | 可填写更大的 Android 版本号；留空为源码版本号加工作流运行编号 |
| `release_tag` | 可填写新的 Release 标签；留空为 `v<versionCode>`；已有标签和 Release 不会被覆盖 |

版本在构建开始时解析并冻结到构建记录，构建中途不会继续追踪 `latest`。
新版后端仍需能应用仓库的 Android 补丁，新版前端仍需通过 ASAR 适配校验。
不兼容时工作流失败并保留日志，不会悄悄回退旧版本，也不会取消校验来强行发布。
后续需要迁移补丁时，更新 `recovery/engine/manifest.json` 与配套补丁即可；GNU 构建器没有另藏固定提交号。

首版从 `config/android/native-baseline.json` 指定的已发布 APK 校验并复用原生 JNI、执行器和 Python 载荷；
Codex GNU 后端、Mesa 和干净 Debian 环境在云端构建。原生载荷必须与当前源码清单相符，否则拒绝构建。
因此需保留该基线 Release 的 APK，且不能将这一流程称为全部原生组件从源码重建。

完整 APK 内置环境包与对应校验清单，首次启动直接流式解压、创建本机账户和密钥环。
已有 Linux 环境继续保留，不会因为内置了新环境包就重置项目或登录信息。
发布前校验 APK 内容、原签名和上传摘要；通过后自动公开 Release，并使用
`config/android/release-notes.txt` 中的说明，同时附带 `build-info.json` 和 `SHA256SUMS`。
未通过的上传保留为草稿；小体积日志保留七天，不上传签名密钥或手机数据。

首版尚需一次实际 Actions 构建与新设备首次安装验证。工作流成功不等于通过真机测试。
完整镜像含官方桌面客户端；公开分发前需按其适用条款处理，仓库的开源许可证不授予该客户端的再分发权。
