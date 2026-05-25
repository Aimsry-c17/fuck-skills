# fuck-skills

一个专门用来狠狠干碎“技能太多、任务太杂、路由太乱”问题的动态 Skill Router。

如果你已经受够了这些场景：

- 一个需求要 review、要测试、要文档、要部署，结果不知道该上哪个 skill
- skill 装了一堆，真正要用的时候反而更乱
- Agent 看起来很聪明，实际一到复杂任务就开始乱选 skill、乱装 skill、乱清理 skill
- 临时装 skill 容易，清理干净很难

那这个项目就是冲着这些痛点来的。

`fuck-skills` 不是普通的 skill。
它是一个 **专门调度 skill 的 skill**。

它做的事情非常直接：

> 把复杂请求拆开，给每一段任务找最合适的 skill，只装该装的，只用该用的，用完就收，绝不让 skill 生态继续失控。

---

## 这玩意儿到底是什么

`fuck-skills` 是一个面向 Codex / Agent 工作流的动态技能路由器。

它会：

- 把一个复杂请求拆成多个有顺序的能力 part
- 判断哪些 part 值得用外部 skill
- 去 `skills.sh` 搜索候选 skill
- 按 **相关性优先、热度次之** 的规则选 skill
- 如果前面已经选过的 skill 还能覆盖后面的 part，就直接复用
- 临时安装 skill
- 执行完之后安全移除

一句话：

> 它不是让你“多装几个 skill 试试看”，而是让 skill 真正变成一个可控、可编排、可回收的工具系统。

---

## 为什么这个项目很猛

因为它不是在修小毛病。
它直接解决的是 Agent skill 生态里最烦、最脏、最容易失控的那一层：

### 1. 复杂任务不该只靠一个 skill 硬顶
真实需求从来不是一句话就能处理干净的。

用户经常会说：

- 帮我 review 这个 PR
- 顺手把测试补了
- 再写 release notes
- 最后给我一份部署建议

普通 skill 面对这种任务，往往只有两种死法：

- 要么能力不够，处理一半就废了
- 要么太泛，什么都沾一点但什么都不够准

`fuck-skills` 的做法很狠：

> 不让一个 skill 硬吃所有任务，而是把任务拆开，让每个 part 去找最适合自己的 skill。

### 2. 它不信“最火的 skill”，它信“最对的 skill”
很多系统的问题是：

- 只按安装量排序
- 只看热度
- 只看模糊命中

结果选出来的 skill 看起来很火，实际上根本不对题。

`fuck-skills` 直接采用：

```text
(relevance_score, installs_value)
```

也就是：

- 先看相关性
- 再看安装量

这意味着它追求的是：

> 最热门的“相关” skill，而不是最热门的“垃圾泛 skill”。

### 3. 它不是疯狂安装，而是按需借用
这个项目最爽的一点就在这里：

- 不要求你常驻装几十个 skill
- 不鼓励你把环境变成技能垃圾场
- 不让每次任务都把上下文搞得满地都是

它的哲学非常简单粗暴：

> 要用的时候装，不用的时候删。

### 4. 它连“乱清理”这件事都狠狠干掉了
很多路由器项目最危险的地方不是“装错”，而是“删错”。

这个项目已经做了很关键的安全收敛：

- remove 优先按完整 package 精确定位
- 同名 skill 冲突时，直接拒绝删除，不瞎猜
- 清理只走 `skills remove`
- 不再自己手动删本地目录

所以它不是“装得猛”，而是：

> 该猛的时候猛，该稳的时候非常稳。

---

## 它到底能干什么

### 动态拆任务
把一个复杂请求拆成多个按顺序执行的 part。

支持的能力方向包括：

- review
- testing
- deployment
- documentation
- refactor
- analysis
- migration
- integration

### 动态找 skill
对每个 part 生成搜索 query，去 `skills.sh` 搜索候选 skill。

### 动态选 skill
自动评分、排序、过滤，选出最值得装的那个。

### 动态复用
如果一个 skill 还能打多个 part，就不重复安装。

### 动态清理
任务做完，安全 remove。

---

## 使用体验有多顺
### 先预览，不盲装
你可以先 dry-run，看看整个计划是不是靠谱。

```bash
python3 scripts/skills_router.py batch-select \
  --parts-json '[
    {"part_id":"p1","title":"Review PR","capability":"review","queries":["pr review"],"needs_skill":true},
    {"part_id":"p2","title":"Add tests","capability":"testing","queries":["unit testing"],"needs_skill":true},
    {"part_id":"p3","title":"Write changelog","capability":"documentation","queries":["release notes"],"needs_skill":true}
  ]' \
  --dry-run
```

示例输出：

```text
p1: Review PR -> warpdotdev/common-skills@review-pr [high:110]
p2: Add tests -> aj-geddes/useful-ai-prompts@unit-testing-framework [medium:75]
p3: Write changelog -> fallback
packages_to_install=warpdotdev/common-skills@review-pr, aj-geddes/useful-ai-prompts@unit-testing-framework
already_installed_packages=-
fallback_parts=p3
reused_parts=-
```

这个输出的意思很直接：

- 第一段任务该用哪个 skill
- 第二段任务该用哪个 skill
- 第三段如果没有强候选，就 fallback
- 哪些 skill 会被新装
- 哪些 skill 已经存在
- 哪些 part 会复用

### 需要就装

```bash
python3 scripts/skills_router.py install "warpdotdev/common-skills@review-pr"
```

### 用完就删

```bash
python3 scripts/skills_router.py remove "warpdotdev/common-skills@review-pr"
```

简洁、干净、没有废动作。

---

## 常用命令

### 环境检查

```bash
python3 scripts/skills_router.py check
python3 scripts/skills_router.py check --json
```

### 搜索 skill

```bash
python3 scripts/skills_router.py search "pr review"
python3 scripts/skills_router.py search-many --query "pr review" --query "code review"
```

### 单 part 选 skill

```bash
python3 scripts/skills_router.py select \
  --part-title "Review PR" \
  --capability review \
  --query "pr review"
```

### 批量预览路由计划

```bash
python3 scripts/skills_router.py batch-select \
  --parts-json '[{"part_id":"p1","title":"Review PR","capability":"review","queries":["pr review"],"needs_skill":true}]' \
  --dry-run
```

### 安装 / 删除 / 查看已安装

```bash
python3 scripts/skills_router.py install "owner/repo@skill-name"
python3 scripts/skills_router.py remove "owner/repo@skill-name"
python3 scripts/skills_router.py list
```

---

## 输出模式

### 文本模式
默认输出就是给人看的。

不带 `--json` 时，CLI 输出会尽量简洁、直接、可扫读。

### JSON 模式
如果你要把 `fuck-skills` 接到别的 Agent、workflow、脚本里，直接加 `--json`。

关键字段包括：

- `selected`
- `candidates`
- `all_candidates`
- `score_breakdown`
- `summary.packages_to_install`
- `summary.already_installed_packages`
- `reused`
- `reused_from_package`

---

## 安全设计：这项目不是瞎搞的

它现在已经做了这些关键保护：

- part 输入先校验，不让脏数据直接进主流程
- 同名 skill 冲突时拒绝 remove-by-name
- cleanup 不再手动删本地目录
- 没有强候选时允许 fallback
- 优先最小、最相关 skill，而不是瞎装一堆
- 支持 dry-run 预览，先看清楚再动手

换句话说：

> 它不是一个“看起来很会装 skill”的项目，
> 而是一个“真正在控制 skill 风险”的项目。

---

## 现在它已经验证到什么程度了

不是纸上谈兵。

这个项目已经真实跑过：

- `batch-select --dry-run` 真实从 `skills.sh` 选 skill
- 真实执行过 install
- 真实读取过已安装 skill 的 `SKILL.md`
- 真实执行过 remove
- remove 后已通过 `list` 验证 skill 确实消失

同时还补了：

- 单元测试
- part 输入校验测试
- summary 预览测试
- install / remove / check 分支测试
- 文本输出测试
- 真实链路中的识别 bug 修复

所以它现在不是一个“看起来挺有想法”的 demo，
而是一个已经能真正上手用的 skill。

---

## 项目结构

```text
SKILL.md                      skill 工作流定义
agents/openai.yaml            agent 元数据
references/v2-design.md       设计说明
scripts/skills_router.py      路由器实现
scripts/test_skills_router.py 测试
```

---

## 谁最该用它

如果你正在做这些事情，你会很需要它：

- 做一个基于 Codex 的 skill 生态
- 做一个支持临时借用 skill 的 Agent
- 做 review / testing / docs / deploy 的任务编排层
- 不想永久安装一大堆 skill，但又想在复杂任务里灵活调用它们

---

## 这个项目最准确的定位

它不是普通的业务 skill。

它更像是：

> 一个专门治理 skill 混乱、清理 skill 膨胀、把复杂任务重新编排干净的 skill orchestration engine。

更直白一点：

> 如果你的技能系统已经开始乱了，`fuck-skills` 就是来收拾场子的。

---

## 之后还能继续变得更狠

虽然现在已经能稳定使用，但往后还可以继续进化：

- 把大脚本拆成模块
- 增加更多集成测试和 E2E 测试
- 优化长尾 skill 名称的相关性判断
- 增强相近候选之间的歧义处理
- 让整个 skill router 更像一个真正的可插拔调度内核

---

## License

按你的需要补充许可证即可。
