# 清源单节点离线部署候选方案

> 当前适用：隔离内网、单节点、Docker Compose、PostgreSQL 17 的部署验证。项目仍是开发验证版本，不得用于真实业务或生产数据。尚需在目标操作系统、CPU 架构、Docker 版本、数据库、备份和安全边界验证后才能作为交付方案。

## 架构和边界

浏览器通过 `http://内网地址:8080` 访问 Nginx；Nginx 提供 Vue 构建后的静态文件，`/api/` 转发给 FastAPI。数据库和 API 不发布宿主机端口，位于 Compose 内部网络。没有运行 Vite 开发服务器；没有部署尚未实现的 Worker 和对象存储。

**没有证书意味着当前使用 HTTP 明文。** 密码、会话令牌和业务数据在网络中可能被窃听或篡改；离线并不自动提供链路加密。默认仅绑定 `127.0.0.1` 供本机验证。要开放给其他主机，必须由建设单位确认隔离网络和风险控制，正式业务应配置经批准的内网 TLS／受信证书或其他经批准的传输保护方案。本方案不凭无证书推定可以承载真实数据。

Compose 单机不提供高可用；服务健康检查只是启动／存活检查，不证明权限、账实、备份或整体可用性。`/api/health` 当前不检查数据库连接。现有 API 未完成角色／字段权限、RLS、登录限速、会话保护、审计归集及生产加固。

## A. 联网构建机：制作离线包

需要 Docker、Python、受控镜像来源和联网依赖源。选定并审核匹配目标 CPU 的 Python 3.12、Node 及 Nginx 镜像，PostgreSQL **必须选择 17 系列**；供应商确认后提供各镜像的完整 `name@sha256:...` 摘要。提前拉取 PostgreSQL 摘要镜像；构建时下载前端／Python 依赖，不在离线目标环境执行构建或下载。

在项目根目录运行（以下值为占位符，不可直接执行）：

```sh
python deploy/offline/make_bundle.py \
  --python-base 'python@sha256:<64位摘要>' \
  --node-base 'node@sha256:<64位摘要>' \
  --nginx-base 'nginx@sha256:<64位摘要>' \
  --postgres 'postgres@sha256:<64位摘要>' \
  --output /path/to/new-wellspring-bundle
```

构建机会生成 `images.tar`、部署配置、`manifest.json`、`SHA256SUMS` 和本文档，并输出 manifest 摘要。通过独立可信渠道提供 manifest 摘要给目标环境；仅与包一起携带的摘要无法证明来源。导出前应完成漏洞扫描、依赖与许可证审核、SBOM、镜像来源审核和目标架构验证。当前 Python 只锁定直接依赖，**还不是可复现的全量哈希锁**；不能将该构建脚本误称为已完成供应链生产验收。

## B. 离线目标机：检查并导入

以下以 Linux 为例，目标机需预装 Docker Engine、Compose、Python 3 和标准 `sha256sum`。目标路径、用户、目录权限和密钥管理由运维确认。命令在离线包目录执行；不要使用包含真实数据的环境做首次演练。

1. 核对独立渠道提供的 manifest 摘要与 `sha256sum manifest.json` 一致。
2. `sha256sum -c SHA256SUMS`，随后执行 `python3 verify_bundle.py`。出现错误立即停止。
3. `docker load -i images.tar`，执行 `python3 verify_bundle.py --loaded` 核对镜像 ID。
4. 将 `env.example` 复制到包外受控位置，例如 `/etc/wellspring/deploy.env`；确认 `SECRETS_DIR`、绑定地址、端口及镜像标签。必须避免覆盖已存在的配置。

校验可以检测文件与已知摘要不一致；摘要本身不是签名，不能替代制品来源审查。

## C. 密钥和首次初始化

在宿主机的受限目录准备 `db_owner_password` 和 `runtime_password` 两个 UTF-8 文本文件，每个只包含各自一个非空密码和可选结尾换行。使用强随机密码；目录、文件只授予启动服务所需账号和容器可读取权限。两个密码要不同，不能放进环境文件、命令历史、镜像、仓库或工单。Compose 的文件型 secrets 是本地文件挂载，**不是完整的密钥管理系统**，须按目标系统 UID、ACL 与备份制度验证；数据库首次初始化后修改文件不会自动更新数据库密码。

以 `deploy.env` 指定的密钥目录为准，以下 `CFG` 示例变量仅指配置文件路径：

```sh
CFG=/etc/wellspring/deploy.env
docker compose --env-file "$CFG" -f compose.yaml config --quiet
docker compose --env-file "$CFG" -f compose.yaml up -d db
docker compose --env-file "$CFG" -f compose.yaml --profile tools run --rm migrate
```

首次初始化时数据库容器创建迁移所有者 `wellspring_owner` 和非超级用户运行角色 `wellspring_app`；迁移建立表并收紧审计表修改权限。若初始化脚本失败，需检查日志、账户和持久化卷状态，不能对含数据的卷盲目删除重建。迁移使用所有者账号，API 和账号初始化使用运行账号；RLS 和生产角色完整矩阵尚未实现。

创建唯一的命名开发账号（交互式输入，不写入镜像或脚本）：

```sh
docker compose --env-file "$CFG" -f compose.yaml --profile tools run --rm bootstrap
```

然后启动服务：

```sh
docker compose --env-file "$CFG" -f compose.yaml up -d api web
docker compose --env-file "$CFG" -f compose.yaml ps
```

从获准的终端访问配置的地址，检查首页、`/api/health`、登录、权限和退出。健康检查不代替功能及安全测试。首次数据库初始化完成后，正常重启无需重新创建账号或执行迁移。

## D. 升级与恢复

先审查新版本的兼容性、迁移、密钥、配置及回滚说明；保存并测试数据库与相关文件的同一恢复点，再经批准停写。核验并加载新的离线包后，更新受控环境文件中的镜像引用；按版本手册先运行迁移，再启动新 API 和 Web，验证版本、核心流程、权限与审计。数据库迁移可能不可逆，恢复以已演练的备份／前向修复方案为准，不能仅回滚镜像标签。当前尚无对象存储，后续接入时必须纳入同一恢复点核对。

示例备份（输出属于敏感数据，目标目录需受控）：

```sh
docker compose --env-file "$CFG" -f compose.yaml exec -T db \
  pg_dump -U wellspring_owner -Fc wellspring > /secure-backup/wellspring.dump
```

恢复必须在隔离环境先演练，记录 PostgreSQL 版本、备份时间、角色、密钥、数据完整性和实际恢复耗时；未经演练不要对现有生产库直接执行恢复。`docker compose down -v` 会删除数据库卷，不应作为日常停止、升级或故障处理步骤。

## 当前交付缺口

- 尚未在目标机完成镜像构建、离线导入、数据库初始化、角色权限和端到端联调。
- 未提供全量依赖哈希锁、SBOM、漏洞扫描、正式密钥管理及签名。
- 未实现 Worker、对象存储、独立受保护审计、正式认证／RLS、监控及数据库完整备份恢复演练。
- API 当前健康接口不检查数据库可用性；应用不应以健康接口成功作为完整业务可用的证明。
