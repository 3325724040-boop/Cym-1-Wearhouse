# 饰品仓库

中文饰品产品及库存管理应用。Python 3.10+、SQLite，运行时不需要第三方依赖。

## 功能

- 录入、编辑款式名称、唯一款式编号、新款/旧款、材质、销售单价、成本价及备注。
- 新建时填写初始库存；后续通过入库、出库调整数量，保留原因及结余流水。
- 防止负库存，金额按整数分存储；支持并发出库检查。
- 按名称、编号、材质搜索，按新旧款、有库存/零库存筛选。
- 汇总款式数、库存总量、库存成本金额及库存销售金额，导出 UTF-8 CSV。
- 桌面和手机自适应页面。流水时间按浏览器当地时间显示。

## 启动

```bash
cd /workspace/Cym-1-Wearhouse
python app.py
```

默认监听本机 `127.0.0.1:8000`。通过 `HOST`、`PORT` 调整监听位置；通过 `WAREHOUSE_DB` 指定数据库文件路径。
首次启动自动创建 `data/warehouse.sqlite3`，重启保留数据；该目录不提交到 Git。原始 `饰品价目表.xlsx` 保持不变，其三个工作表目前为空。

此版本面向本地、受信任环境，尚未提供登录、角色权限或公网部署配置。云环境内启动不等于已发布为可外部访问的网站。

## 独立站：展示商品，联系店主下单

在另一个终端启动只读商品展示站：

```bash
cd /workspace/Cym-1-Wearhouse
python storefront.py
```

默认监听 `127.0.0.1:8001`，支持 `SHOP_HOST`、`SHOP_PORT`。与管理后台使用相同的 `WAREHOUSE_DB`（默认数据库），无需同时运行后台进程即可浏览已有商品。

- 后台新增或编辑款式，填写客户可见的商品介绍和 HTTPS 图片网址，选择“上架展示”后保存。
- 新建商品默认不上架；前台只展示上架商品，库存只显示“有现货 / 暂时缺货”，不公开具体数量、成本价、内部备注或流水。
- 商品展示站支持款式搜索、新品/经典款筛选、商品详情、联系店主入口；没有在线支付或自动订单系统，客户联系店主后人工确认订单，再由后台记录出库。
- `SHOP_NAME` 配置店铺名称，默认“饰物集”；`SHOP_CONTACT` 配置可公开的微信、电话或邮箱。未配置时明确提示尚未公开联系方式，不显示虚构信息。
- 商品图片需使用你有权展示且可公开访问的 HTTPS 图片网址；没有图片时显示占位，加载失败时显示提示。
- 公网部署时仅将展示站放在 HTTPS 域名后；后台应保持内网访问，不要将后台端口或接口转发至展示站。当前未配置域名或部署，也未实现后台登录。

## 验证

```bash
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/shop.js
```

测试使用临时数据库，覆盖产品编辑、金额精度、库存流水、重启初始化保留数据、非法输入、重复编号、并发防超卖、CSV 导出与跨来源写入拦截。

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

恢复前停止应用，并保留当前数据库的备份。CSV 方便查看库存，但不包含完整流水，不能代替数据库备份。
