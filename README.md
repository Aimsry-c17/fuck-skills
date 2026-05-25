# Dynamic Skill Router

一个把复杂请求自动拆分、选 skill、临时安装、执行再清理的动态技能路由器。

`dynamic-skill-router` 不是一个面向单一领域的 skill，
而是一个专门给 Agent / Codex 使用的 **skill 编排器**：
它会把一个复杂请求拆成多个能力片段，为每个片段从 `skills.sh` 里挑选最合适的社区 skill，按需安装，能复用就复用，最后再安全清理。

## 这个 skill 解决了什么问题

真实世界里的请求，往往不是“一个任务，一个 skill”。

比如用户可能会这样说：

- 先帮我 review 一下 PR
- 再补测试
- 再写 changelog
- 最后给我一份部署建议

如果长期预装大量 skill，会带来几个问题：

- 环境臃肿
- skill 太多，不知道该用哪个
- 不同任务之间上下文污染
- 清理困难

`dynamic-skill-router` 的目标，就是把 skill 的使用方式变成：

- **按需选择**
- **按 part 路由**
- **临时安装**
- **任务结束后清理**

## 核心能力

### 1. 多阶段任务拆分
它会把一个用户请求拆成有顺序的 part，而不是粗暴地让一个 skill 处理所有事情。

适合的能力类别包括：

- review
- testing
- deployment
- documentation
- refactor
- analysis
- migration
- integration

### 2. 相关性优先的 skill 选择
候选 skill 的排序规则不是“谁最火谁上”，而是：

```text
(relevance_score, installs_value)
```

也就是：

- 先看相关性
- 再看安装量

这意味着它选的是“最热门的相关 skill”，而不是“全站最热门 skill”。

### 3. 自动复用 skill
如果前面已经选中的某个 skill，仍然能够很好覆盖后面的 part，路由器会直接复用，而不是重复安装新的 skill。

这样可以减少：

- 安装次数
- skill 切换成本
- 临时 skill 数量

### 4. 先预览，再执行
在安装任何 skill 之前，你可以先执行 `batch-select --dry-run` 预览计划。

预览里会告诉你：

- 每个 part 选中了哪个 skill
- 哪些 skill 会新安装
- 哪些 skill 已经存在
- 哪些 part 会 fallback
- 哪些 part 会复用已有 skill

### 5. 更安全的安装与清理
这个项目已经做了安全收敛：

- `remove` 优先使用完整 package 引用
- 同名 skill 歧义场景会拒绝执行，而不是盲删
- 清理依赖官方 `skills remove`
- 不再手动删除本地 skill 目录

### 6. 双输出模式
- 默认输出：适合人类阅读的 CLI 文本格式
- `--json`：适合自动化调用、Agent 集成、二次编排

## 典型使用场景

这个 skill 特别适合下面这类请求：

- 一个需求跨多个专业阶段
- 你不想永久安装大量社区 skill
- 你希望让 skill 使用过程更透明、更可控
- 你希望先预览计划，再决定是否安装
- 你希望任务结束后安全回收临时 skill

## 快速开始

### 1. 检查环境

```bash
python3 scripts/skills_router.py check
```

如果你需要结构化输出：

```bash
python3 scripts/skills_router.py check --json
```

### 2. 预览一个多阶段计划

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

### 3. 安装一个选中的 skill

```bash
python3 scripts/skills_router.py install "warpdotdev/common-skills@review-pr"
```

### 4. 使用完成后清理

```bash
python3 scripts/skills_router.py remove "warpdotdev/common-skills@review-pr"
```

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

### 为单个 part 选 skill

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

### 安装 / 删除 / 查看已安装 skill

```bash
python3 scripts/skills_router.py install "owner/repo@skill-name"
python3 scripts/skills_router.py remove "owner/repo@skill-name"
python3 scripts/skills_router.py list
```

## 输出说明

### 文本模式
默认输出为适合人类阅读的文本格式，适合直接在命令行里看结果。

### JSON 模式
如果你要把这个 router 集成到其它 agent、workflow 或脚本中，请使用 `--json`。

重要字段包括：

- `selected`
- `candidates`
- `all_candidates`
- `score_breakdown`
- `summary.packages_to_install`
- `summary.already_installed_packages`
- `reused`
- `reused_from_package`

## 安全设计

这个项目目前已经做了几项关键安全收敛：

- 优先使用最小相关 skill，而不是盲目安装多个 skill
- `remove` 支持 package 精确定位
- 同名 skill 冲突时直接报错，不做猜测删除
- 清理动作完全依赖 `skills remove`
- 输入 part 会先做结构校验
- 没有强候选时允许 fallback，不强装 skill

## 当前已完成的真实验证

这个 skill 已经做过真实链路验证：

- `batch-select --dry-run` 能真实从 `skills.sh` 选出 skill
- 真实执行过 `install`
- 能读取已安装 skill 的 `SKILL.md`
- 真实执行过 `remove`
- remove 后已通过 `list` 确认 skill 已消失

此外还补了：

- 单元测试
- 输入校验测试
- summary 预览测试
- install / remove / check 分支测试
- 文本输出格式测试

## 项目结构

```text
SKILL.md                      skill 工作流定义
agents/openai.yaml            agent 元数据
references/v2-design.md       设计说明
scripts/skills_router.py      路由器实现
scripts/test_skills_router.py 测试
```

## 它适合谁

如果你在做下面这些事情，这个项目会非常适合你：

- 做一个基于 Codex 的 skill 生态
- 做一个支持临时借用 skill 的 Agent
- 做 review / test / docs / deploy 的任务编排层
- 不想永久装很多 skill，但又想在复杂任务中灵活调用它们

## 这个项目的定位

这不是一个“领域 skill”。

它更像一个：

> skill orchestration skill

也就是：

> 帮 Agent 判断：一个复杂请求该拆成哪些 part、每个 part 应该借哪个 skill、什么时候复用、什么时候清理。

## 后续可继续增强的方向

虽然现在已经可以稳定使用，但后面仍然可以继续进化：

- 把大脚本拆成模块
- 增加更多集成测试和 E2E 测试
- 优化长尾 skill 名称的相关性判断
- 更好地处理近似候选之间的歧义选择

## License

可按你的需要补充许可证信息。
