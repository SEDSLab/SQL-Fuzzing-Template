# Configurable SQL Generator 浣跨敤璇存槑

鏈枃妗ｈ鏄庡浣曚娇鐢?`sql_generation/configurable_sql` 涓嬬殑 YAML 椹卞姩 SELECT 鐢熸垚鍣ㄣ€?
## 蹇€熻繍琛?
榛樿璇硶鏂囦欢锛?
```text
grammars/with_join_aggregate.yaml
```

涓嶅钩琛?bool 鏍戣娉曟ā鏉匡細

```text
grammars/scor_unbalanced.yaml
```

鐢熸垚 100 鏉?SQL锛屽苟浣跨敤 MySQL `127.0.0.1:13306` 鎵ц楠岃瘉锛?
```powershell
python scripts\generate_configurable_sql_batch.py --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

杈撳嚭鏂囦欢锛?
```text
generated_sql/schema.sql
generated_sql/queries.sql
```

鍙敓鎴愪笉鎵ц锛?
```powershell
python scripts\generate_configurable_sql_batch.py --count 100 --output-dir generated_sql --database test --dialect mysql --skip-execute
```

鎸囧畾鑷畾涔?YAML锛?
```powershell
python scripts\generate_configurable_sql_batch.py --grammar path\to\your.yaml --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

浣跨敤涓嶅钩琛℃煡璇㈡ā鏉匡細

```powershell
python scripts\generate_configurable_sql_batch.py --grammar grammars/scor_unbalanced.yaml --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

## Python API

```python
from data_structures.db_dialect import set_dialect
from generate_random_sql import create_sample_functions, create_sample_tables, generate_configurable_sql

set_dialect("mysql")

tables = create_sample_tables()
functions = create_sample_functions()

sql = generate_configurable_sql(
    tables,
    functions,
    grammar_overrides={
        "select": {
            "projection": {
                "count": [3, 3],
                "expr_kinds": {
                    "column": 0.5,
                    "function": 0.5,
                },
            }
        }
    },
    seed=1,
)

print(sql)
```

## YAML 鎬讳綋缁撴瀯

甯歌缁撴瀯锛?
```yaml
query:
  root: select
  max_depth: 3

select:
  distinct_prob: 0.15
  cte: ...
  projection: ...
  from: ...
  where: ...
  having: ...
  order_by: ...
  limit: ...

bool_expr: ...
join_on: ...
having_bool: ...
subquery: ...
window_function: ...
arithmetic: ...
```

`enabled_prob` 琛ㄧず璇ュ瓙鍙ュ嚭鐜版鐜囥€?
`expr_kinds`銆乣atoms`銆乣connectors` 绛?map 琛ㄧず鍔犳潈闅忔満閫夋嫨銆傛潈閲嶅彧闇€瑕佺浉瀵瑰ぇ灏忥紝涓嶈姹傛€诲拰涓?1銆?
## 澶?Profile 璇硶閫夋嫨

鍚屼竴涓?YAML 鍙互瀹氫箟澶氫釜 profile銆傛瘡娆＄敓鎴愪竴鏉?SQL 鏃讹紝鐢熸垚鍣ㄤ細鎸?profile 鏉冮噸閫夋嫨涓€涓?profile锛屽苟鎶婅 profile 鐨勯厤缃悎骞跺埌鍩虹閰嶇疆涓娿€?
绀轰緥锛?
```yaml
select:
  where:
    enabled_prob: 1.0

profiles:
  scor_unbalanced:
    weight: 0.7
    bool_expr:
      max_depth: 4
      atom_prob: 0.0
      connectors:
        and: 1.0
      connector_operands:
        and:
          left:
            kind: bool_expr
          right:
            kind: atom

  and_true:
    weight: 0.3
    bool_expr:
      max_depth: 2
      atom_prob: 0.0
      connectors:
        and: 1.0
      connector_operands:
        and:
          left:
            kind: atom
          right:
            kind: literal
            value: true
```

涔熷彲浠ヤ娇鐢?`overrides` 鍖呰捣鏉ワ細

```yaml
profiles:
  scor_unbalanced:
    weight: 0.7
    overrides:
      bool_expr:
        max_depth: 4
        atom_prob: 0.0
```

濡傛灉甯屾湜鍥哄畾浣跨敤鏌愪竴涓?profile锛屽彲浠ュ湪 YAML 椤跺眰鎸囧畾锛?
```yaml
profile: scor_unbalanced
```

鎴栬€呭湪 Python API 浼犲叆锛?
```python
grammar_overrides = {
    "profile": "scor_unbalanced",
    "profiles": {
        "scor_unbalanced": {
            "weight": 1.0,
            "bool_expr": {
                "max_depth": 4,
            },
        }
    },
}
```

瑙勫垯锛?
```text
鍩虹 YAML 鍏堝姞杞?鎸夋潈閲嶉€夋嫨 profile
profile 閰嶇疆瑕嗙洊鍩虹 YAML
鍐嶄笌 default_select_spec 鍚堝苟
```

娉ㄦ剰锛歚profiles` 涓嬬殑鏈煡 profile 涓嶄細鑷姩鎵ц锛屽彧鏈夎鏉冮噸閫変腑鎴栬 `profile:` 鏄惧紡鎸囧畾鏃舵墠浼氱敓鏁堛€?
### 涓嶅钩琛℃煡璇㈡ā鏉?
椤圭洰鍐呯疆浜嗕竴浠戒笉骞宠　 bool 鏍戞ā鏉匡細

```text
grammars/scor_unbalanced.yaml
```

瀹冪敤浜庣敓鎴愮被浼?SCOR 椋庢牸鐨勫亸鏂?bool 鏉′欢锛屼緥濡傦細

```sql
WHERE (((((a > 1 AND b IS NOT NULL) AND c BETWEEN 1 AND 10) AND d IN (SELECT ...)) AND e LIKE '%x%') AND f <> 3)
```

妯℃澘鍐呯疆 profile锛?
```text
left_deep_and    -- 宸﹁竟閫掑綊 bool_expr锛屽彸杈?atom锛屽舰鎴愬乏娣?AND 鏍?left_deep_or     -- 宸﹁竟閫掑綊 bool_expr锛屽彸杈?atom锛屽舰鎴愬乏娣?OR 鏍?and_true_chain   -- 宸﹁竟閫掑綊 bool_expr锛屽彸杈?TRUE锛屽舰鎴?AND TRUE 閾?mixed_unbalanced -- AND/OR/NOT 娣峰悎锛屼絾浠嶄繚鎸佸乏娣卞亸鏂?```

鏍稿績鍐欐硶锛?
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
```

濡傛灉瑕佸浐瀹氫娇鐢ㄦ煇涓€绉嶄笉骞宠　 profile锛屽湪 `scor_unbalanced.yaml` 椤跺眰鍔犲叆锛?
```yaml
profile: left_deep_and
```

鎴栬€咃細

```yaml
profile: and_true_chain
```

`and_true_chain` 浼氱敓鎴愮被浼硷細

```sql
WHERE ((((t1.c1 > 10) AND TRUE) AND TRUE) AND TRUE)
```

寤鸿淇敼璇ユā鏉垮悗鎵ц锛?
```powershell
python scripts\generate_configurable_sql_batch.py --grammar grammars/scor_unbalanced.yaml --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

鏈€杩戜竴娆￠獙璇佺粨鏋滐細

```text
generated=100
query_execution=completed, total=103, passed=103, failed=0, accuracy=100.00%
```

## SELECT 鎶曞奖閰嶇疆

```yaml
select:
  projection:
    count: [3, 4]
    expr_kinds:
      column: 0.16
      function: 0.55
      window_function: 0.1
      arithmetic: 0.05
      bool_expr: 0.04
      subquery: 0.1
    function_types:
      aggregate: 0.65
      scalar: 0.35
    bool_expr:
      max_depth: 1
```

鏀寔鐨勬姇褰辫〃杈惧紡绫诲瀷锛?
```text
column
literal
function
window_function
arithmetic
bool_expr
subquery
```

绀轰緥杈撳嚭锛?
```sql
SELECT
  t1.c1 AS col_1,
  SUM(t1.c2) AS col_2,
  ROW_NUMBER() OVER (ORDER BY t1.c1 DESC) AS col_3,
  (t1.c3 + 10) AS col_4,
  t1.c4 BETWEEN 1 AND 50 AS col_5
FROM t1 AS t1
```

褰撳墠鏅€?YAML 浠嶆槸鍏ㄥ眬姒傜巼鎺у埗锛屼笉鏀寔鐩存帴鎸囧畾鈥滅 1 鍒楀繀椤绘槸 column锛岀 2 鍒楀繀椤绘槸 aggregate鈥濄€傚鏋滈渶瑕佸浐瀹氭瘡涓?projection slot锛岄渶瑕佺户缁墿灞?`projection.expressions`銆?
## FROM / JOIN 閰嶇疆

```yaml
select:
  from:
    source_kinds:
      join: 0.65
      cte: 0.15
      table: 0.2
    join_source_kinds:
      cte: 0.25
      derived_table: 0.35
      table: 0.4
    join_types: [INNER, LEFT]
    max_joins: 1
```

鏀寔锛?
```text
鏅€氳〃 FROM
FROM CTE
FROM derived table
JOIN 鏅€氳〃
JOIN CTE
JOIN derived table
```

JOIN ON 浣跨敤 `join_on` 鐨?bool 瑙勫垯鐢熸垚锛屼笉鍥哄畾涓哄乏鍙冲垪姣旇緝銆?
## WHERE / Bool 琛ㄨ揪寮忛厤缃?
涓绘煡璇?WHERE 鍑虹幇姒傜巼锛?
```yaml
select:
  where:
    enabled_prob: 0.45
```

WHERE 鍐呴儴缁撴瀯鐢?`bool_expr` 鎺у埗锛?
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

`atom_prob` 琛ㄧず褰撳墠灞傜洿鎺ョ敓鎴?atom 鐨勬鐜囥€傛病鏈夊懡涓?atom 鏃讹紝浼氫娇鐢?`connectors` 鐢熸垚 `AND / OR / NOT` 缁勫悎銆?
鏀寔鐨?bool atom锛?
```text
comparison          -- col = literal, col > literal 绛?is_null             -- IS NULL / IS NOT NULL
between             -- BETWEEN / NOT BETWEEN
like                -- LIKE / NOT LIKE
regexp              -- REGEXP / RLIKE / NOT REGEXP
exists_subquery     -- EXISTS (SELECT ...)
not_exists_subquery -- NOT EXISTS (SELECT ...)
in_subquery         -- IN (SELECT ...)
not_in_subquery     -- NOT IN (SELECT ...)
any_all_subquery    -- = ANY, > ALL 绛?column_comparison   -- JOIN ON 涓乏鍙?relation 鐨勫吋瀹瑰垪姣旇緝
```

绀轰緥杈撳嚭锛?
```sql
WHERE (
  t1.c1 BETWEEN 10 AND 50
  AND t1.c2 NOT IN (SELECT t2.c2 FROM t2 AS t2)
)
```

## 瀹氫箟閫昏緫 op 鐨勫乏鍙崇被鍨?
鍙互鐢?`connector_operands` 鎺у埗 `AND / OR / NOT` 鐨勬搷浣滄暟绫诲瀷銆?
榛樿鍐欐硶锛?
```yaml
bool_expr:
  connector_operands:
    and:
      left:
        kind: bool_expr
      right:
        kind: bool_expr
    or:
      left:
        kind: bool_expr
      right:
        kind: bool_expr
    not:
      operand:
        kind: bool_expr
```

鏀寔鐨?operand kind锛?
```text
bool_expr
atom
literal
true
false
```

鐢熸垚 `random_bool_expr AND TRUE`锛?
```yaml
bool_expr:
  atom_prob: 0.0
  connectors:
    and: 1.0
  connector_operands:
    and:
      left:
        kind: bool_expr
      right:
        kind: literal
        value: true
```

濡傛灉鍙兂鍖呬竴灞傦紝宸﹁竟浣跨敤 `atom`锛?
```yaml
bool_expr:
  atom_prob: 0.0
  connectors:
    and: 1.0
  connector_operands:
    and:
      left:
        kind: atom
      right:
        kind: literal
        value: true
```

绀轰緥杈撳嚭锛?
```sql
WHERE ((t1.c1 > 10) AND TRUE)
```

## HAVING 閰嶇疆

HAVING 浣跨敤鐙珛 profile锛?
```yaml
having_bool:
  max_depth: 2
  atom_prob: 0.65
  atoms:
    aggregate_comparison: 0.75
    group_expression_comparison: 0.25
```

HAVING 涓嶇洿鎺ヤ粠鏅€氬垪闅忔満鍙栧垪锛岃€屾槸浼樺厛浣跨敤锛?
```text
SELECT 涓殑鑱氬悎琛ㄨ揪寮?alias
GROUP BY 琛ㄨ揪寮忓搴旂殑 SELECT alias
```

绀轰緥锛?
```sql
SELECT SUM(t1.c1) AS col_1, t1.c2 AS col_2
FROM t1 AS t1
GROUP BY t1.c2
HAVING col_1 > 10
```

## GROUP BY 澶勭悊

`GROUP BY` 涓嶇敱鐢ㄦ埛鍗曠嫭瀹氫箟銆?
鍙 SELECT 涓嚭鐜拌仛鍚堝嚱鏁帮紝鐢熸垚鍣ㄤ細鑷姩鎶婇潪鑱氬悎琛ㄨ揪寮忓姞鍏?`GROUP BY`锛屼互鍏煎 MySQL `ONLY_FULL_GROUP_BY`銆?
褰撹仛鍚堝嚱鏁板拰绐楀彛鍑芥暟鍚屾椂鍑虹幇鏃讹紝鐢熸垚鍣ㄤ笉浼氭妸绐楀彛鍑芥暟鏈韩鏀捐繘 `GROUP BY`锛岃€屾槸鎶婄獥鍙ｅ嚱鏁颁緷璧栧垪鍔犲叆 `GROUP BY`锛?
```text
绐楀彛鍑芥暟鍙傛暟鍒?PARTITION BY 鍒?绐楀彛 ORDER BY 鍒?```

## 瀛愭煡璇㈤厤缃?
```yaml
subquery:
  max_depth: 2
  correlated_prob: 0.0
  in_subquery:
    where:
      enabled_prob: 0.6
      max_depth: 1
  scalar_subquery:
    where:
      enabled_prob: 0.6
      max_depth: 1
    order_by:
      enabled_prob: 0.5
```

褰撳墠鏀寔锛?
```text
IN subquery
NOT IN subquery
ANY / ALL subquery
EXISTS / NOT EXISTS subquery
scalar subquery 浣滀负 SELECT 鍒?derived table
JOIN derived table
```

`IN subquery` 鍜?`scalar subquery` 鍐呴儴鍙互闅忔満鐢熸垚 FROM/JOIN锛屽苟鎸夐厤缃敓鎴?WHERE銆?
`scalar subquery` 浼氬己鍒跺甫 `LIMIT 1`锛屼繚璇佹爣閲忚涔夈€?
褰撳墠 `correlated_prob` 浠嶄负 0锛岀浉鍏冲瓙鏌ヨ灏氭湭瀹屾暣寮€鏀俱€?
## CTE 閰嶇疆

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

CTE 鏄鐜囧嚭鐜帮紝涓嶆槸榛樿蹇呭嚭銆?
CTE 鐢熸垚鍚庝細杞崲鎴愯櫄鎷熻〃锛?
```sql
WITH cte_1 AS (
  SELECT expr AS col_1, expr AS col_2
)
SELECT ...
FROM cte_1 AS t1
```

鍙湁褰?FROM/JOIN 閫夋嫨鍒?CTE 鏃讹紝CTE 杈撳嚭鍒楁墠杩涘叆褰撳墠 scope 鍙鍒楅泦鍚堛€?
## 绐楀彛鍑芥暟閰嶇疆

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

绐楀彛鍑芥暟鐨?`ORDER BY` 浼氫粠褰撳墠 scope 鍙涓斿彲鎺掑簭鐨勫垪涓殢鏈洪€夋嫨锛屼笉浣跨敤 SELECT alias銆?
绀轰緥锛?
```sql
ROW_NUMBER() OVER (PARTITION BY t1.c2 ORDER BY t1.c1 DESC)
```

## 绠楁湳琛ㄨ揪寮忛厤缃?
```yaml
arithmetic:
  operators: ["+", "-", "*", "/", "%"]
```

绠楁湳琛ㄨ揪寮忓彧浣跨敤 numeric 绫诲瀷鍒楁垨鏁板瓧 literal銆?
闄ゆ硶鍜屽彇妯′細鑷姩闃查櫎闆讹細

```sql
(t1.c1 / NULLIF(t1.c2, 0))
(t1.c1 % NULLIF(10, 0))
```

## 闆嗗悎鎿嶄綔

榛樿鏀寔锛?
```yaml
set_operation:
  operation_types: ["UNION", "UNION ALL", "EXCEPT", "INTERSECT"]
  query_count: [2, 2]
  projection_count: [1, 3]
  categories: ["numeric", "string", "datetime"]
```

濡傛灉瑕佷互闆嗗悎鎿嶄綔涓烘牴锛?
```yaml
query:
  root: set_operation
```

褰撳墠鎸夌敤鎴疯姹備笉鍋氭柟瑷€杩囨护锛屽洓绫婚泦鍚堟搷浣滈兘鍏佽閰嶇疆銆?
## 琛ㄥ垪渚濊禆澶勭悊

鐢熸垚鍣ㄥ唴閮ㄤ娇鐢ㄤ袱涓疮绌垮叏绋嬬殑澶勭悊鍣細

```text
ScopeResolver
ColumnDependencyResolver
```

`ScopeResolver` 缁存姢褰撳墠 SELECT scope 涓彲瑙佺殑琛ㄣ€佸埆鍚嶃€丆TE銆乨erived table 杈撳嚭鍒椼€?
`ColumnDependencyResolver` 鍦ㄨ〃杈惧紡鐢熸垚鏃跺彧浠庡綋鍓嶅彲瑙佸垪涓€夊垪锛屽苟鏍规嵁 category 杩囨护锛?
```text
numeric
string
datetime
boolean
```

鍥犳鏅€氳〃銆丣OIN 琛ㄣ€丆TE銆乨erived table銆乻ubquery 杈撳嚭鍒楅兘浼氳缁熶竴澶勭悊鎴愬彲瑙佸垪銆?
## 楠岃瘉寤鸿

姣忔淇敼 YAML 鍚庯紝寤鸿鑷冲皯璺戯細

```powershell
python scripts\generate_configurable_sql_batch.py --count 100 --output-dir generated_sql --database test --dialect mysql --host 127.0.0.1 --port 13306 --user root --password 123456
```

鍏虫敞杈撳嚭锛?
```text
generated=100
query_execution=completed, total=103, passed=103, failed=0, accuracy=100.00%
```

`schema_execution=completed_with_errors` 褰撳墠鍙兘浠嶅嚭鐜板皯閲忛潪闃诲 schema/index 閿欒锛岄噸鐐圭湅 `query_execution`銆?
