# 端到端验证（对着真 QASx 跑，不是 mock）

这些脚本不连假服务，直接打一个**真实的** quark-auto-save-x 实例。
单元测试只能证明逻辑自洽，这里证明接口对得上。

## 怎么起一个真 QASx

```bash
git clone --depth 1 https://github.com/x1ao4/quark-auto-save-x.git
cd quark-auto-save-x
pip install flask apscheduler requests treelib pypinyin

mkdir -p qasxrun/config
python3 - <<'PY'
import json, hashlib
cfg = {"cookie": ["placeholder"], "webui": {"username": "admin", "password": "testpass123"},
       "tasklist": [], "push_config": {}, "media_servers": {}, "magic_regex": {}, "source": {}}
open("qasxrun/config/quark_config.json", "w").write(json.dumps(cfg, ensure_ascii=False, indent=2))
print("QAS_TOKEN =", hashlib.md5(("token" + "admin" + "testpass123" + "+-*/").encode()).hexdigest()[8:24])
PY

CONFIG_PATH=./qasxrun/config/quark_config.json PORT=5599 python3 app/run.py
```

## 跑法

脚本里的 `QAS_ENDPOINT` / `QAS_TOKEN` 改成你的实例。用 `_request_with_retry` 的脚本需要
`nonebot.init()`，所以都在脚本开头设了环境变量和 `DRIVER=~httpx`（避免要求 fastapi/uvicorn）。

```bash
PYTHONPATH=src python3 tests/e2e/e2e_real_qasx.py        # 9 项：接口契约 + 删任务
PYTHONPATH=src python3 tests/e2e/e2e_dirty_config.py     # 11 项：脏配置 / 字段保全
PYTHONPATH=src python3 tests/e2e/e2e_share_expand.py     # 真分享递归展开、真实大小
PYTHONPATH=src python3 tests/e2e/e2e_full_subscription.py 三体   # 订阅全流程
```

## 各脚本验什么

| 脚本 | 覆盖 |
|---|---|
| `e2e_real_qasx.py` | `/data` 读写、`/api/add_task`、`/update` 删任务并回读、`/get_savepath_detail` 容错、`/task_suggestions` 结构、`/run_script_now` SSE 流 |
| `e2e_dirty_config.py` | 配置里存在 `addition=null` 时删除不再 500；删除不丢 `calendar_info`/`source`/`task_plugins` |
| `e2e_share_expand.py` | 分享根是文件夹时递归展开拿真视频；解析真集数与真文件大小 |
| `e2e_full_subscription.py` | 搜索 → 展开 → 筛选 → 选源 → 建任务 → 转存 → 删任务 全链路 |

## 已知无法在本仓库验证的部分

**真实转存需要你自己的夸克 cookie。** 没有 cookie 时 `run_script` 会跑到「验证账号」后
结束，脚本会如实报「没解析到转存结果」。这不是 bug，是缺登录态。
