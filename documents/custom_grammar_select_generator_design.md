# 基于 AST 的可自定义语法 SELECT 生成器技术方案

## 1. 背景与目标

当前项目已经具备基于 AST 的随机 SQL 生成能力，核心逻辑主要分布在：

- `sql_generation/random_sql/generator.py`：负责 SELECT 主流程、CTE、集合操作、GROUP BY、ORDER BY、LIMIT 等组装。
- `sql_generation/random_sql/expressions.py`：负责随机表达式、函数调用、字面量、类型兼容等。
- `sql_generation/random_sql/predicates.py`：负责 WHERE 谓词、IN/EXISTS 子查询等。
- `sql_generation/random_sql/subqueries.py`：负责 SELECT 子查询。
- `sql_generation/random_sql/joins.py`：负责 JOIN alias 和 JOIN 条件。
- `sql_generation/random_sql/column_tracker.py`：负责部分列使用跟踪。
- `ast_nodes/`：负责 SQL AST 节点和 `to_sql()` 输出。

现有实现的主要问题是：

1. 随机分支硬编码在 Python 函数中，用户无法声明式控制生成语法。
2. `generator.py` 和 `expressions.py` 职责过重，模块边界不清晰。
3. 列选择、类型约束、作用域可见性、聚合规则、子查询可见性混在各处处理。
4. 子查询、CTE、派生表暴露列的逻辑不统一，容易出现非法列引用。
5. 当前 `ColumnUsageTracker` 更偏“避免重复使用列”，还不足以承担完整的 SQL 语义依赖管理。

目标是将当前生成器改造成：

```text
用户语法配置 -> 语法执行器 -> 模块生成器 -> AST -> 语义校验/修复 -> SQL
```

也就是保留现有 AST 和 `to_sql()` 输出能力，把“随机生成策略”从硬编码函数中抽离出来，使用户可以通过配置定义 SELECT 生成要求。

## 2. 总体架构

建议新增一个可配置生成器包：

```text
sql_generation/configurable_sql/
  __init__.py
  context.py
  grammar_spec.py
  grammar_executor.py
  registry.py
  semantic_validator.py

  generators/
    __init__.py
    select_generator.py
    from_generator.py
    projection_generator.py
    bool_expr_generator.py
    value_expr_generator.py
    predicate_generator.py
    function_generator.py
    subquery_generator.py
    join_generator.py
    group_by_generator.py
    order_by_generator.py
    limit_generator.py

  resolvers/
    __init__.py
    scope_resolver.py
    column_dependency_resolver.py
```

旧入口保持兼容：

```python
def generate_random_sql(tables, functions, current_depth=0) -> str:
    spec = DefaultGrammarSpec()
    ctx = GenContext(
        tables=tables,
        functions=functions,
        dialect=get_current_dialect(),
        max_depth=current_depth,
    )
    node = ConfigurableSqlGenerator(spec).generate(ctx)
    return node.to_sql()
```

这样可以逐步迁移，而不是一次性重写整个生成器。

## 3. 核心组件

### 3.1 GrammarSpec：用户语法配置

第一版建议使用 JSON/YAML 结构化配置，不建议直接实现完整 BNF。完整 BNF 灵活性更强，但需要额外处理递归展开、权重、语义约束、类型约束和模块参数映射，第一阶段成本较高。

建议第一阶段支持如下配置：

```yaml
query:
  root: select
  max_depth: 3

select:
  distinct_prob: 0.1

  projection:
    count: [1, 4]
    expr_kinds:
      column: 0.5
      function: 0.3
      arithmetic: 0.1
      case: 0.1

  from:
    source_kinds:
      table: 0.7
      join: 0.2
      derived_table: 0.1
    join_types: [INNER, LEFT]
    max_joins: 2

  where:
    enabled_prob: 0.8
    expr: bool_expr

  group_by:
    enabled_when: aggregate_used
    max_columns: 3

  having:
    enabled_prob: 0.3
    requires_group_by: true

  order_by:
    enabled_prob: 0.5
    max_columns: 2

  limit:
    enabled_prob: 0.4
    range: [1, 100]

bool_expr:
  max_depth: 3
  atoms:
    comparison: 0.5
    between: 0.1
    in_subquery: 0.2
    exists_subquery: 0.2
  connectors:
    and: 0.45
    or: 0.45
    not: 0.1

subquery:
  max_depth: 2
  locations:
    where: true
    from: true
    select: false
  correlated_prob: 0.4
```

配置原则：

1. 用户描述“允许生成什么”和“概率/深度/数量约束”。
2. 配置不直接拼 SQL 字符串。
3. 配置中的终结符映射到内部模块，例如 `bool_expr`、`comparison`、`exists_subquery`。
4. 所有模块输出 AST，而不是 SQL 字符串。

### 3.2 GrammarExecutor：语法执行器

`GrammarExecutor` 根据 `GrammarSpec` 调用模块生成器。

职责：

- 读取配置。
- 根据权重选择生成路径。
- 控制最大递归深度。
- 构造模块请求对象。
- 调用对应生成器。
- 将生成结果传递给语义处理器。

示意接口：

```python
class GrammarExecutor:
    def __init__(self, spec: GrammarSpec, registry: GeneratorRegistry):
        self.spec = spec
        self.registry = registry

    def generate(self, ctx: GenContext, symbol: str) -> Generated:
        rule = self.spec.get_rule(symbol)
        generator = self.registry.resolve(symbol)
        request = self.build_request(rule, ctx)
        return generator.generate(ctx, request)
```

### 3.3 GeneratorRegistry：模块注册表

模块注册表负责把配置中的语法符号映射到生成器。

```python
registry.register("select", SelectGenerator())
registry.register("from", FromGenerator())
registry.register("projection", ProjectionGenerator())
registry.register("bool_expr", BoolExprGenerator())
registry.register("value_expr", ValueExprGenerator())
registry.register("comparison", PredicateGenerator(kind="comparison"))
registry.register("exists_subquery", SubqueryGenerator(kind="exists"))
```

这样用户配置中的 `bool_expr` 不需要知道 Python 函数名。

### 3.4 GenContext：生成上下文

所有模块都应该通过 `GenContext` 获取状态，避免继续使用散落的全局变量。

```python
@dataclass
class GenContext:
    tables: list[Table]
    functions: list[Function]
    dialect: DBDialect
    rng: random.Random
    spec: GrammarSpec
    scope_resolver: ScopeResolver
    dependency_resolver: ColumnDependencyResolver
    depth: int = 0
    max_depth: int = 3
    flags: dict[str, Any] = field(default_factory=dict)
```

上下文中至少要包含：

- 当前数据库方言。
- 可用表结构。
- 可用函数列表。
- 当前递归深度。
- 随机源。
- 当前作用域栈。
- 列依赖处理器。
- 生成期间产生的标记，例如 `aggregate_used`、`window_used`。

## 4. 模块生成器设计

所有模块统一使用：

```python
class BaseGenerator:
    def generate(self, ctx: GenContext, request: GenerationRequest) -> Generated:
        ...
```

统一返回：

```python
@dataclass
class Generated:
    node: ASTNode
    type_category: str | None = None
    data_type: str | None = None
    output_columns: list[ColumnSymbol] = field(default_factory=list)
    used_aggregate: bool = False
    used_window: bool = False
    referenced_columns: set[ColumnRef] = field(default_factory=set)
```

这样上层模块可以知道子模块生成了什么，而不是只能拿到 AST。

### 4.1 SelectGenerator

职责：

1. 创建 `SelectNode`。
2. push 新 `QueryScope`。
3. 调用 `FromGenerator` 注册当前 FROM 可见表列。
4. 调用 `ProjectionGenerator` 生成 SELECT 表达式。
5. 按配置生成 WHERE、GROUP BY、HAVING、ORDER BY、LIMIT。
6. 根据聚合和非聚合列关系补充或修复 GROUP BY。
7. 生成当前 SELECT 的输出列，供 CTE 或派生表使用。
8. pop 当前作用域。

关键点：

- `WHERE` 不能包含 aggregate/window。
- `HAVING` 必须依赖 GROUP BY 或 aggregate。
- `ORDER BY` 可以引用 select alias，也可以引用可见列。
- 如果 SELECT 中存在 aggregate，非聚合列需要进入 GROUP BY。

### 4.2 FromGenerator

职责：

- 选择基础表。
- 生成表 alias。
- 生成 JOIN。
- 生成 FROM 派生表。
- 把所有 FROM source 注册进当前 `QueryScope`。

示例：

```python
relation = RelationRef(
    alias="t1",
    source=table,
    columns=[ColumnSymbol(...)],
    relation_type="table",
)
ctx.scope_resolver.register_relation(relation)
```

如果生成派生表：

```sql
FROM (SELECT a AS c1, b AS c2 FROM t) sq
```

则需要把子查询输出列注册为：

```text
sq.c1
sq.c2
```

父查询只能看到 `sq.c1`、`sq.c2`，不能直接看到子查询内部的 `t.a`、`t.b`。

### 4.3 ProjectionGenerator

职责：

- 根据配置决定 SELECT 列数量。
- 调用 `ValueExprGenerator` 生成表达式。
- 为表达式分配 alias。
- 注册当前 SELECT 的输出列。

如果表达式是：

```sql
t.age + 1 AS col_1
```

输出列应该记录：

```text
name: col_1
category: numeric
source_expr: ArithmeticNode
```

### 4.4 BoolExprGenerator

职责：

- 生成 boolean 类型表达式。
- 支持 AND/OR/NOT 递归组合。
- 支持 comparison、BETWEEN、IN、EXISTS、IS NULL 等原子谓词。
- 控制最大递归深度。
- 按 clause 限制禁止 aggregate/window。

示意请求：

```python
BoolExprRequest(
    max_depth=3,
    allow_subquery=True,
    allow_outer_ref=True,
    allow_aggregate=False,
    allow_window=False,
)
```

### 4.5 ValueExprGenerator

职责：

- 生成指定类型或任意类型表达式。
- 支持列引用、字面量、函数、算术表达式、CASE、子查询表达式。
- 通过 `ColumnDependencyResolver` 选择类型兼容列。

示意请求：

```python
ValueExprRequest(
    expected_category="numeric",
    allowed_kinds=["column", "literal", "function", "arithmetic"],
    allow_aggregate=True,
    allow_window=False,
)
```

### 4.6 SubqueryGenerator

职责：

- 生成 WHERE 子查询、FROM 派生表、SELECT scalar subquery。
- 控制子查询深度。
- 管理 correlated subquery 的外层列引用。
- 将 FROM 子查询输出列注册给父作用域。

需要区分三类子查询：

#### WHERE 子查询

```sql
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.user_id = u.id
)
```

规则：

- 子查询内部可以引用外层 `u.id`，这是 correlated subquery。
- 父查询不能直接引用子查询内部 `o.user_id`。

#### FROM 派生表

```sql
FROM (
  SELECT user_id, COUNT(*) AS cnt
  FROM orders
  GROUP BY user_id
) sq
```

规则：

- 父查询可以引用 `sq.user_id` 和 `sq.cnt`。
- 父查询不能引用派生表内部原始 alias。

#### SELECT scalar subquery

```sql
SELECT
  u.id,
  (SELECT MAX(o.amount) FROM orders o WHERE o.user_id = u.id) AS max_amount
FROM users u
```

规则：

- 子查询必须返回单列。
- 最好限制为单行语义，例如聚合函数或 LIMIT 1。
- 父查询只能通过 SELECT alias 使用结果。

## 5. 两个贯穿全程的处理器

用户初步设想中的“表列依赖处理器”建议拆成两个处理器：`ScopeResolver` 和 `ColumnDependencyResolver`。

### 5.1 ScopeResolver：作用域与可见性处理器

职责：

- 管理查询作用域栈。
- 记录当前 FROM 中有哪些表、派生表、CTE。
- 判断当前 clause 能看到哪些列。
- 支持 correlated subquery 读取外层列。
- 支持 CTE / derived table 输出列被父查询引用。
- 防止父查询错误引用 WHERE 子查询内部列。

核心数据结构：

```python
@dataclass
class QueryScope:
    level: int
    parent: QueryScope | None
    relations: dict[str, RelationRef]
    select_aliases: dict[str, ColumnSymbol]
    output_columns: dict[str, ColumnSymbol]
    allow_outer_refs: bool = False
```

```python
@dataclass
class RelationRef:
    alias: str
    source_name: str
    relation_type: Literal["table", "cte", "derived"]
    columns: list[ColumnSymbol]
```

```python
@dataclass
class ColumnSymbol:
    name: str
    table_alias: str | None
    data_type: str
    category: str
    nullable: bool
    source_expr: ASTNode | None = None
```

关键接口：

```python
class ScopeResolver:
    def push_scope(self, allow_outer_refs: bool = False) -> QueryScope: ...
    def pop_scope(self) -> QueryScope: ...
    def current_scope(self) -> QueryScope: ...

    def register_relation(self, relation: RelationRef) -> None: ...
    def register_select_alias(self, alias: str, column: ColumnSymbol) -> None: ...
    def export_columns(self, columns: list[ColumnSymbol]) -> None: ...

    def visible_columns(
        self,
        category: str | None = None,
        include_outer: bool = False,
        include_select_aliases: bool = False,
    ) -> list[ColumnSymbol]: ...

    def resolve_column(self, table_alias: str, column_name: str) -> ColumnSymbol | None: ...
```

重要规则：

1. 当前 SELECT 的 FROM source 注册在当前 scope。
2. WHERE/GROUP BY/HAVING 通常引用当前 FROM source。
3. ORDER BY 可以额外引用 SELECT alias。
4. correlated subquery 内部可以引用 parent scope。
5. FROM 派生表和 CTE 需要将输出列注册成新的 RelationRef。
6. WHERE 子查询内部列不会被父 scope 注册。

### 5.2 ColumnDependencyResolver：列依赖与语义约束处理器

职责：

- 按类型选择列。
- 选择类型兼容的左右表达式。
- 维护 SELECT、WHERE、GROUP BY、HAVING、ORDER BY 的列依赖。
- 处理聚合函数导致的 GROUP BY 要求。
- 处理 JOIN ON 的兼容列选择。
- 处理子查询输入/输出列依赖。
- 替代当前分散的 `ColumnUsageTracker` 使用逻辑。

核心接口：

```python
class ColumnDependencyResolver:
    def choose_column(self, ctx: GenContext, request: ColumnRequest) -> ColumnSymbol: ...

    def choose_compatible_pair(
        self,
        ctx: GenContext,
        left_scope: QueryScope,
        right_scope: QueryScope,
        category: str | None = None,
    ) -> tuple[ColumnSymbol, ColumnSymbol]: ...

    def register_select_expr(self, expr: ASTNode, alias: str, generated: Generated) -> ColumnSymbol: ...
    def register_filter_expr(self, expr: ASTNode) -> None: ...
    def require_group_by(self, expr: ASTNode) -> None: ...
    def build_derived_relation(self, subquery: SelectNode, alias: str) -> RelationRef: ...
```

示例请求：

```python
@dataclass
class ColumnRequest:
    category: str | None = None
    data_type: str | None = None
    clause: Literal["select", "where", "join", "group_by", "having", "order_by"] = "select"
    include_outer: bool = False
    allow_reuse: bool = True
    orderable_only: bool = False
    nullable_allowed: bool = True
```

## 6. 子查询列可见性规则

这是设计中最容易出错的部分，需要明确。

### 6.1 父查询可以使用 FROM 子查询输出列

合法：

```sql
SELECT sq.user_id, sq.total_amount
FROM (
  SELECT user_id, SUM(amount) AS total_amount
  FROM orders
  GROUP BY user_id
) sq
WHERE sq.total_amount > 100;
```

原因：

- 子查询作为 FROM source。
- 子查询 SELECT list 暴露了 `user_id` 和 `total_amount`。
- 父查询把它当作虚拟表 `sq` 使用。

处理方式：

1. 子查询生成完成后，从 `select_expressions` 中提取 alias。
2. 构造 `RelationRef(alias="sq", relation_type="derived")`。
3. 注册到父 scope。

### 6.2 父查询不能直接使用 WHERE 子查询内部列

非法：

```sql
SELECT o.amount
FROM users u
WHERE EXISTS (
  SELECT o.amount
  FROM orders o
  WHERE o.user_id = u.id
);
```

原因：

- `o` 只存在于 EXISTS 子查询内部。
- 父查询 FROM 中没有 `o`。
- 子查询 SELECT 的 `o.amount` 不会暴露给父查询。

处理方式：

- `EXISTS` 子查询 pop scope 后，不向父 scope 注册内部 relation。
- 只把该子查询作为 boolean predicate 返回。

### 6.3 子查询可以引用外层列

合法：

```sql
SELECT u.id
FROM users u
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.user_id = u.id
);
```

原因：

- 子查询是 correlated subquery。
- 内层 WHERE 可以引用外层 scope 的 `u.id`。

处理方式：

- 创建子查询 scope 时设置 `allow_outer_refs=True`。
- 内层列选择时 `include_outer=True`。
- `ColumnDependencyResolver.choose_compatible_pair()` 从内层和外层分别选类型兼容列。

## 7. 语义校验与修复

当前 `SelectNode.validate_all_columns()` 和 `repair_invalid_columns()` 已经承担了部分校验修复工作，但新架构建议把错误尽量前移到生成阶段。

建议保留两层：

### 7.1 生成期约束

模块生成时直接避免非法结构：

- WHERE 不生成 aggregate/window。
- HAVING 只在 GROUP BY 或 aggregate 存在时生成。
- ORDER BY 只选择 orderable 类型。
- JOIN ON 选择兼容列。
- 子查询深度不超过配置。
- SELECT scalar subquery 限制单列。

### 7.2 生成后校验

统一 `SemanticValidator` 做兜底：

```python
class SemanticValidator:
    def validate(self, node: SelectNode, ctx: GenContext) -> list[ValidationError]: ...
    def repair(self, node: SelectNode, errors: list[ValidationError], ctx: GenContext) -> SelectNode: ...
```

校验项：

- 所有 ColumnReferenceNode 是否在当前 scope 可见。
- WHERE 是否返回 boolean。
- GROUP BY 是否覆盖非聚合列。
- HAVING 是否合法。
- ORDER BY 是否引用合法列或 SELECT alias。
- 子查询输出列数量是否符合上下文要求。
- 方言是否支持对应语法。

## 8. 与现有代码的迁移关系

建议按阶段迁移。

### 阶段 1：增加上下文和默认配置

新增：

- `GenContext`
- `GrammarSpec`
- `DefaultGrammarSpec`
- `GeneratorRegistry`

此阶段不改变现有生成行为，只包一层适配。

### 阶段 2：抽出 SELECT 主流程

从 `generator.py` 拆出：

- `SelectGenerator`
- `FromGenerator`
- `ProjectionGenerator`
- `GroupByGenerator`
- `OrderByGenerator`
- `LimitGenerator`

旧 `generate_random_sql()` 调用新 `SelectGenerator`。

### 阶段 3：抽出表达式生成器

从 `expressions.py` 和 `predicates.py` 拆出：

- `ValueExprGenerator`
- `BoolExprGenerator`
- `FunctionGenerator`
- `PredicateGenerator`
- `SubqueryGenerator`

保留旧函数作为 wrapper：

```python
def create_where_condition(...):
    ctx = build_legacy_context(...)
    return BoolExprGenerator().generate(ctx, default_request).node
```

### 阶段 4：引入 ScopeResolver

将以下逻辑逐步迁移到 `ScopeResolver`：

- FROM alias 管理。
- 子查询作用域。
- CTE 输出列。
- 派生表输出列。
- 外层列引用。

当前 `FromNode` 和 `SelectNode` 中的校验逻辑先保留，作为兜底。

### 阶段 5：引入 ColumnDependencyResolver

逐步替代：

- `ColumnUsageTracker`
- `get_random_column_with_tracker`
- 表达式中散落的 `random.choice(table.columns)`
- JOIN 条件里的随机列选择
- GROUP BY 修复逻辑

### 阶段 6：接入用户配置

支持：

- YAML/JSON grammar profile。
- clause 开关。
- 模块概率。
- 最大深度。
- 子查询位置控制。
- predicate 类型控制。
- 表达式类型控制。

### 阶段 7：扩展到 BNF 风格语法

当结构化配置稳定后，再考虑支持类似：

```text
query      ::= select
select     ::= SELECT projection FROM from_clause where_clause?
projection ::= module:value_expr[count=1..4]
where_clause ::= WHERE module:bool_expr[max_depth=3]
```

BNF 中的 `module:value_expr` 仍然映射到内部 AST 模块，不直接拼 SQL。

## 9. 示例生成流程

用户配置：

```yaml
select:
  projection:
    count: [2, 3]
    expr_kinds:
      column: 0.7
      function: 0.3
  from:
    source_kinds:
      join: 1.0
    max_joins: 1
  where:
    enabled_prob: 1.0
    expr: bool_expr

bool_expr:
  max_depth: 2
  atoms:
    comparison: 0.7
    exists_subquery: 0.3
```

生成过程：

1. `GrammarExecutor` 从 root `select` 开始。
2. `SelectGenerator` push scope。
3. `FromGenerator` 生成主表和一个 JOIN，并注册 alias。
4. `ProjectionGenerator` 生成 2 到 3 个 SELECT 表达式。
5. `BoolExprGenerator` 生成 WHERE。
6. 如果选择 `exists_subquery`，`SubqueryGenerator` push 子 scope。
7. 子查询内部允许引用外层列，生成 correlated predicate。
8. 子查询 pop scope，不向父 scope 暴露内部表列。
9. `SemanticValidator` 校验 AST。
10. `SelectNode.to_sql()` 输出 SQL。

可能输出：

```sql
SELECT u.id AS col_1, u.name AS col_2
FROM users u
INNER JOIN orders o ON u.id = o.user_id
WHERE EXISTS (
  SELECT 1 AS col_1
  FROM payments p
  WHERE p.order_id = o.id
)
```

## 10. 风险与注意事项

### 10.1 不要过早实现完整 SQL grammar

SQL 语法很大，完整 BNF 生成会迅速遇到语义约束问题。建议先做“结构化配置 + 模块生成器”，稳定后再支持 BNF。

### 10.2 不要让配置直接拼字符串

配置直接拼字符串会绕过 AST 和语义校验，后续很难保证列引用、类型和方言兼容性。

### 10.3 子查询输出列必须显式建模

父查询能不能引用子查询列，取决于子查询出现位置：

- FROM / CTE：可以引用输出列。
- WHERE EXISTS / IN：不能引用内部列。
- SELECT scalar subquery：只能通过 SELECT alias 被外层再使用。

### 10.4 聚合规则要集中处理

不要继续在多个地方临时补 GROUP BY。应由 `ColumnDependencyResolver` 记录：

- 哪些 SELECT 表达式是 aggregate。
- 哪些 SELECT 表达式是非 aggregate。
- 哪些非 aggregate 表达式必须进入 GROUP BY。

### 10.5 方言能力要进入上下文

不同数据库对以下语法支持不同：

- `INTERSECT`
- `EXCEPT`
- `FOR UPDATE`
- window function
- CTE
- JSON/geometry 函数
- LIMIT/OFFSET 语法

模块生成前应查询 `ctx.dialect`，避免生成后再大量修复。

## 11. 推荐的最小可落地版本

第一版不追求覆盖所有 SQL，只实现：

1. 用户可以配置 SELECT 是否包含 JOIN、WHERE、GROUP BY、HAVING、ORDER BY、LIMIT。
2. 用户可以配置 projection 数量和表达式类型。
3. 用户可以配置 boolean expression 最大深度和 predicate 类型。
4. 用户可以配置子查询出现位置和最大深度。
5. 支持 correlated subquery。
6. 支持 FROM derived table 输出列注册。
7. 保留旧生成器行为作为 `default` profile。

完成该版本后，项目会形成清晰边界：

```text
AST 节点：只负责表达 SQL 结构和输出 SQL。
模块生成器：负责生成某类 AST。
GrammarSpec：负责描述用户生成要求。
ScopeResolver：负责表/列可见性。
ColumnDependencyResolver：负责类型、聚合、JOIN、GROUP BY 等依赖。
SemanticValidator：负责最终合法性校验和兜底修复。
```

这是从当前硬编码随机生成器演进到“用户可自定义语法要求的 AST SQL 生成器”的较稳妥路径。
