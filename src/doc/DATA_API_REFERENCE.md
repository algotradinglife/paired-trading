# Minishare 数据接口与 AK 能力码明细

更新时间：2026-05-02

这份文档只聚焦“取数接口”。数据接口主要分成三层：通用行情路由、Tushare 统一查询接口、AK 能力接口。Tushare 子接口虽然共用 `POST /api/v1/query`，AK 能力接口虽然共用 `GET /api/v1/akshare/{capability_code}`，但每个 `api_name` / 能力码都代表一个独立数据能力，所以这里逐个展开。

## 快速理解

- 普通行情：优先看 `/api/v1/daily`、`/api/v1/stock-basic`、`/api/v1/query`。
- Tushare 统一查询：全部调 `POST /api/v1/query`，用请求体里的 `api_name` 区分；当前共 232 个 `api_name`。
- AK 能力目录：先调 `/api/v1/akshare/capabilities` 找能力码。
- AK 真实取数：统一调 `GET /api/v1/akshare/{capability_code}`，把能力码换成表里的 code。
- 期权能力码是 `option_minute_history`，路径是 `/api/v1/akshare/option_minute_history`。
- 常规错误返回：`{"detail":"错误原因"}`；AK 权限、时间窗或限流失败时也会返回 403/429 类错误。

## 快速开始

下面这 5 步适合第一次接入。先把 `baseUrl` 和 `apiKey` 换成自己的值，确认能拿到 `rows`，再去查后面的接口明细。

### 1. 准备调用地址和 API Key

- 线上示例地址：`https://minishare.wmlgg.com`
- 请求头：`X-API-Key: <your-api-key>`
- 所有 JSON 请求体都带：`Content-Type: application/json`

### 2. 验证当前身份

```bash
curl "https://minishare.wmlgg.com/api/v1/me" \
  -H "X-API-Key: <your-api-key>"
```

成功时会返回当前用户、角色和默认配额。失败时先看是否是 `401` 或 `403`，不要继续排查数据参数。

### 3. 用快捷路由查询 A 股日线

```bash
curl "https://minishare.wmlgg.com/api/v1/daily?ts_code=000001.SZ&trade_date=20260410&fields=ts_code,trade_date,open,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

返回结果重点看：`columns` 是字段列表，`rows` 是数据行，`row_count` 是行数，`cached/cache_layer` 表示是否来自缓存或本地层。

### 4. 用 Tushare 统一查询入口

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"daily","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","open","close","vol"],"use_cache":true}'
```

Tushare 子接口都走这个入口。只要替换 `api_name` 和 `params`，就能调用下面明细表里的 232 个查询能力。

### 5. 用 AK 能力查询期权分钟线

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/option_minute_history?symbol=10000001.SH&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

AK 能力返回里会额外带 `capability_code`、`display_name`、`permission_code`、`upstream_api_names`，方便确认命中了哪个能力和上游 API。

## 场景示例

如果用户不知道该用哪个接口，可以先按场景找。下面示例都可以直接复制，替换代码、日期和 API Key 即可。

| 场景 | 推荐接口 | 请求方式 | 关键参数 | 返回看什么 |
| --- | --- | --- | --- | --- |
| A 股日线行情 | `daily` 或 `/api/v1/daily` | `GET` / `POST /api/v1/query` | `ts_code`、`trade_date`、`start_date`、`end_date` | `open/high/low/close/vol/amount` |
| 股票基础资料 | `stock_basic` 或 `/api/v1/stock-basic` | `GET` / `POST /api/v1/query` | `exchange`、`list_status` | `ts_code/symbol/name/industry/list_date` |
| 财务报表 | `income`、`balancesheet`、`cashflow`、`fina_indicator` | `POST /api/v1/query` | `ts_code`、`period` | `ann_date/end_date/report_type` 以及财务字段 |
| 港股行情 | `hk_daily`、`hk_mins` | `POST /api/v1/query` | `ts_code`、`trade_date`、`freq` | 港股 K 线或分钟线字段 |
| 美股行情 | `us_daily`、`us_daily_adj` | `POST /api/v1/query` | `ts_code`、`trade_date` | 美股日线字段 |
| 基金/ETF | `fund_daily`、`fund_nav`、`etf_basic` | `POST /api/v1/query` | `ts_code`、`trade_date`、`end_date`、`market` | 净值、行情或基础资料 |
| 期货分钟线 | `ft_mins` 或 AK `futures_minute_history` | `POST /api/v1/query` / `GET /api/v1/akshare/{code}` | `ts_code`、`trade_date`、`freq`、`symbol` | 分钟 K 线 rows |
| 期权分钟线 | AK `option_minute_history` | `GET /api/v1/akshare/option_minute_history` | `symbol`、`start_time`、`end_time`、`period` | 期权分钟 K 线 rows |
| 批量取数 | `/api/v1/query:batch` | `POST` | `requests` 或 `combo_code` | `items`、`ok_count`、`error_count` |
| 系统选股 | `/api/v1/stock-selection/system` | `GET` | `trade_date`、`board_source`、`limit` | `selected`、`score`、`reasons` |

### 场景 1：查 A 股最近一段日线

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"daily","params":{"ts_code":"600519.SH","start_date":"20260401","end_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol"],"use_cache":true}'
```

### 场景 2：查股票基础资料

```bash
curl "https://minishare.wmlgg.com/api/v1/stock-basic?list_status=L&fields=ts_code,symbol,name,area,industry,list_date" \
  -H "X-API-Key: <your-api-key>"
```

### 场景 3：查利润表

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"income","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","end_date","total_revenue","n_income"],"use_cache":true}'
```

### 场景 4：查港股日线

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_daily","params":{"ts_code":"00700.HK","trade_date":"20260410"},"fields":["ts_code","trade_date","open","close","vol"],"use_cache":true}'
```

### 场景 5：查美股日线

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_daily","params":{"ts_code":"AAPL","trade_date":"20260410"},"fields":["ts_code","trade_date","open","close","vol"],"use_cache":true}'
```

### 场景 6：批量查行情、资金和两融

```bash
curl "https://minishare.wmlgg.com/api/v1/query:batch" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"requests":[{"api_name":"daily","params":{"ts_code":"600519.SH","trade_date":"20260410"}},{"api_name":"moneyflow","params":{"ts_code":"600519.SH","trade_date":"20260410"}},{"api_name":"margin_detail","params":{"ts_code":"600519.SH","trade_date":"20260410"}}],"use_cache":true}'
```

批量接口不会因为某一个子请求失败就让整批失败。请看返回里的 `items[].ok`、`items[].data` 和 `items[].error`。

## 错误排查

接口失败时先看 HTTP 状态码，再看响应 JSON 里的 `category`、`detail`、`hint`、`retry_after_seconds`。常见错误返回形态如下：

```json
{
  "detail": "Permission denied for quote:read_daily.",
  "category": "permission.denied",
  "hint": "检查当前账号是否具备对应权限"
}
```

| 状态码/现象 | 常见原因 | 用户怎么处理 |
| --- | --- | --- |
| `400 Bad Request` | 参数格式不对、日期不合法、布尔/整数传错、必填字段缺失 | 对照对应接口的“请求参数”表；日期优先用 `YYYYMMDD`；JSON 请求体确认双引号和字段名正确。 |
| `401 Unauthorized` | 未带 API Key、API Key 无效、Session 过期 | 重新登录或重建 API Key；先调用 `GET /api/v1/me` 验证身份。 |
| `403 Forbidden` | 账号没有权限、AK 能力未授权、Bearer Token 不包含该能力、非管理员请求超出允许历史边界 | 查 `permission_code`；到能力目录确认是否有权限；AK 先调 `/api/v1/akshare/capabilities` 看 `available_now`。 |
| `404 Not Found` | 路径写错、AK 能力码写错、资源不存在 | 检查路径是否是 `/api/v1/query` 或 `/api/v1/akshare/{capability_code}`；能力码从目录复制。 |
| `409 Conflict` | 本地历史覆盖未完成、导出任务状态冲突、活跃 IP 限制 | 缩小日期范围或等待同步完成；导出先查任务详情；多机器调用时减少出口 IP。 |
| `422 Unprocessable Entity` | JSON 结构符合语法但不符合 schema，例如字段类型不对 | 看 `detail` 中的字段路径，修正请求体。 |
| `429 Too Many Requests` | 用户限流、AK QPS/日额度、上游回源额度紧张 | 降低并发，按 `retry_after_seconds` 等待；优先查历史日期或开启缓存。 |
| `502/503/504` | 上游 Tushare/AK/AI 暂时不可用或超时 | 稍后重试；如果持续出现，把 `request_id`、接口名、参数交给管理员排查。 |
| 返回 `row_count=0` 或 `rows=[]` | 代码、日期、市场、交易日不匹配，或字段过滤过窄 | 先去掉 `fields`，再放宽日期范围；确认 `ts_code` 后缀、交易日和 `period/freq` 是否正确。 |

稳定错误类别可用于程序判断：

| category | 含义 | 下一步 |
| --- | --- | --- |
| `auth.required` / `auth.invalid` | 缺少或无效凭证 | 补 `X-API-Key`，或重新生成 Key。 |
| `permission.denied` | 没有权限 | 对照明细表里的 `permission_code` 开通权限。 |
| `validation.invalid_request` | 请求参数不合法 | 修正字段名、类型、日期格式和分页限制。 |
| `rate_limit.user` / `rate_limit.active_ip` | 用户限流或活跃 IP 限制 | 降低频率、减少并发出口 IP。 |
| `cold_cache_miss` | 冷缓存未允许回源 | 查询已缓存数据，或联系管理员预热。 |
| `local_coverage_incomplete` | 本地历史覆盖未同步完整 | 缩小日期范围，或等待/触发同步任务。 |
| `local_coverage_out_of_range` | 请求超出本地数据边界 | 改到允许的历史范围内。 |
| `upstream_failure` | 上游准入后失败 | 稍后重试；持续失败时交给管理员看上游日志。 |

### 快速定位顺序

1. 先调 `GET /api/v1/me`：确认 API Key 和账号状态。
2. 看错误 `category`：程序判断优先用它，不要只匹配中文 `detail`。
3. 看接口明细里的 `permission_code`：确认账号是否具备权限。
4. 看参数：`ts_code` 后缀、`trade_date`、`period`、`freq`、`fields` 最容易写错。
5. 看缓存层：`cache_layer=source` 表示真实回源，`redis/mysql/local_market/materialized` 表示命中缓存或本地层。

### 用 AI 错误诊断接口

如果账号有 `ai:question` 权限，可以把错误响应原样交给诊断接口：

```bash
curl "https://minishare.wmlgg.com/api/v1/ai/diagnose-error" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"error_payload":{"code":409,"category":"local_coverage_incomplete","detail":"历史数据未同步完成"}}'
```

## 通用数据接口总览

| 方法 | 路径 | 用途 | 鉴权 | 返回结果 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/akshare/access` | AK 接口统一访问守卫，支持 API Key 或已签发 token，并叠加权限、时间窗与限流校验。 | API Key / Session / Bearer | application/json |
| `GET` | `/api/v1/akshare/capabilities` | AK 能力中心目录，支持 API Key 或 Session，按模块返回每个能力的包装信息。 | API Key / Session | 能力目录包含每个能力的请求路径、示例、权限和授权状态。 |
| `GET` | `/api/v1/akshare/capabilities/{capability_code}` | 单个 AK 能力的包装详情、参数建议和示例，支持 API Key 或 Session。 | API Key / Session | application/json |
| `GET` | `/api/v1/akshare/{capability_code}` | 用户直接请求单个 AK 能力的统一入口，内部完成 token、权限、时间窗和 QPS 校验。 | API Key / Session / Bearer | AK 统一查询会同时返回包装元信息和数据行。 |
| `GET` | `/api/v1/daily` | 行情读接口按当日或历史动态决定缓存。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `GET` | `/api/v1/hot-rank` | 本地每日热榜股票快照，同花顺热榜与东方财富热榜合并结果。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `GET` | `/api/v1/hot-stocks` | 每日热点股票快照：用热门板块、成分关系和个股日线强度组合评分。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `GET` | `/api/v1/me` | 返回当前主体与默认配额。 | API Key / Session | 返回当前认证主体和默认配额。 |
| `POST` | `/api/v1/query` | 通用查询，必须叠加 api_name 策略校验。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `POST` | `/api/v1/query:batch` | 受控批量查询，可传 requests 或 combo_code 展开内置组合。 | API Key / Session | 子请求失败不会让整批请求直接失败，会进入对应 item 的 `error` 字段。 |
| `GET` | `/api/v1/query:catalog` | 查询接口目录，返回受控组合查询和批量安全 api_name。 | API Key / Session | 用于学习哪些 `api_name` 可以批量查询，以及内置 `combo_code`。 |
| `GET` | `/api/v1/stock-basic` | 基础资料共享长缓存。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `GET` | `/api/v1/stock-company` | 上市公司资料快捷路由。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |
| `GET` | `/api/v1/stock-selection/system` | 系统选股：用东财板块热度、成分关系和个股强度组合评分。 | API Key / Session | 系统选股为组合计算结果，字段会随策略版本扩展。 |
| `GET` | `/api/v1/trade-calendar` | 交易日历快捷路由。 | API Key / Session | 通用行情类接口统一返回 `QueryResponse` 结构。 |

## Tushare 查询接口明细表

当前内置 Tushare 查询子接口共 232 个。所有子接口都调用同一个 HTTP 路由：`POST /api/v1/query`，差异只在请求体的 `api_name`、`params`、`fields`。

| api_name | 名称 | 请求方式 | 请求路径 | 权限 | 产品等级 | 缓存 | 请求参数示例 | 返回结构 | rows 含义 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `adj_factor` | 复权因子 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 复权因子按交易日缓存历史结果；最新或未带日期查询不缓存。 |
| `announcements` | 公告数据 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 公告查询兼容入口；/api/v1/query 方式走 anns_d，完整公告检索优先使用 /api/v1/akshare/announcements。 |
| `anns_d` | 公告披露 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `bak_basic` | 备用基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `bak_daily` | 备用行情 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `balancesheet` | 资产负债表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | 资产负债表适合长缓存。 |
| `bc_bestotcqt` | BC最优报价 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `bc_otcqt` | BC场外报价 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `block_trade` | 大宗交易 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `bond_blk` | 债券板块 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `bond_blk_detail` | 债券板块明细 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `broker_recommend` | 券商推荐 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `month` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `bse_mapping` | BSEMAPPING | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `cashflow` | 现金流量表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | 现金流量表适合长缓存。 |
| `cb_basic` | 可转债基础资料 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 可转债基础资料低频变化，适合参考类共享长缓存。 |
| `cb_call` | 可转债赎回公告 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债赎回公告属于低频披露数据，适合共享长缓存。 |
| `cb_daily` | 可转债日线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 可转债日线只缓存历史日期；当天和未带日期查询不缓存。 |
| `cb_factor_pro` | CB因子PRO | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `cb_issue` | 可转债发行 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债发行公告属于低频披露数据，适合共享长缓存。 |
| `cb_price_chg` | 可转债转股价变动 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债转股价变动属于低频事件，适合共享长缓存。 |
| `cb_rate` | 可转债票面利率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债票面利率低频变化，适合共享长缓存。 |
| `cb_rating` | 可转债信用评级 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债信用评级属于低频事件，适合共享长缓存。 |
| `cb_share` | 可转债转股结果 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 可转债转股结果属于披露类数据，适合共享长缓存。 |
| `ccass_hold` | 中央结算HOLD | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ccass_hold_detail` | 中央结算HOLD明细 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `cctv_news` | 央视新闻 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `ci_daily` | 中信行业日线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 中信行业指数日行情只缓存历史日期；当天和未带日期查询不缓存。 |
| `ci_index_member` | 中信行业成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `l1_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 中信行业成分低频变化，适合参考类共享长缓存。 |
| `cn_cpi` | 中国 CPI | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | 中国 CPI 宏观数据更新频率低，适合参考类共享长缓存。 |
| `cn_gdp` | 中国 GDP | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | 中国 GDP 宏观数据更新频率低，适合参考类共享长缓存。 |
| `cn_m` | 中国货币供应量 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | 货币供应量 M0/M1/M2 月度数据更新频率低，适合参考类共享长缓存。 |
| `cn_pmi` | 中国 PMI | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | 中国 PMI 宏观数据更新频率低，适合参考类共享长缓存。 |
| `cn_ppi` | 中国 PPI | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `cn_schedule` | 财经日历 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `concept` | 概念分类 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 概念分类低频变化，适合共享长缓存。 |
| `concept_detail` | 概念成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `id` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 概念成分低频变化，适合共享长缓存。 |
| `cyq_chips` | 筹码分布 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 筹码分布只缓存历史日期；最新或未带日期查询不缓存。 |
| `cyq_perf` | 筹码及胜率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 筹码及胜率只缓存历史日期；最新或未带日期查询不缓存。 |
| `daily` | A股日线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 当日行情短缓存，历史日线长缓存。 |
| `daily_basic` | 每日指标 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 每日指标只缓存明确历史日期；最新或未带日期查询不缓存。 |
| `daily_info` | 日线INFO | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `dc_concept` | 东方财富概念 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `dc_concept_cons` | 东方财富概念成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `dc_daily` | 东方财富板块日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `dc_hot` | 东方财富热榜 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `dc_index` | 东方财富板块指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `dc_member` | 东方财富板块成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `disclosure_date` | 财报披露计划 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条公司行为、业绩或披露记录。 | 财报披露计划更新频率较低，适合共享长缓存。 |
| `dividend` | 分红送股 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条公司行为、业绩或披露记录。 | 分红送股属于披露类数据，适合共享长缓存。 |
| `eco_cal` | 财经日历事件 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `etf_basic` | ETF 基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `market` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `etf_index` | ETF 标的指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `etf_share_size` | ETF 份额规模 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `express` | 业绩快报 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条公司行为、业绩或披露记录。 | 业绩快报属于披露类数据，适合共享长缓存。 |
| `fina_audit` | 财务审计意见 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 财务审计意见属于披露类数据，适合共享长缓存。 |
| `fina_indicator` | 财务指标 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | 财务指标适合长缓存。 |
| `fina_indicator_vip` | 财务指标 VIP 兼容 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 财务指标 VIP 兼容入口；当前上游走 fina_indicator 替代。 |
| `fina_mainbz` | 主营业务构成 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period`, `type` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `forecast` | 业绩预告 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条公司行为、业绩或披露记录。 | 业绩预告属于披露类数据，适合共享长缓存。 |
| `ft_limit` | 期货LIMIT | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ft_mins` | 期货分钟线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fund_adj` | 基金ADJ | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fund_basic` | 基金基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `market` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 基金基础信息低频变化，适合共享长缓存。 |
| `fund_company` | 基金公司 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fund_daily` | 基金日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 基金日线只缓存明确历史日期窗口；最新窗口不缓存。 |
| `fund_factor_pro` | 基金因子PRO | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fund_manager` | 基金经理 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fund_nav` | 基金净值 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fund_portfolio` | 基金持仓 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `fund_sales_ratio` | 基金SALESRATIO | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fund_sales_vol` | 基金SALESVOL | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fund_share` | 基金规模 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fut_basic` | 期货合约基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 期货合约基础资料低频变化，适合参考类共享长缓存。 |
| `fut_daily` | 期货日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 期货日线只缓存明确历史日期窗口；最新窗口不缓存。 |
| `fut_holding` | 期货持仓 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date`, `symbol` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fut_mapping` | 期货连续合约映射 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `fut_settle` | 期货结算 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fut_weekly_detail` | FUT周线明细 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fut_weekly_monthly` | FUT周线月线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fut_wsr` | FUTWSR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fx_daily` | 外汇日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `fx_obasic` | 外汇基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `ggt_daily` | 港股通每日成交 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ggt_monthly` | 港股通月度成交 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `month` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ggt_top10` | 港股通十大成交股 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 港股通十大成交股只缓存历史日期；当天榜单不缓存。 |
| `gz_index` | 估值指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `hibor` | HIBOR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `hk_adjfactor` | 港股复权因子 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `hk_balancesheet` | 港股资产负债表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `hk_basic` | 港股基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 港股基础资料低频变化，适合参考类共享长缓存。 |
| `hk_cashflow` | 港股现金流量表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `hk_daily` | 港股日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 港股日线只缓存明确历史日期窗口；最新窗口不缓存。 |
| `hk_daily_adj` | 港股复权日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `hk_fina_indicator` | 港股财务指标 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `hk_hold` | 沪深港通持股 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 沪深股通持股明细只缓存历史日期；当天和未带日期查询不缓存。 |
| `hk_income` | 港股利润表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `hk_mins` | 港股分钟线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `hk_tradecal` | 港股交易日历 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条交易日历记录。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `hm_detail` | 沪深港通明细 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `hm_list` | 沪深港通列表 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `hsgt_top10` | 沪深股通十大成交股 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date`, `market_type` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 沪深股通十大成交股只缓存历史日期；当天榜单不缓存。 |
| `idx_anns` | 指数公告 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `idx_factor_pro` | 指数技术因子 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 指数技术面因子只缓存明确历史日期窗口；最新窗口不缓存。 |
| `idx_mins` | 指数分钟线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `income` | 利润表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | 财报披露类数据适合长缓存。 |
| `index_basic` | 指数基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 指数基础信息低频变化，适合共享长缓存。 |
| `index_classify` | 指数分类 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 指数分类低频变化，适合参考类共享长缓存。 |
| `index_daily` | 指数日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 指数日线只缓存明确历史日期窗口；最新窗口不缓存。 |
| `index_dailybasic` | 指数每日指标 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 大盘指数每日指标只缓存历史日期；当天和未带日期查询不缓存。 |
| `index_global` | 全球指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `index_member_all` | 指数全部成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `index_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `index_monthly` | 指数月线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `index_weekly` | 指数周线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `index_weight` | 指数权重 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `index_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 指数权重只缓存明确历史日期窗口；最新窗口不缓存。 |
| `irm_qa_sh` | 互动问答问答SH | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `irm_qa_sz` | 互动问答问答深圳 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `kpl_concept_cons` | 开盘啦CONCEPT成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `kpl_list` | 开盘啦列表 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `libor` | LIBOR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `limit_cpt_list` | LIMIT概念列表 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `limit_list_d` | 涨跌停明细 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | 涨跌停明细只缓存历史日期；当天和未带日期查询不缓存。 |
| `limit_list_ths` | 同花顺涨跌停榜 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | 同花顺涨跌停榜只缓存历史日期；当天和未带日期查询不缓存。 |
| `limit_step` | 连板天梯 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `major_news` | MAJOR新闻 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `margin` | 融资融券汇总 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 融资融券汇总只缓存历史日期；当天和未带日期查询不缓存。 |
| `margin_detail` | 融资融券明细 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 融资融券明细只缓存历史日期；当天和未带日期查询不缓存。 |
| `margin_secs` | 融资融券标的 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 融资融券标的只缓存历史日期；当天和未带日期查询不缓存。 |
| `moneyflow` | 个股资金流向 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | 个股资金流向只缓存历史日期；当天和未带日期查询不缓存。 |
| `moneyflow_cnt_ths` | MONEYFLOWCNT同花顺 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `moneyflow_dc` | MONEYFLOWDC | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `moneyflow_hsgt` | 沪深港通资金流向 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | 沪深港通资金流向只缓存历史日期；当天和未带日期查询不缓存。 |
| `moneyflow_ind_dc` | MONEYFLOW行业DC | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `moneyflow_ind_ths` | MONEYFLOW行业同花顺 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `moneyflow_mkt_dc` | MONEYFLOW市场DC | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `moneyflow_ths` | 同花顺资金流向 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条资金流向记录。 | THS 资金流向只缓存历史日期；当天和未带日期查询不缓存。 |
| `monthly` | A股月线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 月线只有在明确历史日期窗口时共享缓存；最新窗口不缓存。 |
| `namechange` | 股票更名记录 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 更名记录低频变化，适合共享长缓存。 |
| `new_share` | 新股发行 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `news` | 新闻资讯 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `npr` | 政策法规库 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `org`, `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条政策法规或规范性文件记录。 | Tushare Pro 政策法规库接口，适合按发布机构、政策类型和发布时间窗口共享长缓存。 |
| `opt_basic` | OPTBASIC | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `opt_daily` | OPT日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `opt_mins` | OPT分钟线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `pledge_detail` | 股权质押明细 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `pledge_stat` | 股权质押统计 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `realtime_list` | 实时行情列表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `src`, `page_count` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条实时行情快照或实时成交记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `realtime_quote` | 实时行情快照 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条实时行情快照或实时成交记录。 | 实时快照更新频繁，默认不缓存。 |
| `realtime_tick` | 实时成交明细 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `src` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条实时行情快照或实时成交记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `repo_daily` | 回购日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `report_rc` | REPORTRC | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `repurchase` | 股票回购 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条公司行为、业绩或披露记录。 | 回购公告属于披露类数据，适合共享长缓存。 |
| `research_report` | 研究报告 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条新闻、公告或研报内容记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `rt_etf_k` | ETF 实时日线 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_etf_sz_iopv` | ETF 实时 IOPV | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条实时行情快照或实时成交记录。 | ETF 实时 IOPV 仅适合有对应上游权限的深市 ETF，实时高频数据默认不缓存。 |
| `rt_fut_min` | 期货实时分钟 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_hk_k` | 港股实时日线 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_idx_k` | 指数实时日线 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_idx_min` | 指数实时分钟 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_k` | A股实时日线 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_min` | A股实时分钟 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_min_daily` | A股实时分钟日内 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_sw_k` | 申万实时日线 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，实时或高频数据默认不缓存。 |
| `rt_tick` | 分时实时成交 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | NC / none | `ts_code`, `src` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条实时行情快照或实时成交记录。 | 分时实时成交更新频繁，默认不缓存。 |
| `sf_month` | 社会融资规模 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 社会融资规模月度数据更新频率低，适合参考类共享长缓存。 |
| `sge_basic` | 上金所BASIC | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `sge_daily` | 上金所日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `share_float` | 限售股解禁 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 限售股解禁计划更新频率较低，适合共享长缓存。 |
| `shibor` | Shibor 利率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Shibor 利率只缓存历史日期；最新或未带日期查询不缓存。 |
| `shibor_lpr` | LPR 利率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `shibor_quote` | Shibor 报价 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `slb_len` | 转融资交易汇总 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 转融资交易汇总只缓存历史日期；当天和未带日期查询不缓存。 |
| `slb_sec` | 转融券交易汇总 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 转融券交易汇总只缓存历史日期；当天和未带日期查询不缓存。 |
| `slb_sec_detail` | 转融券交易明细 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 转融券交易明细只缓存历史日期；当天和未带日期查询不缓存。 |
| `st` | 风险警示板列表 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | ST 风险警示板列表属于低频参考数据，适合共享长缓存。 |
| `stk_ah_comparison` | 股票AHCOMPARISON | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_alert` | 股票预警 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_auction` | 开盘集合竞价 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_auction_c` | 收盘集合竞价 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 收盘集合竞价只缓存历史日期；当天和未带日期查询不缓存。 |
| `stk_auction_o` | 开盘集合竞价明细 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_factor_pro` | 股票技术因子 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 股票技术面因子只缓存明确历史日期窗口；最新窗口不缓存。 |
| `stk_high_shock` | 股票HIGH异动 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_holdernumber` | 股东户数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | 股东户数属于披露类低频数据，适合共享长缓存。 |
| `stk_holdertrade` | 股东增减持 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | 股东增减持披露低频变化，适合共享长缓存。 |
| `stk_limit` | 涨跌停价格 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | 涨跌停价按历史交易日缓存；当天和未带日期查询不缓存。 |
| `stk_managers` | 管理层名单 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `stk_mins` | 股票分钟线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一根分钟 K 线或一条分钟级行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_nineturn` | 神奇九转 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 神奇九转指标只缓存明确历史日期窗口；最新窗口不缓存。 |
| `stk_premarket` | 盘前数据 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_rewards` | 管理层薪酬 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `stk_shock` | 股票异动 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_surv` | 股票SURV | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `stk_week_month_adj` | 股票WEEKMONTHADJ | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stk_weekly_monthly` | 股票周线月线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date`, `freq` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `stock_basic` | 股票基础信息 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 股票基础信息低频变化，但按天刷新更利于和路由层行为保持一致。 |
| `stock_company` | 上市公司资料 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 上市公司资料低频变化，适合参考类共享长缓存。 |
| `stock_hsgt` | 沪深港通股票列表 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 沪深港通股票列表低频变化，适合参考类共享长缓存。 |
| `stock_st` | ST 股票列表 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `limit` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | ST 股票列表属于低频参考数据，适合共享长缓存。 |
| `suspend_d` | 停复牌明细 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 停复牌明细按历史交易日缓存；当天和未带日期查询不缓存。 |
| `sw_daily` | 申万日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `sz_daily_info` | 深圳日线INFO | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `tdx_daily` | 通达信日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `tdx_index` | 通达信指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `tdx_member` | 通达信MEMBER | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `ths_bk_daily` | 同花顺板块日线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 同花顺板块日行情只缓存历史日期；当天和未带日期查询不缓存。 |
| `ths_bk_list` | 同花顺板块成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 同花顺板块成分低频变化，适合参考类共享长缓存。 |
| `ths_daily` | 同花顺指数日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ths_hot` | 同花顺热榜 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `ths_index` | 同花顺指数目录 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | 同花顺指数/板块目录属于参考数据，适合共享长缓存。 |
| `ths_member` | 同花顺指数成分 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `top10_cb_holders` | 可转债前十大持有人 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | 可转债前十大持有人属于披露类数据，适合共享长缓存。 |
| `top10_floatholders` | 前十大流通股东 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | 前十大流通股东属于披露类数据，适合共享长缓存。 |
| `top10_holders` | 前十大股东 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条股东、持股或质押相关记录。 | 前十大股东属于披露类数据，适合共享长缓存。 |
| `top_inst` | 龙虎榜机构席位 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | 龙虎榜机构席位只缓存历史日期；当天和未带日期查询不缓存。 |
| `top_list` | 龙虎榜每日明细 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条榜单、热度或涨跌停明细记录。 | 龙虎榜每日明细只缓存历史日期；当天和未带日期查询不缓存。 |
| `trade_cal` | 交易日历 | `POST` | `/api/v1/query` | `quote:read_stock_basic` | `standard` | S2 / shared | `exchange`, `start_date`, `end_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条交易日历记录。 | 交易日历变化极低，适合长缓存。 |
| `us_adjfactor` | 美股复权因子 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_balancesheet` | 美股资产负债表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `us_basic` | 美股基础资料 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条证券、基金、期货、指数或机构基础资料。 | 美股基础资料低频变化，适合参考类共享长缓存。 |
| `us_cashflow` | 美股现金流量表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `us_daily` | 美股日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 美股日线只缓存明确历史日期窗口；最新窗口不缓存。 |
| `us_daily_adj` | 美股复权日线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_fina_indicator` | 美股财务指标 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `us_income` | 美股利润表 | `POST` | `/api/v1/query` | `query:run_generic` | `sensitive` | S2 / shared | `ts_code`, `period` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条财务报表或财务指标记录。 | Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。 |
| `us_tbr` | 美国国债利率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_tltr` | 美股长期利率 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_tradecal` | 美股交易日历 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | S2 / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条交易日历记录。 | Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。 |
| `us_trltr` | 美股TRLTR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_trycr` | 美股TRYCR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `us_tycr` | 美股TYCR | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条宏观经济或利率时间序列记录。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `weekly` | A股周线 | `POST` | `/api/v1/query` | `quote:read_daily` | `standard` | DYNAMIC / shared | `ts_code`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条日线、周线、月线或 K 线行情记录。 | 周线只有在明确历史日期窗口时共享缓存；最新窗口不缓存。 |
| `wz_index` | 万得指数 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `ts_code` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |
| `yc_cb` | 中债收益率曲线 | `POST` | `/api/v1/query` | `query:run_generic` | `standard` | DYNAMIC / shared | `curve_type`, `trade_date` | `QueryResponse`：`columns`、`rows`、`row_count`、`cached`、`cache_layer`、`response_meta` | 每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。 | Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。 |

## Tushare 统一调用约定

- 请求方式：`POST /api/v1/query`
- 鉴权：`X-API-Key` 或浏览器 Session。
- `api_name`：必填，取下面小节里的接口名。
- `params`：对象，放 Tushare 上游参数；Minishare 不改名，原样透传，并叠加权限、缓存、审计和限流。
- `fields`：可选，数组或逗号分隔字符串，用于裁剪返回字段；不传或空数组时返回上游默认字段。
- 返回结构：统一 `QueryResponse`，核心数据在 `rows`；`columns` 告诉你本次实际返回了哪些列。

## Tushare 查询接口逐项说明

### `adj_factor` - 复权因子

复权因子按交易日缓存历史结果；最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `adj_factor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"adj_factor","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "adj_factor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `announcements` - 公告数据

公告查询兼容入口；/api/v1/query 方式走 anns_d，完整公告检索优先使用 /api/v1/akshare/announcements。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `announcements` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `20250101` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20251231` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"announcements","params":{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "announcements",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `anns_d` - 公告披露

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `anns_d` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `20250101` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20251231` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"anns_d","params":{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "anns_d",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `bak_basic` - 备用基础资料

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bak_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bak_basic","params":{"ts_code":"000001.SZ"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "bak_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `bak_daily` - 备用行情

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bak_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bak_daily","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "bak_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `balancesheet` - 资产负债表

资产负债表适合长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `balancesheet` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"balancesheet","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "balancesheet",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `bc_bestotcqt` - BC最优报价

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bc_bestotcqt` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bc_bestotcqt","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "bc_bestotcqt",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `bc_otcqt` - BC场外报价

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bc_otcqt` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bc_otcqt","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "bc_otcqt",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `block_trade` - 大宗交易

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `block_trade` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"block_trade","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "block_trade",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `bond_blk` - 债券板块

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bond_blk` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bond_blk","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "bond_blk",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `bond_blk_detail` - 债券板块明细

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bond_blk_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bond_blk_detail","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "bond_blk_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `broker_recommend` - 券商推荐

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `broker_recommend` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"month":"202604"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `month` | `body.params.month` | 按上游 | `string` | `202604` | 月份，通常为 YYYYMM。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"broker_recommend","params":{"month":"202604"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "broker_recommend",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `bse_mapping` - BSEMAPPING

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `bse_mapping` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"bse_mapping","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "bse_mapping",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cashflow` - 现金流量表

现金流量表适合长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cashflow` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cashflow","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "cashflow",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `cb_basic` - 可转债基础资料

可转债基础资料低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_basic","params":{"ts_code":"113021.SH"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "cb_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_call` - 可转债赎回公告

可转债赎回公告属于低频披露数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_call` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_call","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_call",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_daily` - 可转债日线

可转债日线只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113059.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113059.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_daily","params":{"ts_code":"113059.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "cb_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "113059.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `cb_factor_pro` - CB因子PRO

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_factor_pro` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113059.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113059.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_factor_pro","params":{"ts_code":"113059.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_factor_pro",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113059.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `cb_issue` - 可转债发行

可转债发行公告属于低频披露数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_issue` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_issue","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_issue",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_price_chg` - 可转债转股价变动

可转债转股价变动属于低频事件，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_price_chg` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_price_chg","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_price_chg",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_rate` - 可转债票面利率

可转债票面利率低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_rate` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_rate","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_rate",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_rating` - 可转债信用评级

可转债信用评级属于低频事件，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_rating` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_rating","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_rating",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cb_share` - 可转债转股结果

可转债转股结果属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cb_share` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cb_share","params":{"ts_code":"113021.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cb_share",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `ccass_hold` - 中央结算HOLD

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ccass_hold` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ccass_hold","params":{"ts_code":"00700.HK","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ccass_hold",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ccass_hold_detail` - 中央结算HOLD明细

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ccass_hold_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ccass_hold_detail","params":{"ts_code":"00700.HK","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ccass_hold_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `cctv_news` - 央视新闻

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cctv_news` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cctv_news","params":{"limit":20},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "cctv_news",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `ci_daily` - 中信行业日线

中信行业指数日行情只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ci_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CI005001.CI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CI005001.CI` | 中信行业指数代码，使用 .CI 后缀。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ci_daily","params":{"ts_code":"CI005001.CI","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "ci_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CI005001.CI",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ci_index_member` - 中信行业成分

中信行业成分低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ci_index_member` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"l1_code":"CI005001.CI"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `l1_code` | `body.params.l1_code` | 按上游 | `string` | `CI005001.CI` | 中信一级行业代码，使用 .CI 后缀。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ci_index_member","params":{"l1_code":"CI005001.CI"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ci_index_member",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_cpi` - 中国 CPI

中国 CPI 宏观数据更新频率低，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_cpi` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_cpi","params":{"limit":20},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "cn_cpi",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_gdp` - 中国 GDP

中国 GDP 宏观数据更新频率低，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_gdp` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_gdp","params":{"limit":20},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "cn_gdp",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_m` - 中国货币供应量

货币供应量 M0/M1/M2 月度数据更新频率低，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_m` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_m","params":{"limit":20},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "cn_m",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_pmi` - 中国 PMI

中国 PMI 宏观数据更新频率低，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_pmi` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_pmi","params":{"limit":20},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "cn_pmi",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_ppi` - 中国 PPI

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_ppi` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_ppi","params":{"limit":20},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "cn_ppi",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cn_schedule` - 财经日历

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cn_schedule` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cn_schedule","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cn_schedule",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `concept` - 概念分类

概念分类低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `concept` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"concept","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "concept",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `concept_detail` - 概念成分

概念成分低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `concept_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"id":"TS2"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `body.params.id` | 按上游 | `string` | `TS2` | 概念、主题或上游实体 ID。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"concept_detail","params":{"id":"TS2"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "concept_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `cyq_chips` - 筹码分布

筹码分布只缓存历史日期；最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cyq_chips` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cyq_chips","params":{"ts_code":"600519.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cyq_chips",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `cyq_perf` - 筹码及胜率

筹码及胜率只缓存历史日期；最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `cyq_perf` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"cyq_perf","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "cyq_perf",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `daily` - A股日线

当日行情短缓存，历史日线长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"daily","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `daily_basic` - 每日指标

每日指标只缓存明确历史日期；最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `daily_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"daily_basic","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "daily_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `daily_info` - 日线INFO

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `daily_info` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"daily_info","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "daily_info",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `dc_concept` - 东方财富概念

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_concept` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_concept","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "dc_concept",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `dc_concept_cons` - 东方财富概念成分

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_concept_cons` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260204"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","theme_code","industry_code","industry","reason","hot_num"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260204` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_concept_cons","params":{"trade_date":"20260204"},"fields":["ts_code","trade_date","name","theme_code","industry_code","industry","reason","hot_num"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `theme_code`, `industry_code`, `industry`, `reason`, `hot_num`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "dc_concept_cons",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "theme_code",
    "industry_code",
    "industry",
    "reason",
    "hot_num"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260204",
      "name": "<name>",
      "theme_code": "<theme_code>",
      "industry_code": "<industry_code>",
      "industry": "<industry>",
      "reason": "<reason>",
      "hot_num": "<hot_num>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `dc_daily` - 东方财富板块日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"BK0145.DC","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `BK0145.DC` | 东方财富板块代码，使用 BKxxxx.DC 后缀；可从 `dc_index` 或 `dc_daily` 单日全量结果获取。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_daily","params":{"ts_code":"BK0145.DC","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "dc_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "BK0145.DC",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `dc_hot` - 东方财富热榜

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_hot` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_hot","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "dc_hot",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `dc_index` - 东方财富板块指数

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"BK0145.DC"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `BK0145.DC` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_index","params":{"ts_code":"BK0145.DC"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "dc_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "BK0145.DC",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `dc_member` - 东方财富板块成分

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dc_member` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dc_member","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "dc_member",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `disclosure_date` - 财报披露计划

财报披露计划更新频率较低，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `disclosure_date` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","end_date":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","type","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20251231` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"disclosure_date","params":{"ts_code":"600519.SH","end_date":"20251231"},"fields":["ts_code","ann_date","end_date","type","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `type`, `amount`
行含义：每一行通常是一条公司行为、业绩或披露记录。

示例：
```json
{
  "api_name": "disclosure_date",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "type",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "type": "<type>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `dividend` - 分红送股

分红送股属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `dividend` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","type","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"dividend","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","type","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `type`, `amount`
行含义：每一行通常是一条公司行为、业绩或披露记录。

示例：
```json
{
  "api_name": "dividend",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "type",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "type": "<type>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `eco_cal` - 财经日历事件

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `eco_cal` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"eco_cal","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "eco_cal",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `etf_basic` - ETF 基础资料

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `etf_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"market":"E"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `market` | `body.params.market` | 按上游 | `string` | `E` | 市场代码，例如 E 表示场内基金；具体取值按 Tushare 接口定义。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"etf_basic","params":{"market":"E"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "etf_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `etf_index` - ETF 标的指数

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `etf_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"etf_index","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "etf_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `etf_share_size` - ETF 份额规模

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `etf_share_size` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"etf_share_size","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "etf_share_size",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `express` - 业绩快报

业绩快报属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `express` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"start_date":"20250101","end_date":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","type","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `20250101` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20251231` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"express","params":{"start_date":"20250101","end_date":"20251231"},"fields":["ts_code","ann_date","end_date","type","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `type`, `amount`
行含义：每一行通常是一条公司行为、业绩或披露记录。

示例：
```json
{
  "api_name": "express",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "type",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "type": "<type>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `fina_audit` - 财务审计意见

财务审计意见属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fina_audit` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fina_audit","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fina_audit",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `fina_indicator` - 财务指标

财务指标适合长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fina_indicator` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fina_indicator","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "fina_indicator",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `fina_indicator_vip` - 财务指标 VIP 兼容

财务指标 VIP 兼容入口；当前上游走 fina_indicator 替代。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fina_indicator_vip` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fina_indicator_vip","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fina_indicator_vip",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `fina_mainbz` - 主营业务构成

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fina_mainbz` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231","type":"P"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |
| `type` | `body.params.type` | 按上游 | `string` | `P` | 业务类型过滤参数，例如主营业务构成里 P=产品、D=地区。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fina_mainbz","params":{"ts_code":"600519.SH","period":"20251231","type":"P"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fina_mainbz",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `forecast` - 业绩预告

业绩预告属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `forecast` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","type","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `20250101` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20251231` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"forecast","params":{"ts_code":"600519.SH","start_date":"20250101","end_date":"20251231"},"fields":["ts_code","ann_date","end_date","type","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `type`, `amount`
行含义：每一行通常是一条公司行为、业绩或披露记录。

示例：
```json
{
  "api_name": "forecast",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "type",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "type": "<type>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `ft_limit` - 期货LIMIT

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ft_limit` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ft_limit","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "ft_limit",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ft_mins` - 期货分钟线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ft_mins` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410","freq":"1min"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1min` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ft_mins","params":{"ts_code":"CU.SHF","trade_date":"20260410","freq":"1min"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "ft_mins",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fund_adj` - 基金ADJ

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_adj` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"510300.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `510300.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_adj","params":{"ts_code":"510300.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_adj",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "510300.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fund_basic` - 基金基础资料

基金基础信息低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"market":"E"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `market` | `body.params.market` | 按上游 | `string` | `E` | 市场代码，例如 E 表示场内基金；具体取值按 Tushare 接口定义。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_basic","params":{"market":"E"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "fund_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fund_company` - 基金公司

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_company` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_company","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_company",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fund_daily` - 基金日线

基金日线只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"510300.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `510300.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_daily","params":{"ts_code":"510300.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "fund_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "510300.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fund_factor_pro` - 基金因子PRO

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_factor_pro` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"510300.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `510300.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_factor_pro","params":{"ts_code":"510300.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_factor_pro",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "510300.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fund_manager` - 基金经理

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_manager` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_manager","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_manager",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fund_nav` - 基金净值

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_nav` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.OF","end_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.OF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20260410` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_nav","params":{"ts_code":"000001.OF","end_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_nav",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.OF",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fund_portfolio` - 基金持仓

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_portfolio` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.OF"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.OF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_portfolio","params":{"ts_code":"000001.OF"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_portfolio",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.OF",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `fund_sales_ratio` - 基金SALESRATIO

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_sales_ratio` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_sales_ratio","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_sales_ratio",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fund_sales_vol` - 基金SALESVOL

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_sales_vol` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_sales_vol","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_sales_vol",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fund_share` - 基金规模

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fund_share` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fund_share","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fund_share",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fut_basic` - 期货合约基础资料

期货合约基础资料低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_basic","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "fut_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fut_daily` - 期货日线

期货日线只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_daily","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "fut_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fut_holding` - 期货持仓

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_holding` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410","symbol":"CU"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `symbol` | `body.params.symbol` | 按上游 | `string` | `CU` | 交易品种代码或简称，期货/期权/部分榜单接口常用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_holding","params":{"trade_date":"20260410","symbol":"CU"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fut_holding",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fut_mapping` - 期货连续合约映射

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_mapping` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_mapping","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fut_mapping",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `fut_settle` - 期货结算

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_settle` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_settle","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fut_settle",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fut_weekly_detail` - FUT周线明细

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_weekly_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_weekly_detail","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "fut_weekly_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fut_weekly_monthly` - FUT周线月线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_weekly_monthly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260430","freq":"week"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260430` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `week` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_weekly_monthly","params":{"ts_code":"CU.SHF","trade_date":"20260430","freq":"week"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "fut_weekly_monthly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260430",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fut_wsr` - FUTWSR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fut_wsr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fut_wsr","params":{"ts_code":"CU.SHF","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fut_wsr",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fx_daily` - 外汇日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fx_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"USDCNH.FX","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `USDCNH.FX` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fx_daily","params":{"ts_code":"USDCNH.FX","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "fx_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "USDCNH.FX",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `fx_obasic` - 外汇基础资料

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `fx_obasic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"USDCNH.FX","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `USDCNH.FX` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"fx_obasic","params":{"ts_code":"USDCNH.FX","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "fx_obasic",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "USDCNH.FX",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `ggt_daily` - 港股通每日成交

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ggt_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ggt_daily","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "ggt_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ggt_monthly` - 港股通月度成交

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ggt_monthly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"month":"202604"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `month` | `body.params.month` | 按上游 | `string` | `202604` | 月份，通常为 YYYYMM。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ggt_monthly","params":{"month":"202604"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "ggt_monthly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ggt_top10` - 港股通十大成交股

港股通十大成交股只缓存历史日期；当天榜单不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ggt_top10` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ggt_top10","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ggt_top10",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `gz_index` - 估值指数

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `gz_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"gz_index","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "gz_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `hibor` - HIBOR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hibor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hibor","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hibor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_adjfactor` - 港股复权因子

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_adjfactor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_adjfactor","params":{"ts_code":"00700.HK"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hk_adjfactor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_balancesheet` - 港股资产负债表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_balancesheet` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_balancesheet","params":{"ts_code":"00700.HK","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "hk_balancesheet",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `hk_basic` - 港股基础资料

港股基础资料低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","symbol","name","area","industry","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_basic","params":{"ts_code":"00700.HK"},"fields":["ts_code","symbol","name","area","industry","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `symbol`, `name`, `area`, `industry`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "hk_basic",
  "columns": [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "symbol": "<symbol>",
      "name": "<name>",
      "area": "<area>",
      "industry": "<industry>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `hk_cashflow` - 港股现金流量表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_cashflow` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_cashflow","params":{"ts_code":"00700.HK","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "hk_cashflow",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `hk_daily` - 港股日线

港股日线只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_daily","params":{"ts_code":"00700.HK","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "hk_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_daily_adj` - 港股复权日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_daily_adj` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_daily_adj","params":{"ts_code":"00700.HK","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "hk_daily_adj",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_fina_indicator` - 港股财务指标

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_fina_indicator` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_fina_indicator","params":{"ts_code":"00700.HK","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "hk_fina_indicator",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `hk_hold` - 沪深港通持股

沪深股通持股明细只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_hold` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_hold","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hk_hold",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_income` - 港股利润表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_income` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_income","params":{"ts_code":"00700.HK","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "hk_income",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `hk_mins` - 港股分钟线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_mins` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK","trade_date":"20260410","freq":"1min"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1min` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_mins","params":{"ts_code":"00700.HK","trade_date":"20260410","freq":"1min"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "hk_mins",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hk_tradecal` - 港股交易日历

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hk_tradecal` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["exchange","cal_date","is_open","pretrade_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hk_tradecal","params":{"ts_code":"00700.HK"},"fields":["exchange","cal_date","is_open","pretrade_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`exchange`, `cal_date`, `is_open`, `pretrade_date`
行含义：每一行通常是一条交易日历记录。

示例：
```json
{
  "api_name": "hk_tradecal",
  "columns": [
    "exchange",
    "cal_date",
    "is_open",
    "pretrade_date"
  ],
  "rows": [
    {
      "exchange": "<exchange>",
      "cal_date": "20260410",
      "is_open": "<is_open>",
      "pretrade_date": "<pretrade_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `hm_detail` - 沪深港通明细

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hm_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hm_detail","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hm_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `hm_list` - 沪深港通列表

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hm_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hm_list","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hm_list",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `hsgt_top10` - 沪深股通十大成交股

沪深股通十大成交股只缓存历史日期；当天榜单不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `hsgt_top10` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410","market_type":"1"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `market_type` | `body.params.market_type` | 按上游 | `string` | `1` | 市场类型，常用于沪深港通等接口，具体取值按上游定义。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"hsgt_top10","params":{"trade_date":"20260410","market_type":"1"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "hsgt_top10",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `idx_anns` - 指数公告

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `idx_anns` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"idx_anns","params":{"ts_code":"000001.SH"},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "idx_anns",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `idx_factor_pro` - 指数技术因子

指数技术面因子只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `idx_factor_pro` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"idx_factor_pro","params":{"ts_code":"000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "idx_factor_pro",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `idx_mins` - 指数分钟线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `idx_mins` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410","freq":"1min"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1min` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"idx_mins","params":{"ts_code":"000001.SH","trade_date":"20260410","freq":"1min"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "idx_mins",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `income` - 利润表

财报披露类数据适合长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `income` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"income","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "income",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `index_basic` - 指数基础资料

指数基础信息低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_basic","params":{"ts_code":"000001.SH"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "index_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `index_classify` - 指数分类

指数分类低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_classify` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_classify","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "index_classify",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `index_daily` - 指数日线

指数日线只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_daily","params":{"ts_code":"000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "index_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `index_dailybasic` - 指数每日指标

大盘指数每日指标只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_dailybasic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_dailybasic","params":{"ts_code":"000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "index_dailybasic",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `index_global` - 全球指数

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_global` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"HSI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `HSI` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_global","params":{"ts_code":"HSI","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "index_global",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "HSI",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `index_member_all` - 指数全部成分

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_member_all` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"index_code":"000300.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `index_code` | `body.params.index_code` | 按上游 | `string` | `000300.SH` | 指数代码，例如 000300.SH。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_member_all","params":{"index_code":"000300.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "index_member_all",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `index_monthly` - 指数月线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_monthly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260430"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260430` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_monthly","params":{"ts_code":"000001.SH","trade_date":"20260430"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "index_monthly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260430",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `index_weekly` - 指数周线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_weekly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_weekly","params":{"ts_code":"000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "index_weekly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `index_weight` - 指数权重

指数权重只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `index_weight` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"index_code":"000300.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `index_code` | `body.params.index_code` | 按上游 | `string` | `000300.SH` | 指数代码，例如 000300.SH。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"index_weight","params":{"index_code":"000300.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "index_weight",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `irm_qa_sh` - 互动问答问答SH

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `irm_qa_sh` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"irm_qa_sh","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "irm_qa_sh",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `irm_qa_sz` - 互动问答问答深圳

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `irm_qa_sz` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"irm_qa_sz","params":{"ts_code":"000001.SZ"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "irm_qa_sz",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `kpl_concept_cons` - 开盘啦CONCEPT成分

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `kpl_concept_cons` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"kpl_concept_cons","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "kpl_concept_cons",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `kpl_list` - 开盘啦列表

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `kpl_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"kpl_list","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "kpl_list",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `libor` - LIBOR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `libor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"libor","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "libor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `limit_cpt_list` - LIMIT概念列表

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `limit_cpt_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"limit_cpt_list","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "limit_cpt_list",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `limit_list_d` - 涨跌停明细

涨跌停明细只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `limit_list_d` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"limit_list_d","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "limit_list_d",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `limit_list_ths` - 同花顺涨跌停榜

同花顺涨跌停榜只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `limit_list_ths` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"limit_list_ths","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "limit_list_ths",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `limit_step` - 连板天梯

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `limit_step` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"limit_step","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "limit_step",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `major_news` - MAJOR新闻

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `major_news` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"major_news","params":{"limit":20},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "major_news",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `margin` - 融资融券汇总

融资融券汇总只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `margin` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"margin","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "margin",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `margin_detail` - 融资融券明细

融资融券明细只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `margin_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"margin_detail","params":{"ts_code":"600519.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "margin_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `margin_secs` - 融资融券标的

融资融券标的只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `margin_secs` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"margin_secs","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "margin_secs",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow` - 个股资金流向

个股资金流向只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_cnt_ths` - MONEYFLOWCNT同花顺

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_cnt_ths` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"881267.TI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `881267.TI` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_cnt_ths","params":{"ts_code":"881267.TI","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_cnt_ths",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "881267.TI",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_dc` - MONEYFLOWDC

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_dc` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_dc","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_dc",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_hsgt` - 沪深港通资金流向

沪深港通资金流向只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_hsgt` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_hsgt","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_hsgt",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_ind_dc` - MONEYFLOW行业DC

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_ind_dc` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"BK0166.DC","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `BK0166.DC` | 东方财富行业/地域/概念板块代码，使用 BKxxxx.DC 后缀，不是股票代码。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_ind_dc","params":{"ts_code":"BK0166.DC","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_ind_dc",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "BK0166.DC",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_ind_ths` - MONEYFLOW行业同花顺

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_ind_ths` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"881267.TI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `881267.TI` | 同花顺行业/概念代码，使用 .TI 后缀，不是股票代码。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_ind_ths","params":{"ts_code":"881267.TI","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_ind_ths",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "881267.TI",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_mkt_dc` - MONEYFLOW市场DC

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_mkt_dc` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_mkt_dc","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_mkt_dc",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `moneyflow_ths` - 同花顺资金流向

THS 资金流向只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `moneyflow_ths` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"moneyflow_ths","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","buy_sm_amount","sell_sm_amount","net_mf_amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `buy_sm_amount`, `sell_sm_amount`, `net_mf_amount`
行含义：每一行通常是一条资金流向记录。

示例：
```json
{
  "api_name": "moneyflow_ths",
  "columns": [
    "ts_code",
    "trade_date",
    "buy_sm_amount",
    "sell_sm_amount",
    "net_mf_amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "buy_sm_amount": "<buy_sm_amount>",
      "sell_sm_amount": "<sell_sm_amount>",
      "net_mf_amount": "<net_mf_amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `monthly` - A股月线

月线只有在明确历史日期窗口时共享缓存；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `monthly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260430"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260430` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"monthly","params":{"ts_code":"000001.SZ","trade_date":"20260430"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "monthly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260430",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `namechange` - 股票更名记录

更名记录低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `namechange` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"namechange","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "namechange",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `new_share` - 新股发行

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `new_share` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"new_share","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "new_share",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `news` - 新闻资讯

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `news` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"start_date":"2026-04-10 00:00:00","end_date":"2026-04-10 23:59:59"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `2026-04-10 00:00:00` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `2026-04-10 23:59:59` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"news","params":{"start_date":"2026-04-10 00:00:00","end_date":"2026-04-10 23:59:59"},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "news",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `npr` - 政策法规库

Tushare Pro 政策法规库接口，适合按发布机构、政策类型和发布时间窗口共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `npr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"org":"国务院","start_date":"2024-01-01 00:00:00","end_date":"2025-12-31 23:59:59"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["pcode","title","puborg","pubtime","ptype"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `org` | `body.params.org` | 按上游 | `string` | `国务院` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `2024-01-01 00:00:00` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `2025-12-31 23:59:59` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"npr","params":{"org":"国务院","start_date":"2024-01-01 00:00:00","end_date":"2025-12-31 23:59:59"},"fields":["pcode","title","puborg","pubtime","ptype"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`pcode`, `title`, `puborg`, `pubtime`, `ptype`
行含义：每一行通常是一条政策法规或规范性文件记录。

示例：
```json
{
  "api_name": "npr",
  "columns": [
    "pcode",
    "title",
    "puborg",
    "pubtime",
    "ptype"
  ],
  "rows": [
    {
      "pcode": "<pcode>",
      "title": "<title>",
      "puborg": "<puborg>",
      "pubtime": "<pubtime>",
      "ptype": "<ptype>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `opt_basic` - OPTBASIC

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `opt_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"10000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `10000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"opt_basic","params":{"ts_code":"10000001.SH","trade_date":"20260410"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "opt_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "10000001.SH",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `opt_daily` - OPT日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `opt_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"10000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `10000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"opt_daily","params":{"ts_code":"10000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "opt_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "10000001.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `opt_mins` - OPT分钟线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `opt_mins` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"10000001.SH","trade_date":"20260410","freq":"1min"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `10000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1min` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"opt_mins","params":{"ts_code":"10000001.SH","trade_date":"20260410","freq":"1min"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "opt_mins",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "10000001.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `pledge_detail` - 股权质押明细

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `pledge_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"pledge_detail","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "pledge_detail",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `pledge_stat` - 股权质押统计

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `pledge_stat` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"pledge_stat","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "pledge_stat",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `realtime_list` - 实时行情列表

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `realtime_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"src":"dc","page_count":1}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","name","price","pct_chg","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `src` | `body.params.src` | 按上游 | `string` | `dc` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |
| `page_count` | `body.params.page_count` | 按上游 | `integer` | `1` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"realtime_list","params":{"src":"dc","page_count":1},"fields":["ts_code","trade_time","name","price","pct_chg","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `name`, `price`, `pct_chg`, `vol`, `amount`
行含义：每一行通常是一条实时行情快照或实时成交记录。

示例：
```json
{
  "api_name": "realtime_list",
  "columns": [
    "ts_code",
    "trade_time",
    "name",
    "price",
    "pct_chg",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_time": "<trade_time>",
      "name": "<name>",
      "price": "<price>",
      "pct_chg": "<pct_chg>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `realtime_quote` - 实时行情快照

实时快照更新频繁，默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `realtime_quote` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","name","price","pct_chg","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"realtime_quote","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_time","name","price","pct_chg","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `name`, `price`, `pct_chg`, `vol`, `amount`
行含义：每一行通常是一条实时行情快照或实时成交记录。

示例：
```json
{
  "api_name": "realtime_quote",
  "columns": [
    "ts_code",
    "trade_time",
    "name",
    "price",
    "pct_chg",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "name": "<name>",
      "price": "<price>",
      "pct_chg": "<pct_chg>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `realtime_tick` - 实时成交明细

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `realtime_tick` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","src":"dc"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","name","price","pct_chg","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `src` | `body.params.src` | 按上游 | `string` | `dc` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"realtime_tick","params":{"ts_code":"600519.SH","src":"dc"},"fields":["ts_code","trade_time","name","price","pct_chg","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `name`, `price`, `pct_chg`, `vol`, `amount`
行含义：每一行通常是一条实时行情快照或实时成交记录。

示例：
```json
{
  "api_name": "realtime_tick",
  "columns": [
    "ts_code",
    "trade_time",
    "name",
    "price",
    "pct_chg",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "name": "<name>",
      "price": "<price>",
      "pct_chg": "<pct_chg>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `repo_daily` - 回购日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `repo_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"repo_daily","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "repo_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `report_rc` - REPORTRC

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `report_rc` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"report_rc","params":{"limit":20},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "report_rc",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `repurchase` - 股票回购

回购公告属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `repurchase` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","type","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"repurchase","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","type","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `type`, `amount`
行含义：每一行通常是一条公司行为、业绩或披露记录。

示例：
```json
{
  "api_name": "repurchase",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "type",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "type": "<type>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `research_report` - 研究报告

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `research_report` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","title","source","url"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"research_report","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","title","source","url"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `source`, `url`
行含义：每一行通常是一条新闻、公告或研报内容记录。

示例：
```json
{
  "api_name": "research_report",
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "source",
    "url"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "source": "<source>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `rt_etf_k` - ETF 实时日线

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_etf_k` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"510300.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `510300.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_etf_k","params":{"ts_code":"510300.SH"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "rt_etf_k",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "510300.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_etf_sz_iopv` - ETF 实时 IOPV

ETF 实时 IOPV 仅适合有对应上游权限的深市 ETF，实时高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_etf_sz_iopv` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"159915.SZ"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","name","price","pct_chg","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `159915.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_etf_sz_iopv","params":{"ts_code":"159915.SZ"},"fields":["ts_code","trade_time","name","price","pct_chg","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `name`, `price`, `pct_chg`, `vol`, `amount`
行含义：每一行通常是一条实时行情快照或实时成交记录。

示例：
```json
{
  "api_name": "rt_etf_sz_iopv",
  "columns": [
    "ts_code",
    "trade_time",
    "name",
    "price",
    "pct_chg",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "159915.SZ",
      "trade_time": "<trade_time>",
      "name": "<name>",
      "price": "<price>",
      "pct_chg": "<pct_chg>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_fut_min` - 期货实时分钟

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_fut_min` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"CU.SHF","freq":"1MIN"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `CU.SHF` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1MIN` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_fut_min","params":{"ts_code":"CU.SHF","freq":"1MIN"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "rt_fut_min",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_hk_k` - 港股实时日线

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_hk_k` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"00700.HK"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `00700.HK` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_hk_k","params":{"ts_code":"00700.HK"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "rt_hk_k",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700.HK",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_idx_k` - 指数实时日线

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_idx_k` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_idx_k","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "rt_idx_k",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_idx_min` - 指数实时分钟

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_idx_min` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","freq":"1MIN"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1MIN` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_idx_min","params":{"ts_code":"000001.SH","freq":"1MIN"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "rt_idx_min",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_k` - A股实时日线

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_k` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_k","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "rt_k",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_min` - A股实时分钟

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_min` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","freq":"1MIN"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1MIN` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_min","params":{"ts_code":"600519.SH","freq":"1MIN"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "rt_min",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_min_daily` - A股实时分钟日内

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_min_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410","freq":"1MIN"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1MIN` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_min_daily","params":{"ts_code":"600519.SH","trade_date":"20260410","freq":"1MIN"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "rt_min_daily",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_sw_k` - 申万实时日线

Tushare 官网目录补充接口，实时或高频数据默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_sw_k` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"801010.SI"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `801010.SI` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_sw_k","params":{"ts_code":"801010.SI"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "rt_sw_k",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "801010.SI",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `rt_tick` - 分时实时成交

分时实时成交更新频繁，默认不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：NC / none；Redis TTL：-；MySQL TTL：-

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `rt_tick` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","src":"dc"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","name","price","pct_chg","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `false` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `src` | `body.params.src` | 按上游 | `string` | `dc` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"rt_tick","params":{"ts_code":"600519.SH","src":"dc"},"fields":["ts_code","trade_time","name","price","pct_chg","vol","amount"],"use_cache":false}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `name`, `price`, `pct_chg`, `vol`, `amount`
行含义：每一行通常是一条实时行情快照或实时成交记录。

示例：
```json
{
  "api_name": "rt_tick",
  "columns": [
    "ts_code",
    "trade_time",
    "name",
    "price",
    "pct_chg",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "name": "<name>",
      "price": "<price>",
      "pct_chg": "<pct_chg>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "NC"
  }
}
```

### `sf_month` - 社会融资规模

社会融资规模月度数据更新频率低，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `sf_month` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"sf_month","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "sf_month",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `sge_basic` - 上金所BASIC

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `sge_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","name","market","exchange","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"sge_basic","params":{"trade_date":"20260410"},"fields":["ts_code","name","market","exchange","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `name`, `market`, `exchange`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "sge_basic",
  "columns": [
    "ts_code",
    "name",
    "market",
    "exchange",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "name": "<name>",
      "market": "<market>",
      "exchange": "<exchange>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `sge_daily` - 上金所日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `sge_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"sge_daily","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "sge_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `share_float` - 限售股解禁

限售股解禁计划更新频率较低，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `share_float` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"share_float","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "share_float",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `shibor` - Shibor 利率

Shibor 利率只缓存历史日期；最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `shibor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"shibor","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "shibor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `shibor_lpr` - LPR 利率

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `shibor_lpr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"shibor_lpr","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "shibor_lpr",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `shibor_quote` - Shibor 报价

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `shibor_quote` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"shibor_quote","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "shibor_quote",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `slb_len` - 转融资交易汇总

转融资交易汇总只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `slb_len` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"slb_len","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "slb_len",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `slb_sec` - 转融券交易汇总

转融券交易汇总只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `slb_sec` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"slb_sec","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "slb_sec",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `slb_sec_detail` - 转融券交易明细

转融券交易明细只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `slb_sec_detail` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"slb_sec_detail","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "slb_sec_detail",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `st` - 风险警示板列表

ST 风险警示板列表属于低频参考数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `st` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"st","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "st",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stk_ah_comparison` - 股票AHCOMPARISON

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_ah_comparison` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"601318.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `601318.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_ah_comparison","params":{"ts_code":"601318.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_ah_comparison",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "601318.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_alert` - 股票预警

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_alert` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_alert","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_alert",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_auction` - 开盘集合竞价

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_auction` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_auction","params":{"ts_code":"600519.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_auction",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_auction_c` - 收盘集合竞价

收盘集合竞价只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_auction_c` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_auction_c","params":{"ts_code":"600519.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_auction_c",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_auction_o` - 开盘集合竞价明细

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_auction_o` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_auction_o","params":{"ts_code":"600519.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_auction_o",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_factor_pro` - 股票技术因子

股票技术面因子只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_factor_pro` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_factor_pro","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_factor_pro",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_high_shock` - 股票HIGH异动

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_high_shock` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_high_shock","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_high_shock",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_holdernumber` - 股东户数

股东户数属于披露类低频数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_holdernumber` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_holdernumber","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "stk_holdernumber",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stk_holdertrade` - 股东增减持

股东增减持披露低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_holdertrade` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_holdertrade","params":{"ts_code":"600519.SH"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "stk_holdertrade",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stk_limit` - 涨跌停价格

涨跌停价按历史交易日缓存；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_limit` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_limit","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "stk_limit",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_managers` - 管理层名单

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_managers` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_managers","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_managers",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `stk_mins` - 股票分钟线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_mins` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260410","freq":"1min"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_time","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `1min` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_mins","params":{"ts_code":"600519.SH","trade_date":"20260410","freq":"1min"},"fields":["ts_code","trade_time","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根分钟 K 线或一条分钟级行情记录。

示例：
```json
{
  "api_name": "stk_mins",
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_nineturn` - 神奇九转

神奇九转指标只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_nineturn` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_nineturn","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_nineturn",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_premarket` - 盘前数据

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_premarket` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_premarket","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_premarket",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_rewards` - 管理层薪酬

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_rewards` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_rewards","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_rewards",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `stk_shock` - 股票异动

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_shock` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_shock","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_shock",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_surv` - 股票SURV

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_surv` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_surv","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_surv",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `stk_week_month_adj` - 股票WEEKMONTHADJ

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_week_month_adj` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410","freq":"week"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `week` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_week_month_adj","params":{"ts_code":"000001.SZ","trade_date":"20260410","freq":"week"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stk_week_month_adj",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stk_weekly_monthly` - 股票周线月线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stk_weekly_monthly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","trade_date":"20260430","freq":"week"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260430` | 交易日期，通常为 YYYYMMDD。 |
| `freq` | `body.params.freq` | 按上游 | `string` | `week` | 分钟或 K 线周期，常见 1min、5min、15min、30min、60min。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stk_weekly_monthly","params":{"ts_code":"600519.SH","trade_date":"20260430","freq":"week"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "stk_weekly_monthly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260430",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `stock_basic` - 股票基础信息

股票基础信息低频变化，但按天刷新更利于和路由层行为保持一致。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：86400 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stock_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","symbol","name","area","industry","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stock_basic","params":{"ts_code":"000001.SZ"},"fields":["ts_code","symbol","name","area","industry","list_date"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `symbol`, `name`, `area`, `industry`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "stock_basic",
  "columns": [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "symbol": "<symbol>",
      "name": "<name>",
      "area": "<area>",
      "industry": "<industry>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stock_company` - 上市公司资料

上市公司资料低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stock_company` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stock_company","params":{"ts_code":"600519.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stock_company",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stock_hsgt` - 沪深港通股票列表

沪深港通股票列表低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stock_hsgt` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stock_hsgt","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stock_hsgt",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `stock_st` - ST 股票列表

ST 股票列表属于低频参考数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `stock_st` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"limit":20}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `limit` | `body.params.limit` | 按上游 | `integer` | `20` | 返回数量上限；部分接口也支持由服务端分页层处理。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"stock_st","params":{"limit":20},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "stock_st",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `suspend_d` - 停复牌明细

停复牌明细按历史交易日缓存；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `suspend_d` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"suspend_d","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "suspend_d",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `sw_daily` - 申万日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `sw_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"801010.SI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `801010.SI` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"sw_daily","params":{"ts_code":"801010.SI","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "sw_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "801010.SI",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `sz_daily_info` - 深圳日线INFO

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `sz_daily_info` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"sz_daily_info","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "sz_daily_info",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `tdx_daily` - 通达信日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `tdx_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"880001.TDX","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `880001.TDX` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"tdx_daily","params":{"ts_code":"880001.TDX","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "tdx_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "880001.TDX",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `tdx_index` - 通达信指数

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `tdx_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"tdx_index","params":{"ts_code":"000001.SH","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "tdx_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `tdx_member` - 通达信MEMBER

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `tdx_member` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"880001.TDX","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `880001.TDX` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"tdx_member","params":{"ts_code":"880001.TDX","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "tdx_member",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "880001.TDX",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `ths_bk_daily` - 同花顺板块日线

同花顺板块日行情只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_bk_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"871063.TI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `871063.TI` | 同花顺板块代码，使用 .TI 后缀；可先查 `ths_index` 获取有效代码。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_bk_daily","params":{"ts_code":"871063.TI","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "ths_bk_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "871063.TI",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ths_bk_list` - 同花顺板块成分

同花顺板块成分低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_bk_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"881267.TI"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `881267.TI` | 同花顺板块代码，使用 .TI 后缀；可先查 `ths_index` 获取有效代码。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_bk_list","params":{"ts_code":"881267.TI"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ths_bk_list",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "881267.TI",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `ths_daily` - 同花顺指数日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"871063.TI","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `871063.TI` | 同花顺指数/行业代码，使用 .TI 后缀；可先查 `ths_index` 获取有效代码。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_daily","params":{"ts_code":"871063.TI","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "ths_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "871063.TI",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ths_hot` - 同花顺热榜

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_hot` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"885001.TI"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `885001.TI` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_hot","params":{"ts_code":"885001.TI"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "ths_hot",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "885001.TI",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `ths_index` - 同花顺指数目录

同花顺指数/板块目录属于参考数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_index","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ths_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `ths_member` - 同花顺指数成分

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `ths_member` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"881267.TI"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `881267.TI` | 同花顺指数/行业代码，使用 .TI 后缀；可先查 `ths_index` 获取有效代码。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"ths_member","params":{"ts_code":"881267.TI"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "ths_member",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "881267.TI",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `top10_cb_holders` - 可转债前十大持有人

可转债前十大持有人属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `top10_cb_holders` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"113021.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `113021.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"top10_cb_holders","params":{"ts_code":"113021.SH"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "top10_cb_holders",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "113021.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `top10_floatholders` - 前十大流通股东

前十大流通股东属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `top10_floatholders` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"top10_floatholders","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "top10_floatholders",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `top10_holders` - 前十大股东

前十大股东属于披露类数据，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `top10_holders` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"600519.SH","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `600519.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"top10_holders","params":{"ts_code":"600519.SH","period":"20251231"},"fields":["ts_code","ann_date","end_date","holder_name","hold_amount","hold_ratio"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `end_date`, `holder_name`, `hold_amount`, `hold_ratio`
行含义：每一行通常是一条股东、持股或质押相关记录。

示例：
```json
{
  "api_name": "top10_holders",
  "columns": [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "ann_date": "<ann_date>",
      "end_date": "<end_date>",
      "holder_name": "<holder_name>",
      "hold_amount": "<hold_amount>",
      "hold_ratio": "<hold_ratio>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `top_inst` - 龙虎榜机构席位

龙虎榜机构席位只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `top_inst` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"top_inst","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "top_inst",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `top_list` - 龙虎榜每日明细

龙虎榜每日明细只缓存历史日期；当天和未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `top_list` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","name","rank","pct_chg","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"top_list","params":{"trade_date":"20260410"},"fields":["ts_code","trade_date","name","rank","pct_chg","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `rank`, `pct_chg`, `amount`
行含义：每一行通常是一条榜单、热度或涨跌停明细记录。

示例：
```json
{
  "api_name": "top_list",
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "rank",
    "pct_chg",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "name": "<name>",
      "rank": "<rank>",
      "pct_chg": "<pct_chg>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `trade_cal` - 交易日历

交易日历变化极低，适合长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_stock_basic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `trade_cal` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"exchange":"SSE","start_date":"20260401","end_date":"20260430"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["exchange","cal_date","is_open","pretrade_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `exchange` | `body.params.exchange` | 按上游 | `string` | `SSE` | 交易所代码，例如 SSE、SZSE、CFFEX、SHFE。 |
| `start_date` | `body.params.start_date` | 按上游 | `string` | `20260401` | 开始日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |
| `end_date` | `body.params.end_date` | 按上游 | `string` | `20260430` | 结束日期，通常为 YYYYMMDD；新闻类接口也可能支持日期时间字符串。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"trade_cal","params":{"exchange":"SSE","start_date":"20260401","end_date":"20260430"},"fields":["exchange","cal_date","is_open","pretrade_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`exchange`, `cal_date`, `is_open`, `pretrade_date`
行含义：每一行通常是一条交易日历记录。

示例：
```json
{
  "api_name": "trade_cal",
  "columns": [
    "exchange",
    "cal_date",
    "is_open",
    "pretrade_date"
  ],
  "rows": [
    {
      "exchange": "<exchange>",
      "cal_date": "20260410",
      "is_open": "<is_open>",
      "pretrade_date": "<pretrade_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_stock_basic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `us_adjfactor` - 美股复权因子

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_adjfactor` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_adjfactor","params":{"ts_code":"AAPL"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "us_adjfactor",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_balancesheet` - 美股资产负债表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_balancesheet` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","period":"20240930"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20240930` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_balancesheet","params":{"ts_code":"AAPL","period":"20240930"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "us_balancesheet",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `us_basic` - 美股基础资料

美股基础资料低频变化，适合参考类共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_basic` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","symbol","name","area","industry","list_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_basic","params":{"ts_code":"AAPL"},"fields":["ts_code","symbol","name","area","industry","list_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `symbol`, `name`, `area`, `industry`, `list_date`
行含义：每一行通常是一条证券、基金、期货、指数或机构基础资料。

示例：
```json
{
  "api_name": "us_basic",
  "columns": [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "list_date"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "symbol": "<symbol>",
      "name": "<name>",
      "area": "<area>",
      "industry": "<industry>",
      "list_date": "<list_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `us_cashflow` - 美股现金流量表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_cashflow` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","period":"20240930"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20240930` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_cashflow","params":{"ts_code":"AAPL","period":"20240930"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "us_cashflow",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `us_daily` - 美股日线

美股日线只缓存明确历史日期窗口；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_daily` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_daily","params":{"ts_code":"AAPL","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "us_daily",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_daily_adj` - 美股复权日线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_daily_adj` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_daily_adj","params":{"ts_code":"AAPL","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "us_daily_adj",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_fina_indicator` - 美股财务指标

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_fina_indicator` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","period":"20251231"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20251231` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_fina_indicator","params":{"ts_code":"AAPL","period":"20251231"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "us_fina_indicator",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `us_income` - 美股利润表

Tushare 官网目录补充接口，披露/文本类数据适合按查询条件共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`sensitive`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_income` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL","period":"20240930"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","ann_date","f_ann_date","end_date","report_type"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `period` | `body.params.period` | 按上游 | `string` | `20240930` | 报告期，通常为 YYYYMMDD，例如 20251231。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_income","params":{"ts_code":"AAPL","period":"20240930"},"fields":["ts_code","ann_date","f_ann_date","end_date","report_type"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `ann_date`, `f_ann_date`, `end_date`, `report_type`
行含义：每一行通常是一条财务报表或财务指标记录。

示例：
```json
{
  "api_name": "us_income",
  "columns": [
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "ann_date": "<ann_date>",
      "f_ann_date": "<f_ann_date>",
      "end_date": "<end_date>",
      "report_type": "<report_type>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "sensitive",
    "cache_level": "S2"
  }
}
```

### `us_tbr` - 美国国债利率

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_tbr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_tbr","params":{"date":"20260410"},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "us_tbr",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_tltr` - 美股长期利率

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_tltr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_tltr","params":{"date":"20260410"},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "us_tltr",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_tradecal` - 美股交易日历

Tushare 官网目录补充接口，参考类数据低频变化，适合共享长缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：S2 / shared；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_tradecal` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"AAPL"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["exchange","cal_date","is_open","pretrade_date"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `AAPL` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_tradecal","params":{"ts_code":"AAPL"},"fields":["exchange","cal_date","is_open","pretrade_date"],"use_cache":true,"ttl_seconds":3600}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`exchange`, `cal_date`, `is_open`, `pretrade_date`
行含义：每一行通常是一条交易日历记录。

示例：
```json
{
  "api_name": "us_tradecal",
  "columns": [
    "exchange",
    "cal_date",
    "is_open",
    "pretrade_date"
  ],
  "rows": [
    {
      "exchange": "<exchange>",
      "cal_date": "20260410",
      "is_open": "<is_open>",
      "pretrade_date": "<pretrade_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "S2"
  }
}
```

### `us_trltr` - 美股TRLTR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_trltr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_trltr","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "us_trltr",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_trycr` - 美股TRYCR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_trycr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_trycr","params":{"date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "us_trycr",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `us_tycr` - 美股TYCR

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `us_tycr` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["date","item","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `date` | `body.params.date` | 按上游 | `string` | `20260410` | 日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"us_tycr","params":{"date":"20260410"},"fields":["date","item","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`date`, `item`, `value`
行含义：每一行通常是一条宏观经济或利率时间序列记录。

示例：
```json
{
  "api_name": "us_tycr",
  "columns": [
    "date",
    "item",
    "value"
  ],
  "rows": [
    {
      "date": "20260410",
      "item": "<item>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `weekly` - A股周线

周线只有在明确历史日期窗口时共享缓存；最新窗口不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`quote:read_daily`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `weekly` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SZ","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","open","high","low","close","vol","amount"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SZ` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"weekly","params":{"ts_code":"000001.SZ","trade_date":"20260410"},"fields":["ts_code","trade_date","open","high","low","close","vol","amount"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条日线、周线、月线或 K 线行情记录。

示例：
```json
{
  "api_name": "weekly",
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "quote:read_daily",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `wz_index` - 万得指数

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `wz_index` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"ts_code":"000001.SH"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `body.params.ts_code` | 按上游 | `string` | `000001.SH` | Tushare 标准代码，例如 000001.SZ、600519.SH、00700.HK、AAPL。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"wz_index","params":{"ts_code":"000001.SH"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "wz_index",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SH",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

### `yc_cb` - 中债收益率曲线

Tushare 官网目录补充接口，历史日期窗口共享缓存，最新或未带日期查询不缓存。

- 请求路径：`POST /api/v1/query`
- 权限编码：`query:run_generic`
- 产品等级：`standard`
- 缓存：DYNAMIC / shared；Redis TTL：1800 秒；MySQL TTL：259200 秒

请求体字段：

| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `yc_cb` | Tushare 子接口名，固定传当前小节的 `api_name`。 |
| `params` | 否 | `object` | `{"curve_type":"0","trade_date":"20260410"}` | 上游查询参数对象；Minishare 透传给 Tushare，并叠加权限、缓存、审计和限流。 |
| `fields` | 否 | `array<string>` / `string` | `["ts_code","trade_date","value"]` | 返回字段裁剪；不传或传空数组时返回上游默认字段。 |
| `use_cache` | 否 | `boolean` | `true` | 是否允许读取/写入缓存；实时类或 NC 接口通常建议 `false`。 |
| `ttl_seconds` | 否 | `integer` | `1800` | 覆盖本次 Redis 缓存 TTL；不传则按权限策略默认值。 |

`params` 明细：

| 参数 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `curve_type` | `body.params.curve_type` | 按上游 | `string` | `0` | Tushare 上游参数；Minishare 不改名，放在 `params` 内原样透传。 |
| `trade_date` | `body.params.trade_date` | 按上游 | `string` | `20260410` | 交易日期，通常为 YYYYMMDD。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"api_name":"yc_cb","params":{"curve_type":"0","trade_date":"20260410"},"fields":["ts_code","trade_date","value"],"use_cache":true,"ttl_seconds":1800}'
```

返回结果：

统一返回 `QueryResponse` JSON 对象，外层字段稳定，`rows` 内字段由 Tushare 子接口和 `fields` 决定。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 本次调用的 Tushare 子接口名。 |
| `columns` | `array<string>` | 本次实际返回字段。 |
| `rows` | `array<object>` | 数据行；字段随接口和 `fields` 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层，例如 redis、mysql、source。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 权限、缓存、上游调用等元信息。 |

`rows` 常见字段：`ts_code`, `trade_date`, `value`
行含义：每一行通常是一条 Tushare 上游数据记录，字段由 `api_name` 和 `fields` 决定。

示例：
```json
{
  "api_name": "yc_cb",
  "columns": [
    "ts_code",
    "trade_date",
    "value"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "redis",
  "requested_by": "demo",
  "response_meta": {
    "permission_code": "query:run_generic",
    "product_level": "standard",
    "cache_level": "DYNAMIC"
  }
}
```

## AK 能力码明细表

当前内置 AK 能力码共 32 个。是否已经真实可调用，还取决于部署环境的 `AKSHARE_ENTITLEMENTS`、上游 token、用户授权和当前时间窗。

| 能力码 | 名称 | 市场 | 分类 | 模块 | 请求参数 | 返回行含义 | 上游 API |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cn_irm_qa` | 沪深董秘问答 | A股 | 互动问答 | 公司与资讯 | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page`, `market` | 每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。 | `irm_qa_sh, irm_qa_sz` |
| `announcements` | 公告数据 | 全市场 | 公告披露 | 公司与资讯 | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` | 每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。 | `anns_d` |
| `policy_library` | 政策法规库 | 宏观 | 政策法规 | 公司与资讯 | `org`, `ptype`, `keyword`, `start_date`, `end_date`, `limit`, `page` | 每一行通常是一条政策法规或规范性文件记录。 | `npr` |
| `broker_reports` | 券商研报 | 全市场 | 研报 | 公司与资讯 | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` | 每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。 | `research_report` |
| `news` | 新闻资讯 | 全市场 | 资讯 | 公司与资讯 | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page`, `src` | 每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。 | `news` |
| `hk_minute_history` | 港股历史分钟 | 港股 | 分钟历史 | 跨境市场 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `hk_mins` |
| `hk_daily_realtime` | 港股实时日线 | 港股 | 实时日线 | 跨境市场 | `symbol`, `trade_date`, `fields` | 每一行通常是一条当日快照或日线记录。 | `rt_hk_k, index_global` |
| `hk_daily_history` | 港股历史日线 | 港股 | 日线历史 | 跨境市场 | `symbol`, `start_date`, `end_date`, `trade_date`, `adjust`, `fields` | 每一行通常是一条历史日线记录。 | `hk_daily` |
| `us_daily_history` | 美股历史日线 | 美股 | 日线历史 | 跨境市场 | `symbol`, `start_date`, `end_date`, `trade_date`, `adjust`, `fields` | 每一行通常是一条历史日线记录。 | `us_daily` |
| `hk_financial_reports` | 港股财报 | 港股 | 财报 | 跨境市场 | `symbol`, `report_period`, `statement_type`, `limit` | 每一行通常是一条财报科目或财务指标。 | `hk_income, hk_balancesheet, hk_cashflow, hk_fina_indicator` |
| `us_financial_reports` | 美股财报 | 美股 | 财报 | 跨境市场 | `symbol`, `report_period`, `statement_type`, `limit` | 每一行通常是一条财报科目或财务指标。 | `us_income, us_balancesheet, us_cashflow, us_fina_indicator` |
| `etf_minute_history` | ETF历史分钟 | ETF | 分钟历史 | 衍生品与基金 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `stk_mins` |
| `option_minute_history` | 期权历史分钟 | 期权 | 分钟历史 | 衍生品与基金 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `opt_mins` |
| `etf_minute_realtime` | ETF分钟RT | ETF | 分钟实时 | 衍生品与基金 | `symbol`, `period`, `limit` | 每一行通常是一根实时或最近分钟 K 线。 | `rt_min` |
| `convertible_bond_price_change` | 可转债价格变动 | A股 | 可转债 | 衍生品与基金 | `symbol`, `trade_date`, `limit` | 每一行通常是一条上游数据记录。 | `cb_price_chg` |
| `etf_daily_realtime` | ETF日线RT | ETF | 实时日线 | 衍生品与基金 | `symbol`, `trade_date`, `fields` | 每一行通常是一条当日快照或日线记录。 | `rt_etf_k` |
| `futures_minute_history` | 期货历史分钟 | 期货 | 分钟历史 | 期货数据 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `ft_mins` |
| `futures_minute_realtime` | 期货实时分钟 | 期货 | 分钟实时 | 期货数据 | `symbol`, `period`, `limit` | 每一行通常是一根实时或最近分钟 K 线。 | `rt_fut_min` |
| `cn_equity_minute_history` | A股历史分钟 | A股 | 分钟历史 | 基础市场数据 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `stk_mins` |
| `index_minute_history` | 指数历史分钟 | 指数 | 分钟历史 | 基础市场数据 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `idx_mins` |
| `sw_index_minute_history` | 申万指数分钟 | 申万行业 | 分钟历史 | 基础市场数据 | `symbol`, `start_time`, `end_time`, `period`, `adjust` | 每一行通常是一根历史分钟 K 线。 | `sw_mins` |
| `cn_equity_minute_realtime` | A股分钟RT | A股 | 分钟实时 | 基础市场数据 | `symbol`, `period`, `limit` | 每一行通常是一根实时或最近分钟 K 线。 | `rt_min` |
| `index_minute_realtime` | 指数分钟RT | 指数 | 分钟实时 | 基础市场数据 | `symbol`, `period`, `limit` | 每一行通常是一根实时或最近分钟 K 线。 | `rt_idx_min` |
| `cn_equity_daily_realtime` | A股日线RT | A股 | 实时日线 | 基础市场数据 | `symbol`, `trade_date`, `fields` | 每一行通常是一条当日快照或日线记录。 | `rt_k` |
| `index_daily_realtime` | 指数日线RT | 指数 | 实时日线 | 基础市场数据 | `symbol`, `trade_date`, `fields` | 每一行通常是一条当日快照或日线记录。 | `rt_idx_k` |
| `em_concept_boards` | 东方财富概念板块 | 东方财富板块 | 实时行情 | 基础市场数据 | `fields`, `limit`, `page` | 每一行通常是一个板块排行项。 | `stock_board_concept_name_em` |
| `em_industry_boards` | 东方财富行业板块 | 东方财富板块 | 实时行情 | 基础市场数据 | `fields`, `limit`, `page` | 每一行通常是一个板块排行项。 | `stock_board_industry_name_em` |
| `sw_realtime_quotes` | 申万实时行情 | 申万行业 | 实时行情 | 基础市场数据 | `symbol`, `period`, `limit` | 每一行通常是一根实时或最近分钟 K 线。 | `rt_sw_k` |
| `em_concept_board_daily` | 东方财富概念板块日线 | 东方财富板块 | 日线历史 | 基础市场数据 | `symbol`, `trade_date`, `start_date`, `end_date`, `fields`, `limit`, `page` | 每一行通常是一条板块日线记录。 | `dc_daily` |
| `em_industry_board_daily` | 东方财富行业板块日线 | 东方财富板块 | 日线历史 | 基础市场数据 | `symbol`, `trade_date`, `start_date`, `end_date`, `fields`, `limit`, `page` | 每一行通常是一条板块日线记录。 | `dc_daily` |
| `pre_market_capital` | 盘前股本 | A股 | 基础资料 | 基础信息 | `symbol`, `trade_date`, `limit` | 每一行通常是一条上游数据记录。 | `stk_premarket` |
| `call_auction_trades` | 集合竞价成交 | A股 | 盘前行情 | 基础信息 | `symbol`, `trade_date`, `limit` | 每一行通常是一条上游数据记录。 | `stk_auction` |

## AK 统一调用约定

- 请求方式：`GET /api/v1/akshare/{capability_code}`
- 鉴权：`X-API-Key`、浏览器 Session，或已经签发的 AK Bearer Token。
- 参数位置：全部放在 Query String 中。
- 字段裁剪：支持 `fields=a,b,c` 的能力会按字段裁剪 `rows`。
- 返回结构：外层统一，核心数据在 `rows`；`columns` 告诉你本次实际返回了哪些列。

## AK 能力码逐项说明

### `cn_irm_qa` - 沪深董秘问答

查询沪深上市公司董秘问答内容，适合看公司互动回复。 常见写法是先用 symbol 或 keyword 缩小范围，再配合 start_date、end_date、limit 和 page 做分页检索；适合做事件排查、主题搜集和资料归档。

- 请求路径：`GET /api/v1/akshare/cn_irm_qa`
- 所属模块：公司与资讯（`company_content`）
- 市场/分类：A股 / 互动问答
- 权限编码：`akshare:read_disclosure`
- 上游 API：`irm_qa_sh, irm_qa_sz`
- 缓存：S2；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 条件必填 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `keyword` | 否 | `string` | `机器人` | 关键词过滤，用于公告、新闻、研报、政策等内容类能力。 |
| `start_date` | 否 | `string` | `2025-01-01 00:00:00` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2025-12-31 23:59:59` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |
| `market` | 条件必填 | `string` | `sh` | 董秘问答专用。未传 symbol 时可用 market=sh 或 market=sz 指定交易所。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_irm_qa?market=sh&start_date=2025-01-01%2000:00:00&end_date=2025-12-31%2023:59:59&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `question`, `answer`, `pub_date`
行含义：每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 沪深董秘问答 数据。",
  "capability_code": "cn_irm_qa",
  "display_name": "沪深董秘问答",
  "module_code": "company_content",
  "module_name": "公司与资讯",
  "permission_code": "akshare:read_disclosure",
  "available_now": true,
  "request_params": {
    "market": "sh",
    "start_date": "2025-01-01 00:00:00",
    "end_date": "2025-12-31 23:59:59",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "irm_qa_sh",
    "irm_qa_sz"
  ],
  "columns": [
    "ts_code",
    "question",
    "answer",
    "pub_date"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "question": "<question>",
      "answer": "<answer>",
      "pub_date": "<pub_date>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。"
  ]
}
```

### `announcements` - 公告数据

查询上市公司公告数据，适合按股票、关键词或时间范围检索公告。 常见写法是先用 symbol 或 keyword 缩小范围，再配合 start_date、end_date、limit 和 page 做分页检索；适合做事件排查、主题搜集和资料归档。

- 请求路径：`GET /api/v1/akshare/announcements`
- 所属模块：公司与资讯（`company_content`）
- 市场/分类：全市场 / 公告披露
- 权限编码：`akshare:read_disclosure`
- 上游 API：`anns_d`
- 缓存：S2；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `keyword` | 否 | `string` | `机器人` | 关键词过滤，用于公告、新闻、研报、政策等内容类能力。 |
| `start_date` | 否 | `string` | `2025-01-01 00:00:00` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2025-12-31 23:59:59` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/announcements?symbol=600519&start_date=2025-01-01%2000:00:00&end_date=2025-12-31%2023:59:59&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `ann_date`, `title`, `url`
行含义：每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 公告数据 数据。",
  "capability_code": "announcements",
  "display_name": "公告数据",
  "module_code": "company_content",
  "module_name": "公司与资讯",
  "permission_code": "akshare:read_disclosure",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "start_date": "2025-01-01 00:00:00",
    "end_date": "2025-12-31 23:59:59",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "anns_d"
  ],
  "columns": [
    "ts_code",
    "ann_date",
    "title",
    "url"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "ann_date": "<ann_date>",
      "title": "<title>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。"
  ]
}
```

### `policy_library` - 政策法规库

查询政策法规内容，适合按主题或关键词检索政策信息。 建议先看常用参数和请求链接示例，确认代码格式、日期范围和分页条件后再做真实调试。

- 请求路径：`GET /api/v1/akshare/policy_library`
- 所属模块：公司与资讯（`company_content`）
- 市场/分类：宏观 / 政策法规
- 权限编码：`akshare:read_content`
- 上游 API：`npr`
- 缓存：S2；Redis TTL：3600 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `org` | 否 | `string` | `国务院` | 透传给上游或包装层使用的查询参数。 |
| `ptype` | 否 | `string` | `` | 透传给上游或包装层使用的查询参数。 |
| `keyword` | 否 | `string` | `机器人` | 关键词过滤，用于公告、新闻、研报、政策等内容类能力。 |
| `start_date` | 否 | `string` | `2025-01-01 00:00:00` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2025-12-31 23:59:59` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/policy_library?org=国务院&start_date=2025-01-01%2000:00:00&end_date=2025-12-31%2023:59:59&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`pcode`, `title`, `puborg`, `pubtime`, `ptype`
行含义：每一行通常是一条政策法规或规范性文件记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 政策法规库 数据。",
  "capability_code": "policy_library",
  "display_name": "政策法规库",
  "module_code": "company_content",
  "module_name": "公司与资讯",
  "permission_code": "akshare:read_content",
  "available_now": true,
  "request_params": {
    "org": "国务院",
    "start_date": "2025-01-01 00:00:00",
    "end_date": "2025-12-31 23:59:59",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "npr"
  ],
  "columns": [
    "pcode",
    "title",
    "puborg",
    "pubtime",
    "ptype"
  ],
  "rows": [
    {
      "pcode": "<pcode>",
      "title": "<title>",
      "puborg": "<puborg>",
      "pubtime": "<pubtime>",
      "ptype": "<ptype>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条政策法规或规范性文件记录。"
  ]
}
```

### `broker_reports` - 券商研报

查询券商研报内容，适合按股票、机构或关键词检索研报。 常见写法是先用 symbol 或 keyword 缩小范围，再配合 start_date、end_date、limit 和 page 做分页检索；适合做事件排查、主题搜集和资料归档。

- 请求路径：`GET /api/v1/akshare/broker_reports`
- 所属模块：公司与资讯（`company_content`）
- 市场/分类：全市场 / 研报
- 权限编码：`akshare:read_content`
- 上游 API：`research_report`
- 缓存：S2；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `keyword` | 否 | `string` | `机器人` | 关键词过滤，用于公告、新闻、研报、政策等内容类能力。 |
| `start_date` | 否 | `string` | `2025-01-01 00:00:00` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2025-12-31 23:59:59` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/broker_reports?symbol=600519&start_date=2025-01-01%2000:00:00&end_date=2025-12-31%2023:59:59&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `report_date`, `title`, `org`, `analyst`, `url`
行含义：每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 券商研报 数据。",
  "capability_code": "broker_reports",
  "display_name": "券商研报",
  "module_code": "company_content",
  "module_name": "公司与资讯",
  "permission_code": "akshare:read_content",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "start_date": "2025-01-01 00:00:00",
    "end_date": "2025-12-31 23:59:59",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "research_report"
  ],
  "columns": [
    "ts_code",
    "report_date",
    "title",
    "org",
    "analyst",
    "url"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "report_date": "<report_date>",
      "title": "<title>",
      "org": "<org>",
      "analyst": "<analyst>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。"
  ]
}
```

### `news` - 新闻资讯

查询市场新闻资讯，适合跟踪公司或主题相关新闻。 常见写法是先用 symbol 或 keyword 缩小范围，再配合 start_date、end_date、limit 和 page 做分页检索；适合做事件排查、主题搜集和资料归档。

- 请求路径：`GET /api/v1/akshare/news`
- 所属模块：公司与资讯（`company_content`）
- 市场/分类：全市场 / 资讯
- 权限编码：`akshare:read_content`
- 上游 API：`news`
- 缓存：DYNAMIC；Redis TTL：120 秒；MySQL TTL：1800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `keyword` | 否 | `string` | `机器人` | 关键词过滤，用于公告、新闻、研报、政策等内容类能力。 |
| `start_date` | 否 | `string` | `2025-01-01 00:00:00` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2025-12-31 23:59:59` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |
| `src` | 否 | `string` | `cls` | 新闻来源，默认 cls。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/news?src=cls&keyword=机器人&start_date=2025-01-01%2000:00:00&end_date=2025-12-31%2023:59:59&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`datetime`, `source`, `title`, `content`, `url`
行含义：每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 新闻资讯 数据。",
  "capability_code": "news",
  "display_name": "新闻资讯",
  "module_code": "company_content",
  "module_name": "公司与资讯",
  "permission_code": "akshare:read_content",
  "available_now": true,
  "request_params": {
    "src": "cls",
    "keyword": "机器人",
    "start_date": "2025-01-01 00:00:00",
    "end_date": "2025-12-31 23:59:59",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "news"
  ],
  "columns": [
    "datetime",
    "source",
    "title",
    "content",
    "url"
  ],
  "rows": [
    {
      "datetime": "<datetime>",
      "source": "<source>",
      "title": "<title>",
      "content": "<content>",
      "url": "<url>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条内容记录，例如公告、新闻、研报、问答或政策。"
  ]
}
```

### `hk_minute_history` - 港股历史分钟

查询港股历史分钟行情，适合做分钟级复盘分析。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/hk_minute_history`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：港股 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`hk_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `00700` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/hk_minute_history?symbol=00700&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 港股历史分钟 数据。",
  "capability_code": "hk_minute_history",
  "display_name": "港股历史分钟",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "00700",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "hk_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `hk_daily_realtime` - 港股实时日线

查询港股实时日线行情，既可看港股个股，也兼容恒生指数、恒生科技这类常用香港指数快照。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/hk_daily_realtime`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：港股 / 实时日线
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_hk_k, index_global`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：900 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `00700` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `fields` | 否 | `string` | `ts_code,trade_date,open,close,vol` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/hk_daily_realtime?symbol=00700&trade_date=2026-04-10&fields=ts_code,trade_date,open,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条当日快照或日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 港股实时日线 数据。",
  "capability_code": "hk_daily_realtime",
  "display_name": "港股实时日线",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "00700",
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,open,close,vol"
  },
  "upstream_api_names": [
    "rt_hk_k",
    "index_global"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条当日快照或日线记录。"
  ]
}
```

### `hk_daily_history` - 港股历史日线

查询港股历史日线行情，适合做区间走势和复盘分析。 常见写法是用 symbol、start_date、end_date 控制区间，再配合 adjust 和 fields 定义口径；适合做区间走势复盘、对比分析和导出前的数据筛选。

- 请求路径：`GET /api/v1/akshare/hk_daily_history`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：港股 / 日线历史
- 权限编码：`akshare:read_history`
- 上游 API：`hk_daily`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `00700` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_date` | 否 | `string` | `2026-04-01` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2026-04-10` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |
| `fields` | 否 | `string` | `ts_code,trade_date,close` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/hk_daily_history?symbol=00700&start_date=2026-04-01&end_date=2026-04-10&fields=ts_code,trade_date,close" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条历史日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 港股历史日线 数据。",
  "capability_code": "hk_daily_history",
  "display_name": "港股历史日线",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "00700",
    "start_date": "2026-04-01",
    "end_date": "2026-04-10",
    "fields": "ts_code,trade_date,close"
  },
  "upstream_api_names": [
    "hk_daily"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "00700",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条历史日线记录。"
  ]
}
```

### `us_daily_history` - 美股历史日线

查询美股历史日线行情，适合做区间走势和复盘分析。 常见写法是用 symbol、start_date、end_date 控制区间，再配合 adjust 和 fields 定义口径；适合做区间走势复盘、对比分析和导出前的数据筛选。

- 请求路径：`GET /api/v1/akshare/us_daily_history`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：美股 / 日线历史
- 权限编码：`akshare:read_history`
- 上游 API：`us_daily`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `AAPL` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_date` | 否 | `string` | `2026-04-01` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2026-04-10` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |
| `fields` | 否 | `string` | `ts_code,trade_date,close` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/us_daily_history?symbol=AAPL&start_date=2026-04-01&end_date=2026-04-10&fields=ts_code,trade_date,close" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条历史日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 美股历史日线 数据。",
  "capability_code": "us_daily_history",
  "display_name": "美股历史日线",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "AAPL",
    "start_date": "2026-04-01",
    "end_date": "2026-04-10",
    "fields": "ts_code,trade_date,close"
  },
  "upstream_api_names": [
    "us_daily"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条历史日线记录。"
  ]
}
```

### `hk_financial_reports` - 港股财报

查询港股财报数据，适合看公司财务披露内容。 常见写法是按 symbol、report_period 和 statement_type 组合查询；适合按利润表、资产负债表、现金流量表或指标表逐项核对披露内容。

- 请求路径：`GET /api/v1/akshare/hk_financial_reports`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：港股 / 财报
- 权限编码：`akshare:read_disclosure`
- 上游 API：`hk_income, hk_balancesheet, hk_cashflow, hk_fina_indicator`
- 缓存：S2；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `00700` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `report_period` | 否 | `string` | `2024Q4` | 报告期，支持 2025Q4 或 20251231 这类格式。 |
| `statement_type` | 否，默认 income | `string` | `income` | 财报类型：income、balancesheet、cashflow、indicator。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/hk_financial_reports?symbol=00700&report_period=2024Q4&statement_type=income&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `report_period`, `statement_type`, `item_name`, `value`
行含义：每一行通常是一条财报科目或财务指标。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 港股财报 数据。",
  "capability_code": "hk_financial_reports",
  "display_name": "港股财报",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_disclosure",
  "available_now": true,
  "request_params": {
    "symbol": "00700",
    "report_period": "2024Q4",
    "statement_type": "income",
    "limit": "20"
  },
  "upstream_api_names": [
    "hk_income",
    "hk_balancesheet",
    "hk_cashflow",
    "hk_fina_indicator"
  ],
  "columns": [
    "ts_code",
    "report_period",
    "statement_type",
    "item_name",
    "value"
  ],
  "rows": [
    {
      "ts_code": "00700",
      "report_period": "<report_period>",
      "statement_type": "<statement_type>",
      "item_name": "<item_name>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条财报科目或财务指标。"
  ]
}
```

### `us_financial_reports` - 美股财报

查询美股财报数据，适合看公司财务披露内容。 常见写法是按 symbol、report_period 和 statement_type 组合查询；适合按利润表、资产负债表、现金流量表或指标表逐项核对披露内容。

- 请求路径：`GET /api/v1/akshare/us_financial_reports`
- 所属模块：跨境市场（`cross_border`）
- 市场/分类：美股 / 财报
- 权限编码：`akshare:read_disclosure`
- 上游 API：`us_income, us_balancesheet, us_cashflow, us_fina_indicator`
- 缓存：S2；Redis TTL：1800 秒；MySQL TTL：604800 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `AAPL` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `report_period` | 否 | `string` | `2024Q3` | 报告期，支持 2025Q4 或 20251231 这类格式。 |
| `statement_type` | 否，默认 income | `string` | `income` | 财报类型：income、balancesheet、cashflow、indicator。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/us_financial_reports?symbol=AAPL&report_period=2024Q3&statement_type=income&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `report_period`, `statement_type`, `item_name`, `value`
行含义：每一行通常是一条财报科目或财务指标。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 美股财报 数据。",
  "capability_code": "us_financial_reports",
  "display_name": "美股财报",
  "module_code": "cross_border",
  "module_name": "跨境市场",
  "permission_code": "akshare:read_disclosure",
  "available_now": true,
  "request_params": {
    "symbol": "AAPL",
    "report_period": "2024Q3",
    "statement_type": "income",
    "limit": "20"
  },
  "upstream_api_names": [
    "us_income",
    "us_balancesheet",
    "us_cashflow",
    "us_fina_indicator"
  ],
  "columns": [
    "ts_code",
    "report_period",
    "statement_type",
    "item_name",
    "value"
  ],
  "rows": [
    {
      "ts_code": "AAPL",
      "report_period": "<report_period>",
      "statement_type": "<statement_type>",
      "item_name": "<item_name>",
      "value": "<value>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条财报科目或财务指标。"
  ]
}
```

### `etf_minute_history` - ETF历史分钟

查询 ETF 历史分钟行情，适合做分钟级复盘分析。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/etf_minute_history`
- 所属模块：衍生品与基金（`derivatives`）
- 市场/分类：ETF / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`stk_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `510300` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/etf_minute_history?symbol=510300&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 ETF历史分钟 数据。",
  "capability_code": "etf_minute_history",
  "display_name": "ETF历史分钟",
  "module_code": "derivatives",
  "module_name": "衍生品与基金",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "510300",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "stk_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "510300",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `option_minute_history` - 期权历史分钟

查询期权历史分钟行情，适合做分钟级复盘分析。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/option_minute_history`
- 所属模块：衍生品与基金（`derivatives`）
- 市场/分类：期权 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`opt_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `10000001.SH` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/option_minute_history?symbol=10000001.SH&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 期权历史分钟 数据。",
  "capability_code": "option_minute_history",
  "display_name": "期权历史分钟",
  "module_code": "derivatives",
  "module_name": "衍生品与基金",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "10000001.SH",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "opt_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "10000001.SH",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `etf_minute_realtime` - ETF分钟RT

查询 ETF 实时分钟行情，适合盯盘和盘中监控。 常见写法是用 symbol 和 period 看实时节奏，再用 limit 控制返回条数；更适合盯盘、监控和快速回看最近一段盘中变化。

- 请求路径：`GET /api/v1/akshare/etf_minute_realtime`
- 所属模块：衍生品与基金（`derivatives`）
- 市场/分类：ETF / 分钟实时
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_min`
- 缓存：DYNAMIC；Redis TTL：15 秒；MySQL TTL：300 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `510300` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/etf_minute_realtime?symbol=510300&period=1min&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根实时或最近分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 ETF分钟RT 数据。",
  "capability_code": "etf_minute_realtime",
  "display_name": "ETF分钟RT",
  "module_code": "derivatives",
  "module_name": "衍生品与基金",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "510300",
    "period": "1min",
    "limit": "20"
  },
  "upstream_api_names": [
    "rt_min"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "510300",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根实时或最近分钟 K 线。"
  ]
}
```

### `convertible_bond_price_change` - 可转债价格变动

查询可转债价格变动数据，适合看盘中波动和异动情况。 常见写法是按 symbol 和 trade_date 查询单日结果，再用 limit 控制返回规模；适合做盘前快照、单日核对和异动排查。

- 请求路径：`GET /api/v1/akshare/convertible_bond_price_change`
- 所属模块：衍生品与基金（`derivatives`）
- 市场/分类：A股 / 可转债
- 权限编码：`akshare:read_realtime`
- 上游 API：`cb_price_chg`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：900 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `113059.SH` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/convertible_bond_price_change?symbol=113059.SH&trade_date=2026-04-10&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `price`, `pct_change`
行含义：每一行通常是一条上游数据记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 可转债价格变动 数据。",
  "capability_code": "convertible_bond_price_change",
  "display_name": "可转债价格变动",
  "module_code": "derivatives",
  "module_name": "衍生品与基金",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "113059.SH",
    "trade_date": "2026-04-10",
    "limit": "20"
  },
  "upstream_api_names": [
    "cb_price_chg"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "price",
    "pct_change"
  ],
  "rows": [
    {
      "ts_code": "113059.SH",
      "trade_date": "20260410",
      "name": "<name>",
      "price": "<price>",
      "pct_change": "<pct_change>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条上游数据记录。"
  ]
}
```

### `etf_daily_realtime` - ETF日线RT

查询 ETF 实时日线行情，适合看当日基金表现。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/etf_daily_realtime`
- 所属模块：衍生品与基金（`derivatives`）
- 市场/分类：ETF / 实时日线
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_etf_k`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：900 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `510300` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `fields` | 否 | `string` | `ts_code,trade_date,open,close,vol` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/etf_daily_realtime?symbol=510300&trade_date=2026-04-10&fields=ts_code,trade_date,open,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条当日快照或日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 ETF日线RT 数据。",
  "capability_code": "etf_daily_realtime",
  "display_name": "ETF日线RT",
  "module_code": "derivatives",
  "module_name": "衍生品与基金",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "510300",
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,open,close,vol"
  },
  "upstream_api_names": [
    "rt_etf_k"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "510300",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条当日快照或日线记录。"
  ]
}
```

### `futures_minute_history` - 期货历史分钟

查询期货历史分钟行情，适合做历史回看和分钟级分析。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/futures_minute_history`
- 所属模块：期货数据（`futures`）
- 市场/分类：期货 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`ft_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `CU.SHF` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/futures_minute_history?symbol=CU.SHF&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 期货历史分钟 数据。",
  "capability_code": "futures_minute_history",
  "display_name": "期货历史分钟",
  "module_code": "futures",
  "module_name": "期货数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "CU.SHF",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "ft_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `futures_minute_realtime` - 期货实时分钟

查询期货实时分钟行情，适合盯盘和盘中监控。 常见写法是用 symbol 和 period 看实时节奏，再用 limit 控制返回条数；更适合盯盘、监控和快速回看最近一段盘中变化。

- 请求路径：`GET /api/v1/akshare/futures_minute_realtime`
- 所属模块：期货数据（`futures`）
- 市场/分类：期货 / 分钟实时
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_fut_min`
- 缓存：DYNAMIC；Redis TTL：15 秒；MySQL TTL：300 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `CU.SHF` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/futures_minute_realtime?symbol=CU.SHF&period=1min&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根实时或最近分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 期货实时分钟 数据。",
  "capability_code": "futures_minute_realtime",
  "display_name": "期货实时分钟",
  "module_code": "futures",
  "module_name": "期货数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "CU.SHF",
    "period": "1min",
    "limit": "20"
  },
  "upstream_api_names": [
    "rt_fut_min"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "CU.SHF",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根实时或最近分钟 K 线。"
  ]
}
```

### `cn_equity_minute_history` - A股历史分钟

查询 A 股历史分钟行情，适合做分钟级回看和量价分析。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/cn_equity_minute_history`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：A股 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`stk_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_minute_history?symbol=600519&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 A股历史分钟 数据。",
  "capability_code": "cn_equity_minute_history",
  "display_name": "A股历史分钟",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "stk_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `index_minute_history` - 指数历史分钟

查询指数历史分钟行情，适合做盘中走势回看。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/index_minute_history`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：指数 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`idx_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `000001` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/index_minute_history?symbol=000001&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 指数历史分钟 数据。",
  "capability_code": "index_minute_history",
  "display_name": "指数历史分钟",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "000001",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "idx_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `sw_index_minute_history` - 申万指数分钟

查询申万行业指数历史分钟行情，适合看行业盘中走势。 常见写法是用 symbol 搭配 start_time、end_time 和 period 限定分钟区间；排查空结果时，优先确认代码类型、交易日和时间范围是否匹配。

- 请求路径：`GET /api/v1/akshare/sw_index_minute_history`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：申万行业 / 分钟历史
- 权限编码：`akshare:read_history`
- 上游 API：`sw_mins`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `801780` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `start_time` | 否 | `string` | `2026-04-10 09:30:00` | 开始时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `end_time` | 否 | `string` | `2026-04-10 10:30:00` | 结束时间，分钟历史常用，支持 YYYY-MM-DD HH:MM:SS 或 ISO 类格式。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `adjust` | 否 | `string` | `` | 复权/调整参数；当前包装层保留该参数给用户学习和后续扩展，部分上游不会实际使用。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/sw_index_minute_history?symbol=801780&start_time=2026-04-10%2009:30:00&end_time=2026-04-10%2010:30:00&period=1min" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根历史分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 申万指数分钟 数据。",
  "capability_code": "sw_index_minute_history",
  "display_name": "申万指数分钟",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "symbol": "801780",
    "start_time": "2026-04-10 09:30:00",
    "end_time": "2026-04-10 10:30:00",
    "period": "1min"
  },
  "upstream_api_names": [
    "sw_mins"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "801780",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根历史分钟 K 线。"
  ]
}
```

### `cn_equity_minute_realtime` - A股分钟RT

查询 A 股实时分钟行情，适合盯盘和盘中监控。 常见写法是用 symbol 和 period 看实时节奏，再用 limit 控制返回条数；更适合盯盘、监控和快速回看最近一段盘中变化。

- 请求路径：`GET /api/v1/akshare/cn_equity_minute_realtime`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：A股 / 分钟实时
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_min`
- 缓存：DYNAMIC；Redis TTL：15 秒；MySQL TTL：300 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_minute_realtime?symbol=600519&period=1min&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根实时或最近分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 A股分钟RT 数据。",
  "capability_code": "cn_equity_minute_realtime",
  "display_name": "A股分钟RT",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "period": "1min",
    "limit": "20"
  },
  "upstream_api_names": [
    "rt_min"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根实时或最近分钟 K 线。"
  ]
}
```

### `index_minute_realtime` - 指数分钟RT

查询指数实时分钟行情，适合盯盘和盘中监控。 常见写法是用 symbol 和 period 看实时节奏，再用 limit 控制返回条数；更适合盯盘、监控和快速回看最近一段盘中变化。

- 请求路径：`GET /api/v1/akshare/index_minute_realtime`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：指数 / 分钟实时
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_idx_min`
- 缓存：DYNAMIC；Redis TTL：15 秒；MySQL TTL：300 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `000001` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/index_minute_realtime?symbol=000001&period=1min&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根实时或最近分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 指数分钟RT 数据。",
  "capability_code": "index_minute_realtime",
  "display_name": "指数分钟RT",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "000001",
    "period": "1min",
    "limit": "20"
  },
  "upstream_api_names": [
    "rt_idx_min"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根实时或最近分钟 K 线。"
  ]
}
```

### `cn_equity_daily_realtime` - A股日线RT

查询 A 股实时日线行情，适合看当日行情快照。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/cn_equity_daily_realtime`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：A股 / 实时日线
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_k`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：900 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `fields` | 否 | `string` | `ts_code,trade_date,open,close,vol` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_daily_realtime?symbol=600519&trade_date=2026-04-10&fields=ts_code,trade_date,open,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条当日快照或日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 A股日线RT 数据。",
  "capability_code": "cn_equity_daily_realtime",
  "display_name": "A股日线RT",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,open,close,vol"
  },
  "upstream_api_names": [
    "rt_k"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条当日快照或日线记录。"
  ]
}
```

### `index_daily_realtime` - 指数日线RT

查询指数实时日线行情，适合看当日指数表现。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/index_daily_realtime`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：指数 / 实时日线
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_idx_k`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：900 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `000001` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `fields` | 否 | `string` | `ts_code,trade_date,open,close,vol` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/index_daily_realtime?symbol=000001&trade_date=2026-04-10&fields=ts_code,trade_date,open,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一条当日快照或日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 指数日线RT 数据。",
  "capability_code": "index_daily_realtime",
  "display_name": "指数日线RT",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "000001",
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,open,close,vol"
  },
  "upstream_api_names": [
    "rt_idx_k"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "000001",
      "trade_date": "20260410",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条当日快照或日线记录。"
  ]
}
```

### `em_concept_boards` - 东方财富概念板块

查询东方财富概念板块实时排行，适合观察题材热度、板块轮动和领涨概念。 建议先看常用参数和请求链接示例，确认代码格式、日期范围和分页条件后再做真实调试。

- 请求路径：`GET /api/v1/akshare/em_concept_boards`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：东方财富板块 / 实时行情
- 权限编码：`akshare:read_realtime`
- 上游 API：`stock_board_concept_name_em`
- 缓存：S2；Redis TTL：30 秒；MySQL TTL：- 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `fields` | 否 | `string` | `排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/em_concept_boards?fields=排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`rank`, `board_name`, `board_code`, `pct_change`, `up_count`, `down_count`, `leader`
行含义：每一行通常是一个板块排行项。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 东方财富概念板块 数据。",
  "capability_code": "em_concept_boards",
  "display_name": "东方财富概念板块",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "fields": "排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "stock_board_concept_name_em"
  ],
  "columns": [
    "rank",
    "board_name",
    "board_code",
    "pct_change",
    "up_count",
    "down_count",
    "leader"
  ],
  "rows": [
    {
      "rank": "<rank>",
      "board_name": "<board_name>",
      "board_code": "<board_code>",
      "pct_change": "<pct_change>",
      "up_count": "<up_count>",
      "down_count": "<down_count>",
      "leader": "<leader>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一个板块排行项。"
  ]
}
```

### `em_industry_boards` - 东方财富行业板块

查询东方财富行业板块实时排行，适合观察行业强弱、涨跌家数和领涨股票。 建议先看常用参数和请求链接示例，确认代码格式、日期范围和分页条件后再做真实调试。

- 请求路径：`GET /api/v1/akshare/em_industry_boards`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：东方财富板块 / 实时行情
- 权限编码：`akshare:read_realtime`
- 上游 API：`stock_board_industry_name_em`
- 缓存：S2；Redis TTL：30 秒；MySQL TTL：- 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `fields` | 否 | `string` | `排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/em_industry_boards?fields=排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`rank`, `board_name`, `board_code`, `pct_change`, `up_count`, `down_count`, `leader`
行含义：每一行通常是一个板块排行项。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 东方财富行业板块 数据。",
  "capability_code": "em_industry_boards",
  "display_name": "东方财富行业板块",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "fields": "排名,板块名称,板块代码,涨跌幅,上涨家数,下跌家数,领涨股票",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "stock_board_industry_name_em"
  ],
  "columns": [
    "rank",
    "board_name",
    "board_code",
    "pct_change",
    "up_count",
    "down_count",
    "leader"
  ],
  "rows": [
    {
      "rank": "<rank>",
      "board_name": "<board_name>",
      "board_code": "<board_code>",
      "pct_change": "<pct_change>",
      "up_count": "<up_count>",
      "down_count": "<down_count>",
      "leader": "<leader>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一个板块排行项。"
  ]
}
```

### `sw_realtime_quotes` - 申万实时行情

查询申万行业实时行情，适合快速看行业当前表现。 常见写法是用 symbol 和 period 看实时节奏，再用 limit 控制返回条数；更适合盯盘、监控和快速回看最近一段盘中变化。

- 请求路径：`GET /api/v1/akshare/sw_realtime_quotes`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：申万行业 / 实时行情
- 权限编码：`akshare:read_realtime`
- 上游 API：`rt_sw_k`
- 缓存：DYNAMIC；Redis TTL：15 秒；MySQL TTL：300 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `801780` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `period` | 否，默认 1min | `string` | `1min` | 分钟周期，常用 1min、5min、15min、30min、60min；不传时按接口默认 1min。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/sw_realtime_quotes?symbol=801780&period=1min&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_time`, `open`, `high`, `low`, `close`, `vol`, `amount`
行含义：每一行通常是一根实时或最近分钟 K 线。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 申万实时行情 数据。",
  "capability_code": "sw_realtime_quotes",
  "display_name": "申万实时行情",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "801780",
    "period": "1min",
    "limit": "20"
  },
  "upstream_api_names": [
    "rt_sw_k"
  ],
  "columns": [
    "ts_code",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "801780",
      "trade_time": "<trade_time>",
      "open": "<open>",
      "high": "<high>",
      "low": "<low>",
      "close": "<close>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一根实时或最近分钟 K 线。"
  ]
}
```

### `em_concept_board_daily` - 东方财富概念板块日线

查询 Tushare Pro 东方财富概念板块日级行情，适合稳定筛选、入库和复盘。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/em_concept_board_daily`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：东方财富板块 / 日线历史
- 权限编码：`akshare:read_history`
- 上游 API：`dc_daily`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `start_date` | 否 | `string` | `2026-04-01` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2026-04-10` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `fields` | 否 | `string` | `ts_code,trade_date,name,close,pct_change,vol,amount` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/em_concept_board_daily?trade_date=2026-04-10&fields=ts_code,trade_date,name,close,pct_change,vol,amount&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `close`, `pct_change`, `vol`, `amount`
行含义：每一行通常是一条板块日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 东方财富概念板块日线 数据。",
  "capability_code": "em_concept_board_daily",
  "display_name": "东方财富概念板块日线",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,name,close,pct_change,vol,amount",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "dc_daily"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "close",
    "pct_change",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_date": "20260410",
      "name": "<name>",
      "close": "<close>",
      "pct_change": "<pct_change>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条板块日线记录。"
  ]
}
```

### `em_industry_board_daily` - 东方财富行业板块日线

查询 Tushare Pro 东方财富行业板块日级行情，适合稳定筛选、入库和复盘。 常见写法是用 symbol、trade_date 和 fields 取当天快照；如果只关心少数字段，建议显式传 fields，结果会更轻、更适合页面展示。

- 请求路径：`GET /api/v1/akshare/em_industry_board_daily`
- 所属模块：基础市场数据（`market_data`）
- 市场/分类：东方财富板块 / 日线历史
- 权限编码：`akshare:read_history`
- 上游 API：`dc_daily`
- 缓存：S2；Redis TTL：259200 秒；MySQL TTL：259200 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 否 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `start_date` | 否 | `string` | `2026-04-01` | 开始日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `end_date` | 否 | `string` | `2026-04-10` | 结束日期，支持 YYYYMMDD 或 YYYY-MM-DD；资讯类也可传日期时间。 |
| `fields` | 否 | `string` | `ts_code,trade_date,name,close,pct_change,vol,amount` | 返回字段裁剪，逗号分隔；不传则返回上游默认字段。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |
| `page` | 否 | `integer` | `1` | 分页页码，和 limit 一起使用；第一页为 1。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/em_industry_board_daily?trade_date=2026-04-10&fields=ts_code,trade_date,name,close,pct_change,vol,amount&limit=20&page=1" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `name`, `close`, `pct_change`, `vol`, `amount`
行含义：每一行通常是一条板块日线记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 东方财富行业板块日线 数据。",
  "capability_code": "em_industry_board_daily",
  "display_name": "东方财富行业板块日线",
  "module_code": "market_data",
  "module_name": "基础市场数据",
  "permission_code": "akshare:read_history",
  "available_now": true,
  "request_params": {
    "trade_date": "2026-04-10",
    "fields": "ts_code,trade_date,name,close,pct_change,vol,amount",
    "limit": "20",
    "page": "1"
  },
  "upstream_api_names": [
    "dc_daily"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "name",
    "close",
    "pct_change",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_date": "20260410",
      "name": "<name>",
      "close": "<close>",
      "pct_change": "<pct_change>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条板块日线记录。"
  ]
}
```

### `pre_market_capital` - 盘前股本

查询 A 股盘前股本相关数据，适合做开盘前基础资料核对。 常见写法是按 symbol 和 trade_date 查询单日结果，再用 limit 控制返回规模；适合做盘前快照、单日核对和异动排查。

- 请求路径：`GET /api/v1/akshare/pre_market_capital`
- 所属模块：基础信息（`reference`）
- 市场/分类：A股 / 基础资料
- 权限编码：`akshare:read_reference`
- 上游 API：`stk_premarket`
- 缓存：S2；Redis TTL：3600 秒；MySQL TTL：86400 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/pre_market_capital?symbol=600519&trade_date=2026-04-10&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `float_share`, `total_share`
行含义：每一行通常是一条上游数据记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 盘前股本 数据。",
  "capability_code": "pre_market_capital",
  "display_name": "盘前股本",
  "module_code": "reference",
  "module_name": "基础信息",
  "permission_code": "akshare:read_reference",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "trade_date": "2026-04-10",
    "limit": "20"
  },
  "upstream_api_names": [
    "stk_premarket"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "float_share",
    "total_share"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_date": "20260410",
      "float_share": "<float_share>",
      "total_share": "<total_share>"
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条上游数据记录。"
  ]
}
```

### `call_auction_trades` - 集合竞价成交

查询 A 股集合竞价阶段的成交数据，适合看开盘前的撮合情况。 常见写法是按 symbol 和 trade_date 查询单日结果，再用 limit 控制返回规模；适合做盘前快照、单日核对和异动排查。

- 请求路径：`GET /api/v1/akshare/call_auction_trades`
- 所属模块：基础信息（`reference`）
- 市场/分类：A股 / 盘前行情
- 权限编码：`akshare:read_realtime`
- 上游 API：`stk_auction`
- 缓存：DYNAMIC；Redis TTL：30 秒；MySQL TTL：600 秒

请求参数：

| 参数 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | 是 | `string` | `600519` | 标的代码。A 股可传 600519 或 600519.SH；期权、期货通常按上游合约代码传入。 |
| `trade_date` | 否 | `string` | `2026-04-10` | 交易日期，支持 YYYYMMDD 或 YYYY-MM-DD。 |
| `limit` | 否 | `integer` | `20` | 返回数量上限。 |

请求示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/call_auction_trades?symbol=600519&trade_date=2026-04-10&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

返回结果：

统一返回 JSON 对象，外层字段稳定，`rows` 内字段由上游能力决定。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示。 |
| `capability_code` | `string` | 本次调用的 AK 能力码。 |
| `display_name` | `string` | 能力中文名称。 |
| `module_code` / `module_name` | `string` | 所属模块。 |
| `permission_code` | `string` | 命中的权限编码。 |
| `available_now` | `boolean` | 当前凭证、授权和时间窗是否可用。 |
| `request_params` | `object` | 服务端收到的 Query 参数。 |
| `upstream_api_names` | `array<string>` | 实际调用的上游 API 名称。 |
| `columns` | `array<string>` | 本次 rows 的字段列表。 |
| `rows` | `array<object>` | 数据行；字段随能力和 fields 裁剪变化。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存层或 source。 |
| `requested_by` | `string` | 请求用户。 |

`rows` 常见字段：`ts_code`, `trade_date`, `price`, `vol`, `amount`
行含义：每一行通常是一条上游数据记录。

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 集合竞价成交 数据。",
  "capability_code": "call_auction_trades",
  "display_name": "集合竞价成交",
  "module_code": "reference",
  "module_name": "基础信息",
  "permission_code": "akshare:read_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "600519",
    "trade_date": "2026-04-10",
    "limit": "20"
  },
  "upstream_api_names": [
    "stk_auction"
  ],
  "columns": [
    "ts_code",
    "trade_date",
    "price",
    "vol",
    "amount"
  ],
  "rows": [
    {
      "ts_code": "600519",
      "trade_date": "20260410",
      "price": "<price>",
      "vol": "<vol>",
      "amount": "<amount>"
    }
  ],
  "row_count": 1,
  "cached": false,
  "cache_layer": "source",
  "requested_by": "demo",
  "notes": [
    "每一行通常是一条上游数据记录。"
  ]
}
```

## 通用数据接口详情

### `GET /api/v1/akshare/access`

AK 接口统一访问守卫，支持 API Key 或已签发 token，并叠加权限、时间窗与限流校验。

- 鉴权：API Key / Session / Bearer
- 权限：公开/按接口实现

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `entitlement_code` | `query` | 是 | `string` | `cn_equity_daily_realtime` | - |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `provider` | `string` | 见返回示例。 |
| `code` | `string` | 见返回示例。 |
| `display_name` | `string` | 展示名称。 |
| `permission_code` | `string` | 权限编码。 |
| `available_now` | `boolean` | 当前是否可用。 |
| `status` | `string` | 状态值。 |
| `effective_qps` | `integer` | 见返回示例。 |
| `requests_per_minute_limit` | `integer` | 见返回示例。 |
| `grant_source` | `string` | 见返回示例。 |

示例：
```json
{
  "provider": "akshare",
  "code": "cn_equity_daily_realtime",
  "display_name": "A 股日线实时行情",
  "permission_code": "akshare:cn_equity_daily_realtime",
  "available_now": true,
  "status": "available",
  "effective_qps": 1,
  "requests_per_minute_limit": 60,
  "grant_source": "user_grant"
}
```

### `GET /api/v1/akshare/capabilities`

AK 能力中心目录，支持 API Key 或 Session，按模块返回每个能力的包装信息。

- 鉴权：API Key / Session
- 权限：profile:read_self

请求参数：

无。

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 能力目录包含每个能力的请求路径、示例、权限和授权状态。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `usage_reference_url` | `string` | 见返回示例。 |
| `akshare_enabled` | `boolean` | 见返回示例。 |
| `registered_entitlement_count` | `integer` | 见返回示例。 |
| `warnings` | `array<string>` | 警告信息列表。 |
| `modules` | `array<string>` | AK 模块列表。 |
| `capabilities` | `array<string>` | AK 能力列表。 |
| `grant_management` | `object` | AK 授权管理数据。 |
| `materialized_summary` | `object` | 物化数据统计。 |

示例：
```json
{
  "usage_reference_url": "/docs",
  "akshare_enabled": true,
  "registered_entitlement_count": 20,
  "warnings": [],
  "modules": [],
  "capabilities": [],
  "grant_management": {},
  "materialized_summary": {}
}
```

### `GET /api/v1/akshare/capabilities/{capability_code}`

单个 AK 能力的包装详情、参数建议和示例，支持 API Key 或 Session。

- 鉴权：API Key / Session
- 权限：profile:read_self

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `capability_code` | `path` | 是 | `string` | `cn_equity_daily_realtime` | - |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `string` | 见返回示例。 |
| `display_name` | `string` | 展示名称。 |
| `request_path` | `string` | 见返回示例。 |
| `request_fields` | `array<string>` | 见返回示例。 |
| `wrapper_endpoints` | `array<string>` | 见返回示例。 |

示例：
```json
{
  "code": "cn_equity_daily_realtime",
  "display_name": "A 股日线实时行情",
  "request_path": "/api/v1/akshare/cn_equity_daily_realtime",
  "request_fields": [
    "symbol",
    "trade_date"
  ],
  "wrapper_endpoints": []
}
```

### `GET /api/v1/akshare/{capability_code}`

用户直接请求单个 AK 能力的统一入口，内部完成 token、权限、时间窗和 QPS 校验。

- 鉴权：API Key / Session / Bearer
- 权限：公开/按接口实现

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `capability_code` | `path` | 是 | `string` | `cn_equity_daily_realtime` | - |
| `symbol` | `query` | 否 | `string` | `600519.SH` | - |
| `trade_date` | `query` | 否 | `string` | `20260410` | - |
| `start_date` | `query` | 否 | `string` | `20260401` | - |
| `end_date` | `query` | 否 | `string` | `20260410` | - |
| `fields` | `query` | 否 | `string` | `ts_code,trade_date,close,vol` | - |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- AK 统一查询会同时返回包装元信息和数据行。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `string` | 人类可读提示信息。 |
| `capability_code` | `string` | AK 能力编码。 |
| `display_name` | `string` | 展示名称。 |
| `permission_code` | `string` | 权限编码。 |
| `available_now` | `boolean` | 当前是否可用。 |
| `request_params` | `object` | 服务端实际接收的查询参数。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |

示例：
```json
{
  "message": "已通过 Tushare Pro 包装接口返回 A 股日线实时行情 数据。",
  "capability_code": "cn_equity_daily_realtime",
  "display_name": "A 股日线实时行情",
  "permission_code": "akshare:cn_equity_daily_realtime",
  "available_now": true,
  "request_params": {
    "symbol": "600519.SH",
    "trade_date": "20260410"
  },
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "600519.SH",
      "trade_date": "20260410",
      "close": 1688.0,
      "vol": 12345.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "mysql",
  "requested_by": "demo"
}
```

### `GET /api/v1/daily`

行情读接口按当日或历史动态决定缓存。

- 鉴权：API Key / Session
- 权限：quote:read_daily

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `query` | 否 | `string` | `000001.SZ` | - |
| `trade_date` | `query` | 否 | `string` | `20260410` | - |
| `start_date` | `query` | 否 | `string` | `20260401` | - |
| `end_date` | `query` | 否 | `string` | `20260410` | - |
| `fields` | `query` | 否 | `string` | `ts_code,trade_date,open,high,low,close,vol` | - |
| `use_cache` | `query` | 否 | `boolean` | `true` | 是否允许读取缓存。 |
| `ttl_seconds` | `query` | 否 | `integer` | `1800` | 具备覆盖权限时的客户端 TTL。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `GET /api/v1/hot-rank`

本地每日热榜股票快照，同花顺热榜与东方财富热榜合并结果。

- 鉴权：API Key / Session
- 权限：quote:read_daily

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `query` | 否 | `string` | `20260410` | - |
| `ts_code` | `query` | 否 | `string` | `600519.SH` | - |
| `limit` | `query` | 否 | `integer` | `20` | 返回数量上限。 |
| `offset` | `query` | 否 | `integer` | `0` | 分页偏移量。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `GET /api/v1/hot-stocks`

每日热点股票快照：用热门板块、成分关系和个股日线强度组合评分。

- 鉴权：API Key / Session
- 权限：query:run_generic

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `query` | 是 | `string` | `20260410` | - |
| `board_source` | `query` | 否 | `string` | `mixed` | - |
| `ts_code` | `query` | 否 | `string` | `600519.SH` | - |
| `limit` | `query` | 否 | `integer` | `20` | 返回数量上限。 |
| `offset` | `query` | 否 | `integer` | `0` | 分页偏移量。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `GET /api/v1/me`

返回当前主体与默认配额。

- 鉴权：API Key / Session
- 权限：profile:read_self

请求参数：

无。

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 返回当前认证主体和默认配额。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `username` | `string` | 见返回示例。 |
| `display_name` | `string` | 展示名称。 |
| `roles` | `array<string>` | 见返回示例。 |
| `auth_method` | `string` | 见返回示例。 |
| `requests_per_minute` | `integer` | 见返回示例。 |
| `max_active_request_ips` | `integer` | 见返回示例。 |
| `cost_points_per_minute` | `integer` | 见返回示例。 |
| `remaining_cost_points` | `integer` | 见返回示例。 |
| `io_budget` | `object` | 见返回示例。 |
| `active_request_count` | `integer` | 见返回示例。 |
| `active_request_ip_count` | `integer` | 见返回示例。 |
| `active_request_ttl_seconds` | `integer` | 见返回示例。 |
| `active_request_bindings` | `array<object>` | 见返回示例。 |
| `redis_cache_ttl_seconds` | `integer` | 见返回示例。 |
| `mysql_cache_ttl_seconds` | `integer` | 见返回示例。 |

示例：
```json
{
  "username": "demo",
  "display_name": "Demo User",
  "roles": [
    "user"
  ],
  "auth_method": "api_key",
  "requests_per_minute": 60,
  "max_active_request_ips": 1,
  "cost_points_per_minute": 1500,
  "remaining_cost_points": 1475,
  "io_budget": {
    "enabled": true,
    "limit": 1500,
    "window_seconds": 60,
    "current_usage": 25,
    "remaining_cost_points": 1475
  },
  "active_request_count": 1,
  "active_request_ip_count": 1,
  "active_request_ttl_seconds": 30,
  "active_request_bindings": [
    {
      "client_ip": "203.0.113.10",
      "in_flight_requests": 1,
      "request_id": "example-request-id",
      "expires_in_seconds": 29
    }
  ],
  "redis_cache_ttl_seconds": 1800,
  "mysql_cache_ttl_seconds": 86400
}
```

### `POST /api/v1/query`

通用查询，必须叠加 api_name 策略校验。

- 鉴权：API Key / Session
- 权限：query:run_generic

请求参数：

无。

请求体：

| 字段 | 必填 | 类型 | 示例/默认 | 说明 |
| --- | --- | --- | --- | --- |
| `api_name` | 是 | `string` | `` | Minishare 查询接口名 |
| `params` | 否 | `object<string, any>` | `` | Params |
| `fields` | 否 | `array<string>` | `` | Fields |
| `use_cache` | 否 | `boolean` | `True` | Use Cache |
| `ttl_seconds` | 否 | `integer` | `None` | Ttl Seconds |

示例：
```json
{
  "api_name": "daily",
  "params": {
    "ts_code": "000001.SZ",
    "trade_date": "20260410"
  },
  "fields": [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol"
  ],
  "use_cache": true
}
```

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `POST /api/v1/query:batch`

受控批量查询，可传 requests 或 combo_code 展开内置组合。

- 鉴权：API Key / Session
- 权限：query:run_generic

请求参数：

无。

请求体：

| 字段 | 必填 | 类型 | 示例/默认 | 说明 |
| --- | --- | --- | --- | --- |
| `requests` | 否 | `array<QueryBatchItemRequest>` | `` | Requests |
| `combo_code` | 否 | `string` | `None` | Combo Code |
| `params` | 否 | `object<string, any>` | `` | Params |
| `params_by_api` | 否 | `object` | `` | Params By Api |
| `fields_by_api` | 否 | `object` | `` | Fields By Api |
| `use_cache` | 否 | `boolean` | `True` | Use Cache |
| `ttl_seconds` | 否 | `integer` | `None` | Ttl Seconds |

示例：
```json
{
  "combo_code": "cn_equity_daily_core",
  "params": {
    "ts_code": "000001.SZ",
    "trade_date": "20260410"
  }
}
```

返回结果：

- 内容类型：`application/json`
- 子请求失败不会让整批请求直接失败，会进入对应 item 的 `error` 字段。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | `array<object>` | 批量查询子结果列表。 |
| `item_count` | `integer` | 子请求总数。 |
| `ok_count` | `integer` | 成功子请求数量。 |
| `error_count` | `integer` | 失败子请求数量。 |
| `total_row_count` | `integer` | 批量返回总行数。 |

示例：
```json
{
  "items": [
    {
      "request_id": "daily-1",
      "index": 0,
      "api_name": "daily",
      "status_code": 200,
      "ok": true,
      "data": {
        "api_name": "daily",
        "columns": [
          "ts_code",
          "trade_date",
          "close",
          "vol"
        ],
        "rows": [
          {
            "ts_code": "000001.SZ",
            "trade_date": "20260410",
            "close": 10.2,
            "vol": 123456.0
          }
        ],
        "row_count": 1,
        "cached": true,
        "cache_layer": "local_market",
        "requested_by": "demo",
        "response_meta": {
          "api_name": "daily",
          "cache_layer": "local_market"
        }
      },
      "headers": {}
    }
  ],
  "item_count": 1,
  "ok_count": 1,
  "error_count": 0,
  "total_row_count": 1
}
```

### `GET /api/v1/query:catalog`

查询接口目录，返回受控组合查询和批量安全 api_name。

- 鉴权：API Key / Session
- 权限：query:run_generic

请求参数：

无。

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 用于学习哪些 `api_name` 可以批量查询，以及内置 `combo_code`。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `query_api_count` | `integer` | 见返回示例。 |
| `batch_allowed_api_count` | `integer` | 见返回示例。 |
| `batch_allowed_api_names` | `array<string>` | 见返回示例。 |
| `batch_allowed_apis` | `array<string>` | 见返回示例。 |
| `combinations` | `array<string>` | 见返回示例。 |
| `rules` | `array<string>` | 见返回示例。 |

示例：
```json
{
  "query_api_count": 42,
  "batch_allowed_api_count": 12,
  "batch_allowed_api_names": [
    "daily"
  ],
  "batch_allowed_apis": [],
  "combinations": [],
  "rules": []
}
```

### `GET /api/v1/stock-basic`

基础资料共享长缓存。

- 鉴权：API Key / Session
- 权限：quote:read_stock_basic

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `exchange` | `query` | 否 | `string` | `SSE` | 交易所，如 SSE/SZSE。 |
| `list_status` | `query` | 否 | `string` | `L` | 上市状态，默认 L。 |
| `is_hs` | `query` | 否 | `string` | `H` | 沪深港通标记。 |
| `fields` | `query` | 否 | `string` | `ts_code,symbol,name,area,industry,list_date` | - |
| `use_cache` | `query` | 否 | `boolean` | `true` | 是否允许读取缓存。 |
| `ttl_seconds` | `query` | 否 | `integer` | `1800` | 具备覆盖权限时的客户端 TTL。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `GET /api/v1/stock-company`

上市公司资料快捷路由。

- 鉴权：API Key / Session
- 权限：quote:read_stock_basic

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `ts_code` | `query` | 否 | `string` | `600519.SH` | - |
| `exchange` | `query` | 否 | `string` | `SSE` | - |
| `fields` | `query` | 否 | `string` | `ts_code,chairman,manager,secretary,reg_capital,setup_date` | - |
| `use_cache` | `query` | 否 | `boolean` | `true` | 是否允许读取缓存。 |
| `ttl_seconds` | `query` | 否 | `integer` | `1800` | 具备覆盖权限时的客户端 TTL。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

### `GET /api/v1/stock-selection/system`

系统选股：用东财板块热度、成分关系和个股强度组合评分。

- 鉴权：API Key / Session
- 权限：query:run_generic

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `trade_date` | `query` | 否 | `string` | `20260410` | - |
| `board_source` | `query` | 否 | `string` | `mixed` | - |
| `top_boards` | `query` | 否 | `integer` | `5` | - |
| `member_limit_per_board` | `query` | 否 | `integer` | `50` | - |
| `max_quote_candidates` | `query` | 否 | `integer` | `80` | - |
| `limit` | `query` | 否 | `integer` | `20` | - |
| `use_cache` | `query` | 否 | `boolean` | `true` | - |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 系统选股为组合计算结果，字段会随策略版本扩展。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `trade_date` | `string` | 见返回示例。 |
| `selected` | `array<object>` | 见返回示例。 |
| `row_count` | `integer` | 返回行数。 |
| `requested_by` | `string` | 请求用户。 |

示例：
```json
{
  "trade_date": "20260410",
  "selected": [
    {
      "ts_code": "000001.SZ",
      "score": 86.5,
      "reasons": [
        "板块热度",
        "个股强度"
      ]
    }
  ],
  "row_count": 1,
  "requested_by": "demo"
}
```

### `GET /api/v1/trade-calendar`

交易日历快捷路由。

- 鉴权：API Key / Session
- 权限：quote:read_stock_basic

请求参数：

| 名称 | 位置 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `exchange` | `query` | 否 | `string` | `SSE` | - |
| `start_date` | `query` | 否 | `string` | `20260401` | - |
| `end_date` | `query` | 否 | `string` | `20260430` | - |
| `is_open` | `query` | 否 | `string` | `1` | - |
| `fields` | `query` | 否 | `string` | `exchange,cal_date,is_open,pretrade_date` | - |
| `use_cache` | `query` | 否 | `boolean` | `true` | 是否允许读取缓存。 |
| `ttl_seconds` | `query` | 否 | `integer` | `1800` | 具备覆盖权限时的客户端 TTL。 |

请求体：

无请求体。

返回结果：

- 内容类型：`application/json`
- 通用行情类接口统一返回 `QueryResponse` 结构。

主要字段：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `api_name` | `string` | 查询接口名。 |
| `columns` | `array<string>` | 返回数据列名。 |
| `rows` | `array<object>` | 返回数据行。 |
| `row_count` | `integer` | 返回行数。 |
| `cached` | `boolean` | 是否命中缓存。 |
| `cache_layer` | `string` | 命中的缓存或数据层。 |
| `requested_by` | `string` | 请求用户。 |
| `response_meta` | `object` | 稳定响应元信息。 |

示例：
```json
{
  "api_name": "daily",
  "columns": [
    "ts_code",
    "trade_date",
    "close",
    "vol"
  ],
  "rows": [
    {
      "ts_code": "000001.SZ",
      "trade_date": "20260410",
      "close": 10.2,
      "vol": 123456.0
    }
  ],
  "row_count": 1,
  "cached": true,
  "cache_layer": "local_market",
  "requested_by": "demo",
  "response_meta": {
    "api_name": "daily",
    "cache_layer": "local_market"
  }
}
```

