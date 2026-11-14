# Windows + Docker 离线部署（验证版）

当前源码版本为 `0.0.8`，迁移 head `0028`；升级涉及 `0026` 证物表删除时，先核对备份和[0.0.8 升级说明](../../docs/0.0.8-版本说明.md)。

Windows 主机须运行已审核的 Docker Desktop/Linux 容器环境及 Python 3.12+，目标 CPU 与构建镜像一致。只允许虚构数据验证。Docker Desktop 的许可、文件共享与系统安全策略由使用单位确认；完整架构、升级和恢复边界见经可信渠道取得的 [部署说明](README.md)。

## 1. 联网构建

在当前源码目录执行，摘要必须替换为已审核值：

```powershell
py -3 deploy/offline/make_bundle.py `
  --python-base 'python@sha256:<64位摘要>' `
  --node-base 'node@sha256:<64位摘要>' `
  --postgres 'postgres@sha256:<64位摘要>' `
  --platform linux/amd64 `
  --output 'C:/wellspring-transfer/bundle'
```

提前拉取 PostgreSQL 17 摘要镜像。脚本打印 manifest 和独立校验引导工具的摘要；将引导工具 `trusted_verify.py`、它的摘要、manifest 摘要及经审核的步骤通过独立可信渠道交付。引导工具不包含在待验包内。源码未提交改动会进入制品；清单记录实际构建输入摘要及依赖锁摘要。

## 2. 先验证可信工具，再验证包

本节命令必须来自可信发布说明，不直接相信待验包中的文档。将引导工具保存到受控的 `C:\wellspring\tools`，包保存到 `C:\wellspring\bundle`，禁止其他非可信账号修改它们。系统 Python 必须可信。

```powershell
$tool = 'C:\wellspring\tools\trusted_verify.py'
$bundle = 'C:\wellspring\bundle'
$trustedToolHash = '<独立渠道取得的工具SHA256>'
$manifestHash = '<独立渠道取得的manifest SHA256>'
if ((Get-FileHash -LiteralPath $tool -Algorithm SHA256).Hash -ne $trustedToolHash) {
    throw '可信引导工具摘要不符，停止'
}
py -3 -I $tool $bundle --manifest-sha256 $manifestHash
if ($LASTEXITCODE -ne 0) { throw '离线包核验失败，停止' }
docker load -i "$bundle/images.tar"
if ($LASTEXITCODE -ne 0) { throw '镜像导入失败，停止' }
py -3 -I $tool $bundle --manifest-sha256 $manifestHash --loaded
if ($LASTEXITCODE -ne 0) { throw '镜像核验失败，停止' }
```

引导工具先核验 manifest，再核验包内 `verify_bundle.py`，仅执行已验证的字节；`-I` 阻止包内模块或 `PYTHONPATH` 冒充标准库。不要直接运行尚未核验的包内校验程序，也不要从包内取“预期摘要”。没有数字签名时仍需独立可信渠道保证发布来源。

## 3. 配置和密钥

将 `env.windows.example` 复制到包外 `C:\wellspring\config\.env`，按需调整 `SECRETS_DIR=C:/wellspring/secrets`。默认只监听 `127.0.0.1:8080`；跨机访问另行配置经批准的 TLS 和访问控制。

在 secrets 目录创建无扩展名的 `db_owner_password` 和 `runtime_password`，使用不同强随机密码，限制 Windows ACL，并确认容器可读。格式为 UTF-8 无 BOM 单行，可以无换行、一个 LF 或 CRLF；不要包含空行、NUL 或 BOM。密码中的空格被保留。数据库和应用统一规范化换行，首次初始化之后改文件不会自动轮换数据库密码。文件型 secrets 不等于完整密钥管理。

## 4. 首次初始化与运行

仅用于新建的空数据库卷；每个命令失败立即停止，不执行下一步。

```powershell
$cfg = 'C:\wellspring\config\.env'
Set-Location -LiteralPath 'C:\wellspring\bundle'
docker compose --env-file $cfg -f compose.yaml config --quiet
docker compose --env-file $cfg -f compose.yaml up -d db
docker compose --env-file $cfg -f compose.yaml --profile tools run --rm migrate
docker compose --env-file $cfg -f compose.yaml --profile tools run --rm bootstrap bootstrap --initial-admin
docker compose --env-file $cfg -f compose.yaml up -d app
docker compose --env-file $cfg -f compose.yaml ps
```

初始化命令交互创建命名管理员，密码至少 12 位；已有管理员不能重复创建。迁移同时应用显式数据库权限矩阵。浏览器访问 [http://127.0.0.1:8080](http://127.0.0.1:8080)，核对页面、登录、业务和退出；`/api/ready` 要求数据库连接和迁移版本均通过，`/api/health` 只表示进程存活。

日常启动：`docker compose --env-file $cfg -f compose.yaml up -d`。停止：`docker compose --env-file $cfg -f compose.yaml stop`。不要使用 `down -v`，它会删除数据库卷。

## 5. 备份、恢复与升级

通过校验后运行工具，避免用 PowerShell 文本重定向生成二进制备份：

```powershell
py -3 -I .\backup_restore.py backup --env-file $cfg `
  --output 'C:\wellspring-backup\wellspring.dump'
py -3 -I .\backup_restore.py drill `
  --dump 'C:\wellspring-backup\wellspring.dump' `
  --sha256 '<从受控备份摘要文件核对的64位值>' `
  --postgres-image wellspring/postgres:17-offline `
  --report 'C:\wellspring-backup\restore-drill.json'
```

工具拒绝覆盖；恢复演练使用独立随机名容器，无网络、无现有卷挂载，检查实际恢复、表计数和迁移版本并记录耗时。演练容器数据使用内存文件系统，需足够内存；不修改源部署。报告不代替完整应用授权与业务核对。正式恢复应恢复角色、重新应用迁移权限，并验证配置与必要密钥。

升级前先备份并完成隔离恢复、审查迁移和停写；核验新包并更新镜像引用，执行迁移后重启应用。不能删除或覆盖旧卷排障，不能将镜像回滚等同于数据库恢复。目标机器的离线安装、ACL、恢复、并发和权限仍需实际验收。
