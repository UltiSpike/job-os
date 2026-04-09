#!/usr/bin/python3
"""
v4.1 - 修复 v4 的三个 bug:
1. normalize() \b 边界在中文环境下失效，导致 k8s 不被识别为 kubernetes
2. 黑名单缺失：业务拓展、招商、拓展经理 等销售类岗位漏过
3. 分层规则太严，命中核心簇的好岗位被埋在 P2

复用 v4_output 的原始数据，重新评分输出到 v4_1_output/
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

INPUT_FILE = Path(__file__).parent / "v4_output" / "raw.json"
ENRICHED_FILES = [
    Path(__file__).parent / "v2_output" / "tiered.json",
    Path(__file__).parent / "v4_output" / "tiered.json",  # v4 已补全的 200 条
]
OUTPUT_DIR = Path(__file__).parent / "v4_1_output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# Bug Fix #1: 用前后断言代替 \b
# ═══════════════════════════════════════════════════════════════

# (?<![a-zA-Z0-9]) 表示前一个字符不是 ASCII 字母数字，中文也算"不是"
# (?![a-zA-Z0-9]) 同理
NB = r"(?<![a-zA-Z0-9])"
NA = r"(?![a-zA-Z0-9])"

SYNONYMS = [
    (NB + r"golang" + NA, "go"),
    (NB + r"go-zero" + NA, "go"),
    (NB + r"k8s" + NA, "kubernetes"),
    (NB + r"k8S" + NA, "kubernetes"),
    (r"cloud native", "云原生"),
    (r"ai基础设施", "ai infra"),
    (r"ai-infra", "ai infra"),
    (r"aiinfra", "ai infra"),
]


def normalize(text: str) -> str:
    lower = text.lower()
    for pat, repl in SYNONYMS:
        lower = re.sub(pat, repl, lower)
    return lower


def has_any(text: str, keywords) -> bool:
    return any(kw.lower() in text for kw in keywords)


def count_any(text: str, keywords) -> int:
    return sum(1 for kw in keywords if kw.lower() in text)


# ═══════════════════════════════════════════════════════════════
# 信号组（同 v3.1）
# ═══════════════════════════════════════════════════════════════

PLATFORM_SIGNALS = [
    "kubernetes", "容器", "operator", "crd", "controller", "helm",
    "云原生", "调度", "多集群", "服务治理", "微服务",
    "集群", "平台", "infra", "基础设施", "sre", "devops",
]

AI_DOMAIN_SIGNALS = [
    "ai infra", "机器学习", "深度学习", "大模型", "llm",
    "推理", "训练", "模型", "ml",
]

ML_FRAMEWORK_HEAVY = [
    "pytorch", "tensorflow", "deepspeed", "fsdp", "zero",
    "tensorrt", "onnx", "量化", "quantization", "int8", "fp8", "fp16",
    "megatron", "vllm", "sglang", "triton",
    "cuda kernel", "cuda 内核", "nccl", "算子开发", "kernel 优化",
    "flash attention", "kv cache", "mixed precision",
    "vla", "world model", "rlhf", "sft", "预训练",
    "数据并行", "模型并行", "tensor parallel", "pipeline parallel",
    "torchacc", "colossal",
]

ALGORITHM_SIGNALS = [
    "算法研究", "论文", "state-of-the-art", "sota",
    "transformer 优化", "attention 优化",
]

HARDWARE_SIGNALS = [
    "硬件设计", "芯片设计", "ip 验证", "rtl", "verilog", "fpga",
    "驱动开发", "kernel module", "嵌入式开发",
]


# ═══════════════════════════════════════════════════════════════
# 簇定义（同 v3.1）
# ═══════════════════════════════════════════════════════════════

CLUSTERS = {
    "platform_ai_infra": {
        "name": "平台型 AI Infra（完美对口）",
        "required": [
            {"ai infra", "算力", "gpu"},
            {"kubernetes", "容器", "云原生", "调度", "operator", "平台"},
        ],
        "optional": [
            {"go", "golang"},
            {"训练", "推理", "模型"},
            {"微服务", "grpc"},
        ],
        "bonus": 35,
    },
    "go_k8s_platform": {
        "name": "Go+K8s 平台（核心对口）",
        "required": [
            {"go", "golang"},
            {"kubernetes"},
        ],
        "optional": [
            {"operator", "crd", "controller"},
            {"云原生"},
            {"微服务", "grpc"},
            {"容器", "docker"},
        ],
        "bonus": 28,
    },
    "gpu_cloud_platform": {
        "name": "GPU 云平台",
        "required": [
            {"gpu", "算力"},
            {"kubernetes", "调度", "云原生", "容器", "平台"},
        ],
        "optional": [
            {"ai", "模型", "训练", "推理"},
            {"go", "golang"},
            {"多租户", "集群"},
        ],
        "bonus": 25,
    },
    "k8s_cloud_native": {
        "name": "K8s/云原生开发",
        "required": [
            {"kubernetes"},
        ],
        "optional": [
            {"operator", "crd", "controller", "helm"},
            {"云原生"},
            {"go", "golang"},
            {"容器", "docker"},
        ],
        "bonus": 18,
    },
    "go_backend": {
        "name": "Go 后端基础",
        "required": [
            {"go", "golang"},
        ],
        "optional": [
            {"redis", "mysql", "postgresql", "kafka"},
            {"grpc", "protobuf", "微服务"},
            {"docker", "容器"},
        ],
        "bonus": 12,
    },
}


def calc_cluster_score(text: str):
    total = 0
    hits = []
    for cname, cfg in CLUSTERS.items():
        all_required = True
        for req in cfg["required"]:
            if not has_any(text, req):
                all_required = False
                break
        if not all_required:
            continue

        opt_hits = 0
        for opt in cfg["optional"]:
            if has_any(text, opt):
                opt_hits += 1

        cs = cfg["bonus"] + opt_hits * 3
        total += cs
        hits.append({"name": cname, "display": cfg["name"], "score": cs, "opt_hits": opt_hits})
    return total, hits


# ═══════════════════════════════════════════════════════════════
# Bug Fix #2: 扩展黑名单
# ═══════════════════════════════════════════════════════════════

TITLE_BLACKLIST = [
    # 销售/BD/招商
    "销售", "商务", "BD ", "渠道", "市场", "运营",
    "招商", "业务拓展", "拓展经理", "客户经理",
    "解决方案经理",  # 注意：架构师不在内
    # 产品
    "产品经理", "PM", "策划",
    # 前端/客户端
    "前端", "iOS", "Android", "flutter", "U3D", "客户端", "Vue", "React",
    # 测试
    "测试", "QA", "自动化测试", "测开",
    # 实习
    "实习生", "见习",
    # 算法/研究
    "算法研究", "研究员", "博士后",
    # DBA
    "DBA",
    # 高管
    "总监", "VP", "CTO", "首席", "总经理",
    # 教学
    "老师", "讲师", "教练",
]


def calc_negative_signals(text: str, title: str, cluster_hits):
    penalty = 0
    reasons = []

    if any(kw in text for kw in ["外包", "驻场", "派遣"]):
        penalty -= 30
        reasons.append("外包/驻场")

    if any(kw in title for kw in ["前端", "客户端", "vue", "react", "ios", "android", "u3d"]):
        penalty -= 40
        reasons.append("前端/客户端")

    if any(kw in title for kw in ["测试", "qa", "测开"]):
        penalty -= 40
        reasons.append("测试岗")

    if any(kw in title for kw in ["总监", "vp", "cto", "首席"]):
        penalty -= 40
        reasons.append("高管岗")

    # 销售类（标题或 JD 含强销售特征）
    sales_kw = ["销售", "招商", "业务拓展", "拓展经理", "客户经理", "渠道经理", "商务经理"]
    if any(kw in title for kw in sales_kw):
        penalty -= 50
        reasons.append("销售类")

    if "运维" in title and not any(kw in title for kw in ["开发", "研发", "平台"]):
        penalty -= 30
        reasons.append("纯运维")

    ml_hits = count_any(text, ML_FRAMEWORK_HEAVY)
    if ml_hits >= 3:
        penalty -= 25
        reasons.append(f"ML框架深度({ml_hits})")
    elif ml_hits >= 2:
        penalty -= 10
        reasons.append(f"偏ML框架({ml_hits})")

    algo_hits = count_any(text, ALGORITHM_SIGNALS)
    if algo_hits >= 2:
        penalty -= 15
        reasons.append(f"偏算法研究({algo_hits})")

    hw_hits = count_any(text, HARDWARE_SIGNALS)
    if hw_hits >= 2:
        penalty -= 25
        reasons.append(f"硬件驱动({hw_hits})")

    ai_hits = count_any(text, AI_DOMAIN_SIGNALS)
    platform_hits = count_any(text, PLATFORM_SIGNALS)
    if ai_hits >= 2 and platform_hits == 0:
        penalty -= 20
        reasons.append("有AI无平台信号")

    if any(kw in text for kw in ["对日", "赴日", "驻日"]):
        penalty -= 10
        reasons.append("日本方向")

    return max(penalty, -80), reasons


# ═══════════════════════════════════════════════════════════════
# 经验解析
# ═══════════════════════════════════════════════════════════════

def parse_exp_years(text: str):
    if not text:
        return (None, None)
    e = text.lower()
    if "应届" in e or "在校" in e:
        return (0, 0)
    if "经验不限" in e or "不限经验" in e:
        return (0, 10)
    if "1年以内" in e or "1年以下" in e:
        return (0, 1)
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*年", e)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d+)\s*年以上", e)
    if m:
        y = int(m.group(1))
        return (y, y + 5)
    m = re.search(r"(\d+)\s*年", e)
    if m:
        y = int(m.group(1))
        return (y, y)
    return (None, None)


def calc_exp_bonus(exp_text: str):
    lo, hi = parse_exp_years(exp_text)
    if lo is None:
        return 0
    if lo == 0:
        return 10
    if lo <= 1:
        return 10
    if lo <= 3:
        return 5
    if lo <= 5:
        return -5
    return -20


BIG_TECH = ["字节", "字节跳动", "tiktok", "腾讯", "阿里", "阿里云", "美团",
            "百度", "京东", "滴滴", "拼多多", "小米", "华为", "网易", "快手", "b站"]
AI_UNICORN = ["智谱", "月之暗面", "kimi", "minimax", "阶跃", "deepseek", "深度求索",
              "硅基流动", "无问芯穹", "零一万物", "面壁", "moonshot"]
CLOUD_VENDORS = ["火山引擎", "腾讯云", "华为云", "ucloud", "优刻得", "百度云", "天翼云", "daocloud"]


def calc_company_bonus(company: str):
    if not company:
        return 0, ""
    cl = company.lower()
    for c in AI_UNICORN:
        if c in cl or c in company:
            return 15, f"AI独角兽: {company}"
    for c in BIG_TECH:
        if c in cl or c in company:
            return 12, f"大厂: {company}"
    for c in CLOUD_VENDORS:
        if c in cl or c in company:
            return 10, f"云厂商: {company}"
    return 0, ""


def score_job(job: dict) -> dict:
    title = job.get("title", "")
    jd = job.get("jd", "") or job.get("text", "")
    company = job.get("company", "")
    exp = job.get("experience", "") or job.get("exp", "")

    title_norm = normalize(title)
    full_norm = normalize(title + " " + jd)

    t_cs, t_hits = calc_cluster_score(title_norm)
    j_cs, j_hits = calc_cluster_score(full_norm)
    cluster_total = t_cs * 0.6 + j_cs * 0.4

    exp_bonus = calc_exp_bonus(exp)
    company_bonus, c_reason = calc_company_bonus(company)
    neg_penalty, neg_reasons = calc_negative_signals(full_norm, title_norm, j_hits)

    final = cluster_total + exp_bonus + company_bonus + neg_penalty
    final = max(0, final)

    return {
        "final_score": round(final, 1),
        "cluster_score": round(cluster_total, 1),
        "cluster_hits": j_hits,
        "title_cluster_score": round(t_cs, 1),
        "exp_bonus": exp_bonus,
        "company_bonus": company_bonus,
        "company_reason": c_reason,
        "negative_penalty": neg_penalty,
        "negative_reasons": neg_reasons,
    }


# ═══════════════════════════════════════════════════════════════
# Bug Fix #3: 分层规则放宽——核心簇命中直接进 P0/P1
# ═══════════════════════════════════════════════════════════════

def classify_tier(job):
    score = job.get("final_score", 0)
    lo, hi = parse_exp_years(job.get("experience", ""))
    is_junior = lo is None or lo <= 1
    is_acceptable = lo is None or lo <= 3

    hits = job.get("cluster_hits", [])
    names = {h["name"] for h in hits}
    has_platform_ai = "platform_ai_infra" in names
    has_go_k8s = "go_k8s_platform" in names
    has_gpu_cloud = "gpu_cloud_platform" in names
    has_k8s = "k8s_cloud_native" in names
    has_perfect = has_platform_ai or has_go_k8s or has_gpu_cloud

    neg = job.get("negative_penalty", 0)

    # 严重负面 → 直接 P3
    if neg <= -40:
        return "P3"

    # P0: 完美簇命中 + 初级友好
    if has_perfect and is_junior and neg > -20:
        return "P0"
    # P0: 完美簇命中 + 经验可接受 + 高分
    if has_perfect and is_acceptable and score >= 50 and neg > -25:
        return "P0"
    # P0: 极高分
    if score >= 70 and is_acceptable:
        return "P0"

    # P1: 完美簇命中（即使经验稍高）
    if has_perfect and neg > -25:
        return "P1"
    # P1: K8s 云原生开发 + 初级友好
    if has_k8s and is_junior and neg > -25:
        return "P1"
    # P1: 高分初级
    if score >= 40 and is_junior:
        return "P1"

    # P2: 至少命中一个核心簇
    if (has_perfect or has_k8s) and neg > -30:
        return "P2"
    if score >= 30:
        return "P2"

    # P3
    if score >= 10:
        return "P3"
    return "P3"


# ═══════════════════════════════════════════════════════════════
# 硬拒绝
# ═══════════════════════════════════════════════════════════════

def check_reject(job):
    title = job.get("title", "")
    if not title:
        return "empty_title"
    tl = title.lower()
    for bl in TITLE_BLACKLIST:
        if bl.lower() in tl:
            return f"title_blacklist: {bl}"
    lo, hi = parse_exp_years(job.get("experience") or job.get("exp", ""))
    if lo is not None and lo >= 5:
        return f"exp_too_high: {lo}+年"
    return None


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  v4.1 评分 - 修复 normalize / 黑名单 / 分层规则")
    print(f"  输出: {OUTPUT_DIR}")
    print("=" * 60)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_jobs = json.load(f)
    print(f"\n  原始: {len(raw_jobs)}")

    # 合并所有已补全详情
    enriched_map = {}
    for ef in ENRICHED_FILES:
        if not ef.exists():
            continue
        with open(ef, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for tj in d.values():
                for j in tj:
                    href = j.get("href", "")
                    if href and j.get("jd"):
                        enriched_map[href] = j
        else:
            for j in d:
                href = j.get("href", "")
                if href and j.get("jd"):
                    enriched_map[href] = j
    print(f"  已补全详情: {len(enriched_map)}")

    # 去重 + 合并
    seen = set()
    jobs = []
    for j in raw_jobs:
        key = (j.get("company", "") + "|" + j.get("title", "")).lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        href = j.get("href", "")
        if href in enriched_map:
            e = enriched_map[href]
            for k in ["jd", "company", "salary", "area", "experience", "tags", "company_info"]:
                if e.get(k):
                    j[k] = e[k]
        jobs.append(j)
    print(f"  去重后: {len(jobs)}")

    accepted = []
    rejected = []
    for j in jobs:
        r = check_reject(j)
        if r:
            j["reject_reason"] = r
            rejected.append(j)
        else:
            accepted.append(j)
    print(f"  硬过滤后: {len(accepted)}（拒绝 {len(rejected)}）")

    for j in accepted:
        j.update(score_job(j))

    for j in accepted:
        j["tier"] = classify_tier(j)

    accepted.sort(key=lambda x: (
        {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(x["tier"], 4),
        -x["final_score"]
    ))

    tiers = {"P0": [], "P1": [], "P2": [], "P3": []}
    for j in accepted:
        tiers[j["tier"]].append(j)

    print(f"\n  P0: {len(tiers['P0'])}  P1: {len(tiers['P1'])}  P2: {len(tiers['P2'])}  P3: {len(tiers['P3'])}")

    with open(OUTPUT_DIR / "tiered.json", "w", encoding="utf-8") as f:
        json.dump(tiers, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "rejected.json", "w", encoding="utf-8") as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)

    export_excel(tiers, rejected)

    for t_name in ["P0", "P1"]:
        tj = tiers.get(t_name, [])
        if tj:
            print(f"\n  [{t_name} Top 15]")
            for i, j in enumerate(tj[:15]):
                print(f"    {i+1:2d}. [{j['final_score']:5.1f}] {j['title']}")
                info = []
                if j.get("company"): info.append(j["company"])
                if j.get("experience"): info.append(j["experience"])
                if info: print(f"        {' | '.join(info)}")
                if j.get("cluster_hits"):
                    print(f"        簇: {' + '.join(h['display'] for h in j['cluster_hits'])}")


def export_excel(tiers, rejected):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    hf = Font(bold=True, color="FFFFFF", size=11)
    hfill = PatternFill(start_color="00B38A", end_color="00B38A", fill_type="solid")
    wrap = Alignment(wrap_text=True, vertical="top")
    border = Border(left=Side(style="thin", color="DDDDDD"),
                    right=Side(style="thin", color="DDDDDD"),
                    top=Side(style="thin", color="DDDDDD"),
                    bottom=Side(style="thin", color="DDDDDD"))

    main_cols = [
        ("分数", 7, lambda j: j.get("final_score", 0)),
        ("职位", 35, lambda j: j.get("title", "")),
        ("公司", 22, lambda j: j.get("company", "")),
        ("薪资", 12, lambda j: j.get("salary", "")),
        ("城市", 14, lambda j: j.get("area", "")),
        ("经验", 12, lambda j: j.get("experience", "")),
        ("命中簇", 30, lambda j: " + ".join(h["display"] for h in j.get("cluster_hits", []))),
        ("簇分", 8, lambda j: j.get("cluster_score", 0)),
        ("标题簇", 8, lambda j: j.get("title_cluster_score", 0)),
        ("经验加", 7, lambda j: j.get("exp_bonus", 0)),
        ("公司加", 20, lambda j: f"{j.get('company_bonus', 0)} {j.get('company_reason', '')}"),
        ("扣分", 30, lambda j: f"{j.get('negative_penalty', 0)} {', '.join(j.get('negative_reasons', []))}"),
        ("JD", 60, lambda j: (j.get("jd") or j.get("text", ""))[:500]),
        ("召回词", 12, lambda j: j.get("source_keyword", "")),
        ("链接", 40, lambda j: j.get("href", "")),
    ]

    def mk(name, jl, color):
        ws = wb.create_sheet(name)
        for col, h in enumerate(main_cols, 1):
            c = ws.cell(row=1, column=col, value=h[0])
            c.font = hf
            c.fill = hfill
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = border
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = h[1]
        rf = PatternFill(start_color=color, end_color=color, fill_type="solid")
        for ri, j in enumerate(jl, 2):
            for col, (_, _, gv) in enumerate(main_cols, 1):
                try: v = gv(j)
                except: v = ""
                c = ws.cell(row=ri, column=col, value=v)
                c.alignment = wrap
                c.border = border
                c.fill = rf
            if j.get("href"):
                lc = ws.cell(row=ri, column=len(main_cols))
                lc.hyperlink = j["href"]
                lc.font = Font(color="0563C1", underline="single")
        ws.freeze_panes = "A2"
        if jl:
            ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(main_cols))}{len(jl)+1}"

    mk("P0_必投", tiers.get("P0", []), "E8F8F5")
    mk("P1_应投", tiers.get("P1", []), "FFF8E1")
    mk("P2_可投", tiers.get("P2", []), "F5F5F5")
    mk("P3_备选", tiers.get("P3", []), "FAFAFA")

    ws = wb.create_sheet("Rejected")
    headers = ["拒绝原因", "职位", "公司", "经验", "召回词", "链接"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hf
        c.fill = hfill
    widths = [25, 35, 22, 12, 12, 40]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    rfill = PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid")
    for ri, j in enumerate(rejected, 2):
        vals = [j.get("reject_reason", ""), j.get("title", ""), j.get("company", ""),
                j.get("experience") or j.get("exp", ""), j.get("source_keyword", ""), j.get("href", "")]
        for col, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=col, value=v)
            c.alignment = wrap
            c.fill = rfill

    ws = wb.create_sheet("统计")
    ws.append(["模型", "v4.1"])
    ws.append(["P0", len(tiers["P0"])])
    ws.append(["P1", len(tiers["P1"])])
    ws.append(["P2", len(tiers["P2"])])
    ws.append(["P3", len(tiers["P3"])])
    ws.append(["Rejected", len(rejected)])

    path = OUTPUT_DIR / "jobs.xlsx"
    wb.save(path)
    print(f"\n✓ Excel: {path}")


if __name__ == "__main__":
    main()
