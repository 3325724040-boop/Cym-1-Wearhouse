# 饰品仓库

中文饰品产品及库存管理应用。Python 3.10+、SQLite，运行时不需要第三方依赖。

## 功能

- 录入和编辑款式名称、唯一编号、新旧款、材质、销售单价、成本价及备注。
- 新建时填写初始库存；后续通过入库、出库调整数量，保留原因及结余流水。
- 防止负库存，金额按整数分存储；支持并发出库检查。
- 按名称、编号、材质搜索，按新旧款、有库存/零库存筛选。
- 汇总款式数、库存总量、库存成本金额及库存销售金额，导出 UTF-8 CSV。
- 商品图片保存在本机，可多图管理、调整图片参数。
- 桌面和手机自适应页面。流水时间按浏览器当地时间显示。

本项目仅用于本机库存管理，不包含独立商品展示站、在线询价或下单功能。

## 启动

```bash
python app.py
```

默认监听本机 `127.0.0.1:8000`。通过 `HOST`、`PORT` 调整监听位置；通过 `WAREHOUSE_DB` 指定数据库文件路径。首次启动自动创建 `data/warehouse.sqlite3`，重启后保留数据；该目录不提交到 Git。

上传图片保存在数据库旁的 `images/` 目录（默认 `data/images/`），与数据库一起备份。每款最多 9 张 JPG、PNG 或 WebP 图片，单张最大 5 MB。图片编辑在浏览器本地完成；原图不会被覆盖。

此版本面向本机和受信任环境，尚未提供登录、角色权限或公网部署配置。不要将后台端口暴露到公网。

## Windows 启动

双击 `start-windows.bat`。首次使用需安装 Python 3.10 或更高版本。运行窗口保持开启时可使用库存后台；关闭窗口或按 Ctrl+C 后服务停止。详细步骤见 [Windows使用说明.txt](Windows使用说明.txt)。

## 验证

```bash
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/gallery.js
```

测试使用临时数据库，覆盖产品编辑、金额精度、库存流水、重启后保留数据、非法输入、重复编号、并发防超卖、CSV 导出、图片上传与图库操作。

## 数据备份

数据库是业务数据，需要独立备份。可在应用运行时使用 SQLite 备份接口创建一致性副本：

```bash
python - <<'PY'
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
Path('data/backups').mkdir(exist_ok=True)
target = 'data/backups/warehouse-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3'
with sqlite3.connect('data/warehouse.sqlite3') as source, sqlite3.connect(target) as dest:
    source.backup(dest)
print(target)
PY
```

恢复前停止应用，并保留当前数据库的备份。CSV 方便查看库存，但不包含完整流水和图片，不能代替完整备份。最简单的方式是停止程序后备份整个 `data` 文件夹。

## 更新已有 Windows 项目（保留库存）

1. 关闭运行程序的窗口。
2. 先将整个 `data` 文件夹复制到其他位置备份。
3. 从 GitHub 下载新版 ZIP，解压，把新版项目文件和 `static`、`tests` 文件夹复制到旧项目文件夹，替换同名文件。
4. 保留原 `data` 文件夹；不要删除后再运行新空文件夹。
5. 双击 `start-windows.bat` 重新启动。若旧版本中还留有独立站文件，可删除 `storefront.py`、`static/shop.html`、`static/shop.js`、`static/shop.css` 和 `tests/test_storefront.py`。

## 浏览器功能检查（可选）

图库检查脚本 `tests/browser_gallery_smoke.py` 使用临时数据库，需事先准备 Playwright 和 Chromium；这些不是应用运行依赖。

```bash
python tests/browser_gallery_smoke.py
```

如浏览器安装在自定义位置，设置 `CHROMIUM_EXECUTABLE`。

## Windows 一键更新

- 新下载的项目包含 `update-windows.bat`。旧版本首次安装更新器时，只需将该 BAT 文件放入原项目文件夹（和 `start-windows.bat` 同一级）；缺少时它会从 GitHub HTTPS 下载 `updater.py`。
- 先关闭正在运行的窗口，再双击 `update-windows.bat`。更新器固定完整提交 SHA 下载 ZIP，校验目录和必要文件、编译 Python 源码，并在临时目录运行自动测试。
- 自检通过后备份整个 `data`（数据库和图片）及将被替换的代码，再逐文件原子替换。下载、自检或备份失败不会替换代码；安装中途失败会尝试恢复旧代码。升级时会清除旧版独立站程序文件。
- 原 Excel、业务数据和本地配置不替换。备份保存在项目旁的 `<项目文件夹名>-backups/时间戳/`，请另行复制到安全位置。
- 仅支持默认 `data/warehouse.sqlite3` 的自动备份；检测到自定义 `WAREHOUSE_DB` 或符号链接时会停止并要求手动处理。
- 更新器 Python 逻辑已在 Linux 验证；Windows 批处理、PowerShell 下载和 Windows 文件锁路径尚未在真实 Windows 机器验证。
