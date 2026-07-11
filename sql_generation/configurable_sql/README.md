# Configurable SQL Generator 使用说明

本文档说明如何使用当前项目中的 YAML 语法制导 SQL 生成器，以及如何配置 SELECT、JOIN、子查询、聚合、窗口函数、集合操作和不平衡布尔表达式。

## 快速运行

默认语法文件：

```text
grammars/with_join_aggregate.yaml
```

不平衡查询语法模板：

```text
grammars/scor_unbalanced.yaml
```

生成 100 条 SQL 并用 MySQL `127.0.0.1:13306` 执行验证：

```powershell
python scripts\generate_configurable_sql_batch.py --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

只生成、不执行：

```powershell
python scripts\generate_configurable_sql_batch.py --count 100 --output-dir generated_sql --database test --skip-execute
```

指定语法文件：

```powershell
python scripts\generate_configurable_sql_batch.py --grammar grammars/scor_unbalanced.yaml --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

输出文件：

```text
generated_sql/schema.sql
generated_sql/queries.sql
```

## 主流程接入

`main.py` 中通过 `RunSettings` 控制生成器模式：

```python
run_settings = RunSettings(
    dialect_str="mysql",
    oracle="RIFT",
    run_hours=24,
    use_database_tables=False,
    generator_mode="configurable",
    grammar_path="grammars/with_join_aggregate.yaml",
    db_config={
        "host": "127.0.0.1",
        "port": 13306,
        "database": "test",
        "user": "root",
        "password": "123456",
        "dialect": "MYSQL",
    },
)
```

字段说明：

- `generator_mode`: `random` 使用原始随机生成器，`configurable` 使用 YAML 语法制导生成器。
- `grammar_path`: configurable 模式下的 YAML 语法文件路径。
- `dialect_str`: 当前执行和 SQL 渲染使用的方言。
- `use_database_tables`: 是否从真实数据库读取表结构。

## Python API

直接生成一条 SQL：

```python
from data_structures.db_dialect import set_dialect
from generate_random_sql import create_sample_functions, create_sample_tables, generate_configurable_sql

set_dialect("mysql")

sql = generate_configurable_sql(
    create_sample_tables(),
    create_sample_functions(),
    grammar_overrides={
        "select": {
            "where": {"enabled_prob": 0.8},
        }
    },
    seed=1,
)
print(sql)
```

批量生成仍可使用统一入口：

```python
from generate_random_sql import Generate

Generate(
    subquery_depth=2,
    total_insert_statements=40,
    num_queries=100,
    output_dir="generated_sql",
    database_name="test",
    generator_mode="configurable",
    grammar_path="grammars/with_join_aggregate.yaml",
)
```

## YAML 总体结构

典型语法文件结构如下：

```yaml
query:
  root: select
  max_depth: 3

set_operation:
  operation_types: [UNION, UNION ALL, EXCEPT, INTERSECT]
  mixed_operations: true
  query_count: [2, 3]
  projection_count: [1, 3]
  categories: [numeric, string, datetime]

select:
  distinct_prob: 0.15
  projection:
    count: [3, 4]
    expr_kinds:
      column: 0.16
      function: 0.55
      window_function: 0.1
      arithmetic: 0.05
      bool_expr: 0.04
      subquery: 0.1
  from:
    source_kinds:
      join: 0.65
      cte: 0.15
      table: 0.2
    join_source_kinds:
      cte: 0.25
      derived_table: 0.35
      table: 0.4
    join_types: [INNER, LEFT, RIGHT, CROSS]
    max_joins: 2
  where:
    enabled_prob: 0.45
  having:
    enabled_prob: 0.65
  order_by:
    enabled_prob: 0.2
    max_columns: 1
  limit:
    enabled_prob: 0.15
    range: [1, 50]
```

`query.root` 可选：

- `select`: 生成普通 SELECT。
- `set_operation`: 生成集合操作查询。

## SELECT 投影

`select.projection.expr_kinds` 控制 SELECT 列表达式类型：

```yaml
select:
  projection:
    count: [3, 4]
    expr_kinds:
      column: 0.2
      literal: 0.05
      function: 0.35
      aggregate: 0.0
      window_function: 0.1
      arithmetic: 0.1
      bool_expr: 0.1
      subquery: 0.1
    function_types:
      aggregate: 0.5
      scalar: 0.5
```

当前支持的投影种类：

- `column`: 可见列。
- `literal`: 字面量。
- `function`: 标量函数或聚合函数，由 `function_types` 控制比例。
- `window_function`: 窗口函数。
- `arithmetic`: 算术表达式。
- `bool_expr`: 布尔表达式作为 SELECT 列。
- `subquery`: 标量子查询。

当 SELECT 中出现聚合函数时，生成器会自动处理 `GROUP BY` 依赖；这部分不需要用户在 YAML 中手写。

## FROM 和 JOIN

主查询、IN 子查询、EXISTS 子查询都可以分别控制 FROM 随机性。

主查询：

```yaml
select:
  from:
    source_kinds:
      table: 0.2
      join: 0.6
      derived_table: 0.1
      cte: 0.1
    join_source_kinds:
      table: 0.5
      derived_table: 0.3
      cte: 0.2
    join_types: [INNER, LEFT, RIGHT, CROSS]
    max_joins: 2
```

说明：

- `source_kinds`: 第一个 FROM source 的类型。
- `join_source_kinds`: JOIN 右侧 source 的类型。
- `join_types`: JOIN 类型集合。
- `max_joins`: 最多 JOIN 次数，当前会随机生成 `1..max_joins` 个 JOIN。

## WHERE / ON / HAVING 布尔表达式

普通 WHERE 使用 `bool_expr`：

```yaml
bool_expr:
  max_depth: 2
  atom_prob: 0.65
  atoms:
    comparison: 0.28
    is_null: 0.1
    between: 0.12
    like: 0.1
    regexp: 0.05
    exists_subquery: 0.15
    in_subquery: 0.12
    not_in_subquery: 0.05
    any_all_subquery: 0.03
  connectors:
    and: 0.45
    or: 0.45
    not: 0.1
```

JOIN ON 使用 `join_on`，HAVING 使用 `having_bool`。它们的结构和 `bool_expr` 类似，但可以配置不同的原子表达式和递归深度。

## 控制 AND / OR 的左右类型

可以用 `connector_operands` 控制逻辑连接符左右两侧是什么：

```yaml
bool_expr:
  connector_operands:
    and:
      left:
        kind: bool_expr
      right:
        kind: true
```

支持的 `kind`：

- `bool_expr`: 递归生成布尔表达式。
- `atom`: 只生成一个布尔原子。
- `literal`: 布尔字面量。
- `true`: 固定生成 `TRUE`。
- `false`: 固定生成 `FALSE`。

例如 `random_bool_expr AND TRUE`：

```yaml
bool_expr:
  connectors:
    and: 1.0
  connector_operands:
    and:
      left:
        kind: bool_expr
      right:
        kind: true
```

当前统一使用 `kind: bool_expr`，不再保留 `random_bool_expr` 这个名字。

## IN / EXISTS 内部查询单独控制

`IN` 和 `EXISTS` 的内部 SELECT 可以分开配置。

`IN` 子查询：

```yaml
subquery:
  in_subquery:
    from:
      source_kinds:
        table: 0.45
        join: 0.4
        derived_table: 0.1
        cte: 0.05
      join_source_kinds:
        table: 0.55
        derived_table: 0.3
        cte: 0.15
      join_types: [INNER, LEFT, RIGHT, CROSS]
      max_joins: 2
    projection:
      expr_kinds: [column, function, arithmetic, literal]
    where:
      enabled_prob: 0.6
      max_depth: 1
    order_by:
      enabled_prob: 0.25
    limit:
      enabled_prob: 0.0
      range: [1, 50]
```

`EXISTS` 子查询：

```yaml
subquery:
  exists_subquery:
    from:
      source_kinds:
        table: 0.4
        join: 0.45
        derived_table: 0.1
        cte: 0.05
      join_source_kinds:
        table: 0.55
        derived_table: 0.3
        cte: 0.15
      join_types: [INNER, LEFT, RIGHT, CROSS]
      max_joins: 2
    projection:
      expr_kinds: [literal, column]
    where:
      enabled_prob: 0.6
      max_depth: 1
    order_by:
      enabled_prob: 0.25
    limit:
      enabled_prob: 0.25
      range: [1, 50]
```

注意：MySQL 不支持 `IN/ANY/ALL/SOME` 子查询中使用 `LIMIT`，因此默认将 `in_subquery.limit.enabled_prob` 设置为 `0.0`。如果需要专门生成这类不兼容语法，可以手动打开。

## 标量子查询

标量子查询由 SELECT 投影中的 `subquery` 触发：

```yaml
subquery:
  scalar_subquery:
    projection:
      expr_kinds: [column, function, arithmetic, literal]
    where:
      enabled_prob: 0.6
      max_depth: 1
    order_by:
      enabled_prob: 0.5
```

标量子查询会自动加 `LIMIT 1`，用于保证作为单独列时返回单值。

## CTE

CTE 是概率出现的，不会默认每条都生成：

```yaml
select:
  cte:
    enabled_prob: 0.45
    count: [1, 2]
    projection_count: [2, 3]
    where:
      enabled_prob: 0.55
    having:
      enabled_prob: 0.55
    order_by:
      enabled_prob: 0.25
    limit:
      enabled_prob: 0.25
```

CTE 会注册为可见表源，后续 FROM/JOIN 可以引用 CTE 输出列。

## 聚合、GROUP BY 和 HAVING

聚合函数由 `select.projection.function_types.aggregate` 控制概率。生成器会自动处理 `GROUP BY` 依赖，用户不需要单独定义 group by 生成器。

HAVING 从布尔表达式扩展而来：

```yaml
having_bool:
  max_depth: 2
  atom_prob: 0.65
  atoms:
    aggregate_comparison: 0.75
    group_expression_comparison: 0.25
  connectors:
    and: 0.5
    or: 0.35
    not: 0.15
```

支持聚合函数和窗口函数同时出现在同一个 SELECT 中。生成器会将窗口函数依赖列加入 GROUP BY，尽量满足 `only_full_group_by`。

## 窗口函数

窗口函数配置：

```yaml
window_function:
  functions:
    ROW_NUMBER: 1.0
    RANK: 0.8
    DENSE_RANK: 0.8
    NTILE: 0.4
    LAG: 0.5
    LEAD: 0.5
    FIRST_VALUE: 0.4
    LAST_VALUE: 0.4
  partition_by:
    enabled_prob: 0.45
    max_columns: 1
  order_by:
    enabled_prob: 0.95
    max_columns: 1
  frame:
    enabled_prob: 0.0
    clauses:
      - ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

窗口函数内部 `ORDER BY` 会从当前可见、可排序列中随机选择。

## 算术表达式

算术表达式配置：

```yaml
arithmetic:
  operators: ["+", "-", "*", "/", "%"]
```

当前算术表达式主要用于数值列和数值字面量，除法会使用 `NULLIF(..., 0)` 避免除零。

## 集合操作

集合操作配置：

```yaml
query:
  root: set_operation

set_operation:
  operation_types: [UNION, UNION ALL, EXCEPT, INTERSECT]
  mixed_operations: true
  query_count: [2, 3]
  projection_count: [1, 3]
  categories: [numeric, string, datetime]
```

说明：

- `operation_types`: 可选集合操作符。
- `mixed_operations`: 是否允许 `A UNION B EXCEPT C` 这类混合 op 链。
- `query_count`: 集合查询中的 SELECT 个数。
- `projection_count`: 每个 SELECT 的列数。
- `categories`: 每列的类型类别，生成器会保证各分支列数和类别一致。

## Profile Selector

一个 YAML 可以定义多个 profile，生成时按权重随机选择：

```yaml
profiles:
  left_deep_and:
    weight: 0.45
    bool_expr:
      max_depth: 5
      atom_prob: 0.05
      connectors:
        and: 1.0
      connector_operands:
        and:
          left:
            kind: bool_expr
          right:
            kind: atom

  and_true_chain:
    weight: 0.2
    bool_expr:
      connectors:
        and: 1.0
      connector_operands:
        and:
          left:
            kind: bool_expr
          right:
            kind: true
```

固定使用某个 profile：

```yaml
profile: and_true_chain
profiles:
  and_true_chain:
    weight: 1.0
    bool_expr:
      connectors:
        and: 1.0
```

## 生成 SCOR 风格不平衡查询

使用内置模板：

```powershell
python scripts\generate_configurable_sql_batch.py --grammar grammars/scor_unbalanced.yaml --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

模板重点：

- 提高 `bool_expr.max_depth`。
- 降低 `atom_prob`，让布尔树更深。
- 使用 `connector_operands` 形成左深或右深结构。
- 增加 `and true`、`or false` 等不平衡结构。
- 提高子查询、JOIN、derived table 的概率。

## 表列依赖处理

生成器维护两个核心上下文：

- `ScopeResolver`: 管理当前 SELECT、CTE、derived table、JOIN source 的可见列。
- `ColumnDependencyResolver`: 根据上下文和期望类型选择可见列。

derived table 和 CTE 会把 SELECT 输出列注册成新的表源，因此外层查询可以引用它们的别名列，例如 `sq1.col_2`、`cte_1.col_3`。

## 注意事项

- 空间函数已从默认函数集合中移除。
- MySQL 下 `IN/ANY/ALL/SOME` 子查询默认不生成 `LIMIT`。
- `GROUP BY` 由生成器根据 SELECT 表达式自动补齐，不建议用户手写 group by 生成器。
- 如果语法过重，例如 `scor_unbalanced.yaml`，生成成功率通常没问题，但数据库执行可能因为查询过重出现超时。
