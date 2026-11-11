# 清源单节点离线部署候选方案

当前用于隔离环境、单节点 Docker Compose + PostgreSQL 17 的虚构数据验证。正式业务仍需完成角色权限、网络传输保护、审计归集及目标环境验收。Windows 命令见 [Windows 离线部署步骤](WINDOWS.md)。

当前源码产品版本为 `0.0.5`，Compose 与环境示例默认引用 `wellspring/app:0.0.5`；修改标签不会更新已经构建或运行的镜像，须重新制作并核验镜像包。数据库 head 为 `0021`，升级与本次验证见 [0.0.5 版本说明](../../docs/0.0.5-版本说明.md)。

## 架构与可用性

同一应用容器提供 Vue 静态页面和 FastAPI；独立 PostgreSQL 容器使用持久卷，数据库不开放宿主机端口。入口默认 `http://127.0.0.1:8080`。跨机访问必须配置经批准的 TLS 和访问控制，隔离网络不等于链路加密。

`/api/health` 仅用于进程存活；Compose 使用 `/api/ready` 检查数据库连接和迁移版本，失败返回 503。就绪检查不证明业务权限或数据恢复通过。单节点没有高可用保证。

## 1. 联网构建机制作镜像包

审核并固定 Python 3.12、Node 和 PostgreSQL **17** 镜像完整摘要，提前获取与目标平台一致的 PostgreSQL 镜像。数据库镜像须包含 Bash 及官方 `/usr/local/bin/docker-entrypoint.sh`。以下摘要是占位符：

```sh
python deploy/offline/make_bundle.py \
  --python-base 'python@sha256:<64位摘要>' \
  --node-base 'node@sha256:<64位摘要>' \
  --postgres 'postgres@sha256:<64位摘要>' \
  --platform linux/amd64 \
  --output /path/to/new-wellspring-bundle
```

构建只复制允许的源文件到独立上下文；数据库、备份、`.env`、依赖目录和测试产物不会进入该上下文。Python 按 `requirements.lock` 的完整哈希安装，前端执行 `npm ci`。构建时需要联网，离线目标环境只加载制品。

包内包含 `images.tar`、配置和 `manifest.json`。清单格式为 2，记录产品版本、平台、源码提交和未提交标记、实际构建输入摘要、两类依赖锁摘要、基础镜像摘要和输出镜像 ID。当前工作区未提交改动会进入构建，Git 提交号本身不代表实际制品；`build_inputs_sha256` 记录此次实际输入。全量依赖锁不替代许可证、漏洞、SBOM 和制品来源审查。

## 2. 建立可信校验链后再导入

**不要直接执行待验包里的 `verify_bundle.py`，也不要以待验包内 README 作为可信命令来源。** 首先通过独立可信渠道取得以下三项，并保存到包外受控目录：

- 本节经审核的操作步骤；
- `trusted_verify.py` 引导工具及其独立 SHA-256（构建机脚本会打印工具路径和摘要）；
- 本次 `manifest.json` 的独立 SHA-256。

`trusted_verify.py` 故意不放入镜像包；不能将同包携带的脚本或摘要当作独立来源。目标机使用可信系统 Python 3.12+ 和 `sha256sum`，在无非可信用户写权限的目录执行：

```sh
# 先将结果与独立渠道的工具摘要逐字核对；不一致立即停止。
sha256sum /opt/wellspring-tools/trusted_verify.py
# EXPECTED_MANIFEST 必须来自独立渠道，不从包内复制。
EXPECTED_MANIFEST='<独立确认的64位manifest摘要>'
python3 -I /opt/wellspring-tools/trusted_verify.py /srv/wellspring/bundle \
  --manifest-sha256 "$EXPECTED_MANIFEST"
```

引导工具先用可信标准库核验 manifest，再核验包内校验器的字节；只执行已经验证的字节。`-I` 阻止包内 `json.py`、`hashlib.py`、`sitecustomize.py` 或 `PYTHONPATH` 覆盖标准库。校验器严格检查全部文件名、文件摘要和符号链接，避免路径越界；不能省略 `-I`。操作期间目录必须保持受控，校验通过之前不执行任何包内代码。

```sh
docker load -i /srv/wellspring/bundle/images.tar
python3 -I /opt/wellspring-tools/trusted_verify.py /srv/wellspring/bundle \
  --manifest-sha256 "$EXPECTED_MANIFEST" --loaded
```

每一步失败立即停止。摘要链能检测与可信输入不一致，仍不能替代发布主体的数字签名和来源审查。

## 3. 配置、密钥与首次初始化

把 `env.example` 复制到包外受控路径（例如 `/etc/wellspring/.env`），填写镜像引用、端口和 `SECRETS_DIR`；禁止覆盖已存在配置。在密钥目录创建 `db_owner_password`、`runtime_password`，使用不同的强随机密码，限制目录和文件权限。密码文件必须为 **UTF-8 无 BOM**，仅一行；可以无结尾换行，或带一个 LF/CRLF，不能有多行、空密码或 NUL。空格是密码的一部分。

数据库启动包装器在内存文件系统中统一规范化两份密钥，再交给 PostgreSQL 官方入口；应用使用相同规则。首次初始化后更改文件不会修改数据库内的账号密码。已有旧环境若曾把 CR 错存入密码，必须人工轮换数据库密码并同步文件，不能删除数据库卷解决。

```sh
CFG=/etc/wellspring/.env
cd /srv/wellspring/bundle
docker compose --env-file "$CFG" -f compose.yaml config --quiet
docker compose --env-file "$CFG" -f compose.yaml up -d db
docker compose --env-file "$CFG" -f compose.yaml --profile tools run --rm migrate
docker compose --env-file "$CFG" -f compose.yaml --profile tools run --rm bootstrap bootstrap --initial-admin
docker compose --env-file "$CFG" -f compose.yaml up -d app
docker compose --env-file "$CFG" -f compose.yaml ps
```

初次创建数据库时建立 `wellspring_owner` 和非特权 `wellspring_app`。迁移使用所有者，每次迁移完成后按显式表权限矩阵授权：重量及审计等历史事件只允许 SELECT/INSERT；普通业务表允许必要写入；sessions 允许退出删除；alembic_version 只允许 SELECT；新表默认不授权。新模块必须同时补权限矩阵和 PostgreSQL 角色测试。此矩阵不等于正式岗位、字段权限或 RLS。

`bootstrap` 交互输入命名账号和至少 12 位密码，管理员只允许首次初始化。初始化失败需检查日志、角色和卷状态，不能盲目重建卷。正常启动只需 `docker compose --env-file "$CFG" -f compose.yaml up -d`；停止使用 `stop`，不要使用删除数据卷的 `down -v`。

## 4. 备份与隔离恢复演练

只有在前述校验全部通过后，才能运行包内工具。备份目标应在受控目录，命令使用 Python 二进制管道，避免 Windows PowerShell 文本重定向损坏 dump：

```sh
python3 -I backup_restore.py backup --env-file "$CFG" \
  --output /secure-backup/wellspring-2026-11-11.dump
python3 -I backup_restore.py drill \
  --dump /secure-backup/wellspring-2026-11-11.dump \
  --sha256 '<核对备份摘要文件中的64位值>' \
  --postgres-image wellspring/postgres:17-offline \
  --report /secure-backup/restore-drill-2026-11-11.json
```

`backup` 不覆盖现有文件，产生自定义格式 dump 和 SHA-256。`drill` 在名称随机、无网络、无宿主机端口、无现有数据卷挂载的临时 PostgreSQL 容器中真正恢复；检查 `pg_restore` 退出状态、迁移版本、每张表计数及证物余额与重量流水一致性，并输出版本、镜像 ID、恢复耗时和摘要。无论成功失败都删除本次创建的演练容器；不修改源数据库或现有部署。恢复库在内存文件系统，需预留足够内存，较大数据应按经审核的隔离存储方案另行演练。

报告不代替应用权限与业务验收；本工具恢复时跳过源 ACL/所有者，实际灾备切换仍需重新创建角色、执行迁移授权并验证应用。备份范围还包括受保护的部署配置、密钥及版本记录；未来加入对象文件后须纳入同一恢复点。

## 5. 升级

审查兼容性与迁移，先备份并完成恢复演练，再停写。核验并加载新包，更新包外环境文件中的镜像引用，运行 migrate，再启动 app，检查 ready 和核心流程。迁移可能不可逆，不能仅靠回滚镜像标签恢复。保留此前可恢复备份及演练报告。

生产前仍需完成目标 Linux/Windows 机器上的完整离线导入、密钥 ACL、网络传输、权限/审计、备份恢复与并发验收；不得把单元测试或健康接口成功表述为生产交付通过。
