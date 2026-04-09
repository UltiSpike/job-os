# v3 评分模型：技能联动与簇匹配

## v2 的三个问题

1. **P0 = 0**：因为要求"技能分≥45 + 初级 + 标题同时 Go+K8s/GPU"这种强联立，太严格
2. **技能独立权重**：Go+K8s 组合的价值 > Go 和 K8s 分别加分
3. **同义词重复**：`Go`/`Golang`/`go-zero` 被当作三个独立技能

---

## 核心思路：技能簇（Skill Clusters）

岗位不是按"单个技能"招人的，而是按"技术栈组合"招人的。评分应该识别这些**组合模式**。

### 定义 5 个核心簇

每个簇代表一种"岗位类型"，命中簇 = 强信号。

```python
CLUSTERS = {
  # 簇1：Go 后端基础（通用 Go 后端）
  "go_backend": {
    "required": [{"Go", "Golang", "go-zero"}],  # 必须命中组 1
    "optional": [{"Redis", "MySQL", "PostgreSQL", "Kafka"},
                 {"gRPC", "protobuf", "微服务"}],
    "bonus": 15,
    "tier_signal": "基础",
  },

  # 簇2：K8s / 云原生开发（核心平台方向）
  "k8s_cloud_native": {
    "required": [{"Kubernetes", "K8s", "K8S"}],
    "optional": [{"Operator", "CRD", "Controller", "Helm"},
                 {"云原生", "Cloud Native"},
                 {"Docker", "容器"}],
    "bonus": 18,
    "tier_signal": "平台",
  },

  # 簇3：Go + K8s 平台（用户背景 80% 对口）
  "go_k8s_platform": {
    "required": [{"Go", "Golang"}, {"Kubernetes", "K8s", "K8S"}],
    "optional": [{"Operator", "CRD", "Controller"},
                 {"云原生"},
                 {"微服务", "gRPC"}],
    "bonus": 25,       # 大奖励
    "tier_signal": "核心",
  },

  # 簇4：GPU / 算力平台
  "gpu_platform": {
    "required": [{"GPU", "算力"}],
    "optional": [{"调度", "Kubernetes", "K8s"},
                 {"AI", "模型", "训练", "推理"},
                 {"CUDA", "NVIDIA"}],
    "bonus": 22,
    "tier_signal": "差异化",
  },

  # 簇5：AI Infra 工程（用户背景 95% 对口 - 最高)
  "ai_infra": {
    "required": [{"AI Infra", "AI基础设施"}],
    "optional": [{"GPU", "算力"},
                 {"Kubernetes", "K8s"},
                 {"Go", "Golang"},
                 {"调度", "训练", "推理"}],
    "bonus": 30,       # 最高奖励
    "tier_signal": "完美",
  },
}
```

### 簇评分规则

```python
def calc_cluster_score(text):
    total = 0
    hit_clusters = []
    for cluster_name, config in CLUSTERS.items():
        # 所有 required 组必须都命中至少一个
        all_required_met = True
        for req_group in config["required"]:
            if not any(skill.lower() in text.lower() for skill in req_group):
                all_required_met = False
                break
        if not all_required_met:
            continue

        # 命中了必选，看可选命中几个
        opt_hits = 0
        for opt_group in config["optional"]:
            if any(skill.lower() in text.lower() for skill in opt_group):
                opt_hits += 1

        # 基础 bonus + 每个 optional 组额外 3 分
        cluster_score = config["bonus"] + opt_hits * 3
        total += cluster_score
        hit_clusters.append(f"{cluster_name}({cluster_score})")

    return total, hit_clusters
```

### 最高分模拟

一个完美匹配的岗位（"AI Infra Go K8s GPU 调度工程师"）：
- `ai_infra`: 30 + 4×3 = 42
- `go_k8s_platform`: 25 + 3×3 = 34
- `gpu_platform`: 22 + 3×3 = 31
- `go_backend`: 15 + 2×3 = 21
- `k8s_cloud_native`: 18 + 3×3 = 27
- **总 cluster bonus: 155** (但会 cap 在 60)

---

## 其他改进

### 1. 同义词归一化

在评分前统一化处理：

```python
SYNONYMS = {
    "golang": "go", "go-zero": "go",
    "k8s": "kubernetes", "k8s": "kubernetes",
    "cloud native": "云原生",
    "ai基础设施": "ai infra",
}

def normalize(text):
    lower = text.lower()
    for k, v in SYNONYMS.items():
        lower = lower.replace(k, v)
    return lower
```

### 2. 标题权重 > JD 权重

标题写什么比 JD 提什么更说明岗位性质：

```python
score =
    0.6 * cluster_score(title_text) +    # 标题权重 60%
    0.4 * cluster_score(jd_text)         # JD 权重 40%
```

### 3. 负面信号（语义冲突）

```python
NEGATIVE_SIGNALS = {
    # 语言冲突
    ("python", -5): lambda t: "python" in t and "go" not in t and "golang" not in t,
    # 岗位类型冲突
    ("纯运维", -15): lambda t: "运维" in t and "开发" not in t,
    ("前端相关", -20): lambda t: any(k in t for k in ["前端", "vue", "react"]),
    # 外包
    ("外包驻场", -25): lambda t: any(k in t for k in ["外包", "驻场", "派遣"]),
}
```

### 4. 公司 × 岗位匹配

某些公司 + 某些技能 = 强信号：

```python
COMPANY_CONTEXT = {
    # AI infra 强对口公司
    ("智谱", "MiniMax", "月之暗面", "阶跃", "DeepSeek", "硅基流动"): +10,
    # 云厂商
    ("阿里云", "火山引擎", "腾讯云", "华为云", "UCloud", "百度云"): +8,
    # 大厂
    ("字节", "腾讯", "阿里", "美团", "百度", "京东", "滴滴", "拼多多",
     "小米", "快手", "网易", "B站"): +12,
}
```

### 5. P0/P1/P2 分层规则重写

```python
def classify_tier(job):
    score = job["final_score"]
    clusters = job["hit_clusters"]
    is_junior = job["exp_years_min"] <= 1

    # P0 = 命中核心簇 + 初级友好
    # 核心簇 = ai_infra / go_k8s_platform / gpu_platform 任一
    has_core_cluster = any(
        c in str(clusters) for c in ["ai_infra", "go_k8s_platform", "gpu_platform"]
    )

    if has_core_cluster and is_junior:
        return "P0"  # 完美匹配且初级友好

    if has_core_cluster:
        return "P1"  # 完美匹配但经验要求稍高

    if score >= 50 and is_junior:
        return "P1"  # 分数高且初级友好

    if score >= 40:
        return "P2"

    if score >= 20:
        return "P3"

    return "P3"
```

---

## v2 → v3 效果对比预期

| 指标 | v2 | v3 |
|------|----|----|
| 评分维度 | 独立技能加分 | 簇匹配 + 标题权重 + 公司×技能 |
| P0 数量 | 0 | 5-15（预期） |
| P1 数量 | 13 | 25-40 |
| 区分度 | 小（前 10 都是 40-50 分） | 大（顶级岗 80+，一般岗 30-） |
| 召回策略 | 10 关键词 × 2 经验段 × 5 页 | **保持不变**（只改评分） |

**输出到 `v3_output/`** 便于与 v2 A/B 对比。
