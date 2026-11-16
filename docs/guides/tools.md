# MCP 工具接口

工具名称保持稳定。金额写入使用“元”的十进制值，账目查询返回整数“分”。日期采用ISO `YYYY-MM-DD`；默认日期与日期差按 `Asia/Shanghai` 计算。

## household_query

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| scope | overview | overview月度总览、items物品、expenses账目 |
| month | 当前月 | 月度账目范围，形如2026-12 |
| offset / limit | 0 / 20 | 偏移与分页，limit为1–30 |
| name / location | null | 物品名称/位置子串，最多100字符，不接受空白 |
| expiry | all | all / overdue / today / within_days / unset |
| days | 7 | within_days的上界，0–3660天 |

name/location/expiry/days的非默认筛选仅能与scope=items一起使用，否则返回错误。物品不按month过滤。

```json
{"scope":"items","name":"牛奶","location":"冷藏","limit":3}
```

物品结果包含 `as_of`、`timezone`、`item_count`、`unknown_due_count`、`records`、`has_more`。item_count是过滤后的总数，不是当前页大小。unknown_due_count是名称/位置范围内未填日期的数量，计算在到期筛选之前。

每项记录含ID、version、数量、单位、位置、入库日、due/due_source，并附加days_until_due和expiry_status：

- overdue：日期早于今天。
- today：日期等于今天。
- within_days：今天至第N天，含两端，不含已经超期的记录。
- unset：未填写日期，剩余天数为null。
- 返回记录中的future：日期晚于今天。

按到期日、名称、ID排序；未填日期排在最后。同名不同批次不合计为一个“到期日”。未来N天没有结果，不等于家中所有物品都安全。

## household_record

```json
{
  "request_id":"example-item-20261201-001",
  "changes":[
    {"action":"add_item","name":"牛奶","quantity":"2","unit":"盒","location":"冰箱冷藏上层","due":"2026-12-20"},
    {"action":"expense","name":"牛奶","amount":"18.80","category":"餐饮","payment":"微信"}
  ]
}
```

这是文档示例，不会自动执行。请求ID为8–100字符，字符集是字母、数字、下划线、连字符；同内容重试复用ID，不同内容不得复用。

每次最多20项，全部成功才提交。`add_item`需要名称、正数量、单位、位置。due仅取用户明确日期；未知日期留空。`expense`需要正金额，kind可为支出/收入/转账/退款。

修改先查询获取唯一record_id和expected_version：

```json
{"request_id":"example-move-001","changes":[{"action":"update","name":"备用电池","record_id":"<query-result-id>","expected_version":1,"location":"玄关抽屉"}]}
```

`update`保留原位置/费用金额调用，物品新增以下可选字段：

| 字段 | 语义 |
| --- | --- |
| name | 原记录名称；仍为必填。改名不会改变记录ID |
| new_name | 新名称；必须同时指定record_id |
| location | 新位置；省略不变 |
| due | 用户明确日期；省略或null不修改 |
| clear_due | true明确清空日期并将due_source改为unset；不能同时设置due |
| set_quantity | 绝对余量，0–100000，最多3位小数；必须提供原unit，不换算单位 |

`consume.quantity`是扣减量，必须大于0，不能与set_quantity混用。`update.quantity`拒绝，避免把“改为2盒”误解为“用掉2盒”。绝对余量为0与取用耗尽一致：记录软删除，仍可撤销恢复。

修改和取用须先查询版本；同名多批必须使用record_id，不随机选择。单一名称匹配的旧调用继续有效；改名始终要求ID。无纠错字段、错误单位、空白名称、无效日期拒绝写入。多项操作任一失败即整体回滚。

```json
{"request_id":"test-correction-001","changes":[{"action":"update","name":"测试牛奶","record_id":"从查询取得的编号","expected_version":1,"new_name":"测试酸奶","location":"测试冷藏二层","clear_due":true,"set_quantity":"2","unit":"盒"}]}
```

request_id是业务幂等标识，区别于JSON-RPC id。响应丢失后必须保留原ID与原参数；已成功的请求重试返回原records和`replayed=true`，不追加审计。即使该操作后来被撤销，也不会再次执行。省略on的跨日重试沿用首次记录日期；明确传入不同on仍冲突。工具桥不会替用户自动重放写入。

结果含status、message、records、replayed。重复成功请求返回原结果及replayed=true。调用失败应按明确错误处理，不得声称已保存。

## household_undo

```json
{"request_id":"example-undo-001"}
```

撤销最近一笔尚未撤销且有业务变化的操作，可一次撤销多项原子写入。它不能按任意日期或任意记录ID删除，也不撤销物理动作。不存在可撤销记录或记录内容已变化时返回冲突。撤销本身追加审计，记录版本增长。

## 超时与安全

工具20秒期限不是分布式事务取消协议。超时后不能直接换新ID再写；保留原ID重试以查询幂等结果。语音模型如何编排工具是上游行为，最终需真人验收。详见[安全说明](../../SECURITY.md)。
