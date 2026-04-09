#!/usr/bin/python3
"""
v5.0 - 求职旅程中心化重构
- Today: 今日焦点
- Discover: Swipe 卡片 triage
- Pipeline: Kanban 看板
- Knowledge: 面试沉淀（占位）
- Decision: Offer 对比（占位）
"""
import json
import re
from pathlib import Path

INPUT = Path(__file__).parent / "v4_1_output" / "tiered.json"
REJECTED = Path(__file__).parent / "v4_1_output" / "rejected.json"
OUTPUT = Path(__file__).parent / "v4_1_output" / "v5.html"


PUA_RE = re.compile(r"[\ue000-\uf8ff]")


def clean_text(s):
    if not s:
        return s
    s = PUA_RE.sub("◆", s)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s


def clean_title(s):
    if not s:
        return s
    return clean_text(s.split("\n")[0].strip())


def clean_salary(s):
    if not s:
        return s
    pua_count = len(PUA_RE.findall(s))
    if pua_count >= 2:
        suffix = PUA_RE.sub("", s).strip()
        if suffix and suffix != "K":
            return f"待登录 {suffix}"
        return "待登录"
    return clean_text(s)


def clean_job(j):
    if "title" in j:
        j["title"] = clean_title(j["title"])
    if "company" in j:
        j["company"] = clean_text(j["company"]).strip()
    if "salary" in j:
        j["salary"] = clean_salary(j["salary"])
    if "area" in j:
        j["area"] = clean_text(j["area"]).strip()
    if "experience" in j:
        j["experience"] = clean_text(j["experience"]).strip()
    if "jd" in j:
        j["jd"] = clean_text(j["jd"])
    if "company_info" in j:
        j["company_info"] = clean_text(j["company_info"])
    if "tags" in j:
        j["tags"] = clean_text(j["tags"])
    for k in ("text", "card_text", "score", "matched"):
        j.pop(k, None)
    return j


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>求职 OS · v5</title>
<style>
:root {
  --primary: #10b981;
  --primary-dark: #059669;
  --primary-light: #d1fae5;
  --target: #10b981;
  --practice: #3b82f6;
  --backup: #94a3b8;
  --ignored: #cbd5e1;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #6366f1;

  --bg: #f8fafc;
  --bg-elevated: #ffffff;
  --bg-subtle: #f1f5f9;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --text: #0f172a;
  --text-muted: #64748b;
  --text-soft: #94a3b8;

  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.08);
  --shadow-lg: 0 10px 25px rgba(15, 23, 42, 0.10);

  --r-sm: 6px;
  --r: 10px;
  --r-lg: 14px;
  --r-xl: 20px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, "SF Pro Text", BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  font-size: 14px;
}

button { font-family: inherit; }

/* ─── 顶部导航 ─── */
header {
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow-sm);
}

.header-inner {
  max-width: 1480px;
  margin: 0 auto;
  padding: 14px 28px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}

.brand-icon {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  box-shadow: 0 4px 10px rgba(16, 185, 129, 0.25);
}

.brand-version {
  font-size: 10px;
  background: var(--primary-light);
  color: var(--primary-dark);
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 700;
  margin-left: 4px;
}

.view-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-subtle);
  padding: 4px;
  border-radius: var(--r);
}

.view-tab {
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  border-radius: 7px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.18s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.view-tab:hover { color: var(--text); }

.view-tab.active {
  background: var(--bg-elevated);
  color: var(--primary);
  box-shadow: var(--shadow);
}

.view-tab .badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--primary);
  color: #fff;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 700;
}

.action-btns {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  border-radius: var(--r);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: all 0.15s;
  font-size: 14px;
}

.icon-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

main {
  max-width: 1480px;
  margin: 0 auto;
  padding: 28px;
}

/* ─── Today 视图 ─── */
.today-greeting {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
  letter-spacing: -0.02em;
}

.today-sub {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 24px;
}

.today-section {
  background: var(--bg-elevated);
  border-radius: var(--r-lg);
  padding: 22px 26px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.today-section.urgent {
  border-left: 4px solid var(--warning);
}

.today-section.action {
  border-left: 4px solid var(--primary);
}

.today-section.alert {
  border-left: 4px solid var(--danger);
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text);
}

.section-title .badge {
  display: inline-flex;
  padding: 2px 9px;
  background: var(--primary-light);
  color: var(--primary-dark);
  border-radius: 11px;
  font-size: 11px;
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0;
}

.section-title.warning .badge { background: #fef3c7; color: #92400e; }
.section-title.danger .badge { background: #fee2e2; color: #991b1b; }

.upcoming-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.upcoming-item:last-child { border-bottom: none; }

.countdown {
  flex-shrink: 0;
  width: 88px;
  text-align: center;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  padding: 12px 8px;
  border-radius: var(--r);
  border: 1px solid #fcd34d;
}

.countdown.imminent { background: linear-gradient(135deg, #fee2e2, #fecaca); border-color: #fca5a5; }
.countdown.relaxed { background: linear-gradient(135deg, #d1fae5, #a7f3d0); border-color: #6ee7b7; }

.countdown .num {
  font-size: 22px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.02em;
  line-height: 1;
}

.countdown .unit {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  margin-top: 2px;
}

.upcoming-info {
  flex: 1;
  min-width: 0;
}

.upcoming-info .ui-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 3px;
}

.upcoming-info .ui-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--r-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: #fff;
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3);
}

.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(16, 185, 129, 0.4); }

.btn-secondary {
  background: var(--bg-subtle);
  color: var(--text);
  border: 1.5px solid var(--border);
}

.btn-secondary:hover { background: var(--bg); border-color: var(--border-strong); }

.followup-list .followup-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}

.followup-list .followup-item:last-child { border-bottom: none; }

.followup-info { flex: 1; min-width: 0; }

.followup-info .fi-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 2px;
}

.followup-info .fi-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.followup-info .fi-meta .days {
  color: var(--warning);
  font-weight: 700;
}

.followup-info .fi-meta .days.danger {
  color: var(--danger);
}

/* ─── Discover (Inbox) ─── */
.discover-toolbar {
  background: var(--bg-elevated);
  border-radius: var(--r-lg);
  padding: 14px 18px;
  margin-bottom: 14px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.discover-toolbar h2 {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.discover-counter {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}

.discover-filters {
  display: flex;
  gap: 4px;
}

.discover-filter {
  padding: 5px 12px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-muted);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.15s;
}

.discover-filter:hover { color: var(--text); }
.discover-filter.active {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.batch-actions {
  display: flex;
  gap: 6px;
  margin-left: 10px;
  padding-left: 10px;
  border-left: 1px solid var(--border);
}

.batch-actions button {
  padding: 5px 10px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-muted);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
}

.batch-actions button:hover {
  border-color: var(--danger);
  color: var(--danger);
}

/* Inbox 列表 */
.inbox {
  background: var(--bg-elevated);
  border-radius: var(--r-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.inbox-row {
  display: grid;
  grid-template-columns: 50px 1fr 160px 110px 90px 200px;
  gap: 12px;
  align-items: center;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}

.inbox-row:last-child { border-bottom: none; }
.inbox-row:hover { background: var(--bg-subtle); }
.inbox-row.expanded { background: var(--bg-subtle); }

.ir-score {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  box-shadow: var(--shadow-sm);
  letter-spacing: -0.02em;
  flex-shrink: 0;
}

.ir-score.tier-P1 { background: linear-gradient(135deg, #f59e0b, #d97706); }
.ir-score.tier-P2 { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.ir-score.tier-P3 { background: linear-gradient(135deg, #94a3b8, #64748b); }

.ir-main { min-width: 0; }

.ir-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ir-clusters {
  display: flex;
  gap: 4px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.ir-clusters .dc-cluster {
  font-size: 10px;
  padding: 1px 7px;
  white-space: nowrap;
}

.ir-company, .ir-area, .ir-exp {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ir-company { font-weight: 600; color: var(--text); }

.ir-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.ir-actions button {
  padding: 7px 14px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  transition: all 0.12s;
}

.ir-actions .btn-skip {
  color: var(--text-muted);
}

.ir-actions .btn-skip:hover {
  border-color: var(--text-muted);
  background: var(--bg-subtle);
}

.ir-actions .btn-keep {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
  box-shadow: 0 1px 3px rgba(16, 185, 129, 0.25);
}

.ir-actions .btn-keep:hover {
  background: var(--primary-dark);
  transform: translateY(-1px);
}

/* 展开的详情 */
.inbox-detail {
  background: var(--bg-subtle);
  padding: 16px 22px 18px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
}

.inbox-detail .id-jd {
  white-space: pre-wrap;
  line-height: 1.7;
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-elevated);
  padding: 12px 14px;
  border-radius: var(--r-sm);
  margin-bottom: 10px;
}

.inbox-detail .id-actions {
  display: flex;
  gap: 8px;
}

.discover-empty {
  text-align: center;
  padding: 80px 20px;
  background: var(--bg-elevated);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow);
}

.discover-empty .icon { font-size: 56px; margin-bottom: 16px; }
.discover-empty h3 { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.discover-empty p { color: var(--text-muted); margin-bottom: 16px; }

.dc-cluster {
  padding: 4px 10px;
  background: var(--primary-light);
  color: var(--primary-dark);
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  display: inline-block;
}

.dc-cluster.core {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: #fff;
}

@media (max-width: 1100px) {
  .inbox-row {
    grid-template-columns: 50px 1fr 140px;
    grid-template-rows: auto auto;
  }
  .ir-area, .ir-exp { display: none; }
  .ir-actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
  }
}

/* ─── Pipeline (Kanban) ─── */
.kanban {
  display: grid;
  grid-template-columns: repeat(6, minmax(220px, 1fr));
  gap: 14px;
  overflow-x: auto;
  padding-bottom: 20px;
}

.kanban-col {
  background: var(--bg-subtle);
  border-radius: var(--r-lg);
  padding: 14px;
  min-height: 200px;
}

.kanban-col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kanban-col-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  background: var(--bg-elevated);
  border-radius: 11px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
}

.kanban-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kanban-card {
  background: var(--bg-elevated);
  border-radius: var(--r);
  padding: 12px 14px;
  box-shadow: var(--shadow);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
}

.kanban-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }

.kanban-card.intent-target { border-left-color: var(--target); }
.kanban-card.intent-practice { border-left-color: var(--practice); }
.kanban-card.intent-backup { border-left-color: var(--backup); }

.kc-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 4px;
  word-break: break-word;
  line-height: 1.4;
}

.kc-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.kc-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.kc-tag {
  font-size: 9px;
  padding: 2px 6px;
  background: var(--bg-subtle);
  border-radius: 4px;
  font-weight: 600;
  color: var(--text-muted);
}

.kc-tag.intent-target { background: #d1fae5; color: var(--primary-dark); }
.kc-tag.intent-practice { background: #dbeafe; color: #1e40af; }
.kc-tag.intent-backup { background: #f1f5f9; color: var(--text-muted); }
.kc-tag.urgent { background: #fef3c7; color: #92400e; }
.kc-tag.danger { background: #fee2e2; color: #991b1b; }

.kanban-empty {
  font-size: 12px;
  color: var(--text-soft);
  text-align: center;
  padding: 20px 10px;
}

/* ─── Modal ─── */
.modal-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-bg.active { display: flex; }

.modal {
  background: var(--bg-elevated);
  border-radius: var(--r-xl);
  padding: 28px 32px;
  max-width: 600px;
  width: 100%;
  box-shadow: var(--shadow-lg);
  max-height: 85vh;
  overflow-y: auto;
}

.modal h3 {
  margin-bottom: 14px;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.modal-jd {
  background: var(--bg-subtle);
  padding: 14px 16px;
  border-radius: var(--r-sm);
  font-size: 12px;
  white-space: pre-wrap;
  line-height: 1.7;
  color: var(--text-muted);
  max-height: 240px;
  overflow-y: auto;
  margin-bottom: 16px;
}

.modal label {
  display: block;
  margin-bottom: 5px;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.modal input, .modal select, .modal textarea {
  width: 100%;
  padding: 9px 13px;
  border: 1.5px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 13px;
  outline: none;
  margin-bottom: 14px;
  font-family: inherit;
  background: var(--bg-elevated);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* ─── Toast ─── */
.toast {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%) translateY(20px);
  background: var(--text);
  color: #fff;
  padding: 12px 24px;
  border-radius: var(--r);
  font-size: 13px;
  font-weight: 600;
  box-shadow: var(--shadow-lg);
  z-index: 2000;
  opacity: 0;
  transition: all 0.25s;
}

.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

/* ─── Empty ─── */
.empty {
  text-align: center;
  padding: 80px 20px;
  color: var(--text-soft);
}
.empty .icon { font-size: 56px; margin-bottom: 12px; opacity: 0.4; }
.empty h3 { font-size: 16px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
.empty p { font-size: 13px; }

/* ─── 训练场 ─── */
.training-header {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 24px;
}
.training-header h2 {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.training-header .sub {
  font-size: 13px;
  color: var(--text-muted);
}

.training-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.tstat-card {
  background: var(--bg-elevated);
  border-radius: var(--r-lg);
  padding: 18px 22px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-left: 4px solid var(--primary);
}
.tstat-card.warning { border-left-color: var(--warning); }
.tstat-card.danger { border-left-color: var(--danger); }
.tstat-num {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
}
.tstat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
  font-weight: 600;
}

.training-section {
  background: var(--bg-elevated);
  border-radius: var(--r-lg);
  padding: 22px 26px;
  margin-bottom: 16px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.training-section h3 {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 14px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  display: flex;
  align-items: center;
  gap: 8px;
}

.heatmap-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px 70px;
  gap: 14px;
  align-items: center;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}
.heatmap-row:last-child { border-bottom: none; }
.heatmap-row:hover { background: var(--bg-subtle); }

.heatmap-row .hr-name {
  font-size: 13px;
  font-weight: 600;
}
.heatmap-row .hr-bar-wrap {
  height: 10px;
  background: var(--bg-subtle);
  border-radius: 5px;
  overflow: hidden;
}
.heatmap-row .hr-bar {
  height: 100%;
  border-radius: 5px;
  transition: width 0.3s;
}
.heatmap-row.weak .hr-bar { background: linear-gradient(90deg, var(--danger), #f87171); }
.heatmap-row.mid .hr-bar { background: linear-gradient(90deg, var(--warning), #fbbf24); }
.heatmap-row.good .hr-bar { background: linear-gradient(90deg, var(--primary), var(--primary-dark)); }

.heatmap-row .hr-stat {
  font-size: 12px;
  color: var(--text-muted);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.heatmap-row .hr-score {
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}
.heatmap-row.weak .hr-score { color: var(--danger); }
.heatmap-row.mid .hr-score { color: var(--warning); }
.heatmap-row.good .hr-score { color: var(--primary); }

.reflection-card {
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 14px 18px;
  margin-bottom: 10px;
  background: var(--bg-elevated);
  cursor: pointer;
  transition: all 0.15s;
}
.reflection-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}
.reflection-card .rc-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.reflection-card .rc-title {
  font-size: 14px;
  font-weight: 700;
}
.reflection-card .rc-meta {
  font-size: 11px;
  color: var(--text-muted);
}
.reflection-card .rc-q-summary {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  gap: 8px;
}
.reflection-card .rc-q-summary span.good { color: var(--primary); font-weight: 700; }
.reflection-card .rc-q-summary span.ok { color: var(--warning); font-weight: 700; }
.reflection-card .rc-q-summary span.bad { color: var(--danger); font-weight: 700; }

.reflection-detail {
  background: var(--bg-subtle);
  border-radius: var(--r);
  padding: 16px 20px;
  margin-top: 10px;
}

.q-item {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  padding: 10px 14px;
  margin-bottom: 8px;
}
.q-item:last-child { margin-bottom: 0; }
.q-item.rating-good { border-left: 3px solid var(--primary); }
.q-item.rating-ok { border-left: 3px solid var(--warning); }
.q-item.rating-bad { border-left: 3px solid var(--danger); }

.q-text {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 5px;
}
.q-topics {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 5px;
}
.q-topic-chip {
  font-size: 10px;
  padding: 1px 7px;
  background: var(--bg-subtle);
  color: var(--text-muted);
  border-radius: 4px;
  font-weight: 600;
}
.q-rating {
  font-size: 11px;
  font-weight: 700;
}
.q-rating.good { color: var(--primary); }
.q-rating.ok { color: var(--warning); }
.q-rating.bad { color: var(--danger); }
.q-review {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed var(--border);
}

.btn-ai {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 3px rgba(99, 102, 241, 0.3);
}
.btn-ai:hover { transform: translateY(-1px); box-shadow: 0 3px 8px rgba(99, 102, 241, 0.4); }
.btn-ai.has-answer {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  box-shadow: 0 1px 3px rgba(16, 185, 129, 0.3);
}

.qbtn {
  padding: 3px 9px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  border-radius: 5px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.12s;
}
.qbtn:hover { border-color: var(--text-muted); background: var(--bg-subtle); }
.qbtn.danger:hover { border-color: var(--danger); color: var(--danger); }
.qbtn.small { padding: 2px 7px; font-size: 10px; }

.q-answer {
  margin-top: 10px;
  background: linear-gradient(135deg, #f5f3ff, #eff6ff);
  border: 1px solid #c7d2fe;
  border-radius: var(--r-sm);
  padding: 12px 14px;
}
.q-answer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 700;
  color: #4338ca;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.q-answer-body {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
  max-height: 500px;
  overflow-y: auto;
}

/* 复盘录入 modal */
.q-row {
  background: var(--bg-subtle);
  border-radius: var(--r-sm);
  padding: 12px 14px;
  margin-bottom: 10px;
}

.q-row textarea {
  margin-bottom: 8px;
}

.topic-chip-bar {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.topic-chip {
  padding: 3px 9px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 11px;
  cursor: pointer;
  font-weight: 600;
  color: var(--text-muted);
}
.topic-chip:hover { border-color: var(--primary); color: var(--primary); }
.topic-chip.selected {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.rating-bar {
  display: flex;
  gap: 6px;
}
.rating-btn {
  flex: 1;
  padding: 6px 8px;
  border: 1.5px solid var(--border);
  background: var(--bg-elevated);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
}
.rating-btn:hover { border-color: var(--text-muted); }
.rating-btn.selected.good { background: var(--primary); color: #fff; border-color: var(--primary); }
.rating-btn.selected.ok { background: var(--warning); color: #fff; border-color: var(--warning); }
.rating-btn.selected.bad { background: var(--danger); color: #fff; border-color: var(--danger); }

/* ─── 响应式 ─── */
@media (max-width: 900px) {
  .header-inner { padding: 12px 16px; flex-wrap: wrap; }
  main { padding: 16px; }
  .kanban { grid-template-columns: 1fr; }
  .discover-actions { grid-template-columns: repeat(5, 1fr); gap: 6px; }
  .intent-btn { padding: 10px 4px; }
}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <div class="brand">
      <div class="brand-icon">💼</div>
      求职 OS <span class="brand-version">v5</span>
    </div>
    <div class="view-tabs" id="view-tabs">
      <button class="view-tab active" data-view="today">🎯 Today</button>
      <button class="view-tab" data-view="discover">🔍 Discover <span class="badge" id="discover-badge">0</span></button>
      <button class="view-tab" data-view="pipeline">💼 Pipeline <span class="badge" id="pipeline-badge">0</span></button>
      <button class="view-tab" data-view="training">🥋 训练场</button>
      <button class="view-tab" data-view="decision">📊 Decision</button>
    </div>
    <div class="action-btns">
      <button class="icon-btn" id="btn-export" title="导出数据">⬇</button>
      <button class="icon-btn" id="btn-import" title="导入数据">⬆</button>
    </div>
  </div>
</header>

<main id="main-content"></main>

<!-- Modal: 添加面试 -->
<div class="modal-bg" id="modal-interview">
  <div class="modal">
    <h3>📅 添加面试</h3>
    <div id="modal-job-info"></div>
    <label>类型</label>
    <select id="iv-type">
      <optgroup label="前置">
        <option>HR 沟通</option>
        <option>简历筛</option>
        <option>笔试</option>
      </optgroup>
      <optgroup label="技术面">
        <option>一面</option>
        <option>二面</option>
        <option>三面</option>
        <option>技术面</option>
        <option>部门面</option>
        <option>交叉面</option>
        <option>Onsite</option>
      </optgroup>
      <optgroup label="后置">
        <option>HR 终面</option>
        <option>谈薪</option>
      </optgroup>
    </select>
    <label>时间</label>
    <input type="datetime-local" id="iv-time">
    <label>形式</label>
    <input type="text" id="iv-location" placeholder="腾讯会议 / 飞书 / 现场...">
    <label>结果</label>
    <select id="iv-result">
      <option value="pending">· 待定</option>
      <option value="pass">✓ 通过</option>
      <option value="fail">✗ 未通过</option>
    </select>
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveInterview()">保存</button>
    </div>
  </div>
</div>

<input type="file" id="import-file" accept=".json" style="display:none">

<script>
const DATA = __DATA_PLACEHOLDER__;
const REJECTED = __REJECTED_PLACEHOLDER__;

// ═══════════════════════════════════════════════════════════════
// 数据模型 v3 - 正交化
// ═══════════════════════════════════════════════════════════════

const STORE_KEY = 'job_tracker_v3';
const OLD_KEY = 'job_tracker_v2';

const INTENT = {
  unknown: { label: '未决定', color: 'var(--text-soft)', icon: '·' },
  target: { label: '目标', color: 'var(--target)', icon: '🎯' },
  practice: { label: '练手', color: 'var(--practice)', icon: '💪' },
  backup: { label: '备选', color: 'var(--backup)', icon: '🤔' },
  ignored: { label: '忽略', color: 'var(--ignored)', icon: '🚫' },
};

const PIPELINE_COLS = [
  { key: 'todo', label: '待投递' },
  { key: 'applied', label: '已投递' },
  { key: 'contacting', label: '沟通中' },
  { key: 'interviewing', label: '面试中' },
  { key: 'offer', label: 'Offer' },
  { key: 'closed', label: '已结束' },
];

const STATUS_TO_PIPELINE = {
  '未投递': 'todo', '已投递': 'applied', '简历筛中': 'contacting', '笔试中': 'contacting',
  '面试中': 'interviewing', 'HR终面': 'interviewing', '谈薪中': 'offer',
  '已收到Offer': 'offer', '已接受': 'closed', '已拒绝Offer': 'closed',
  '我放弃': 'closed', '简历挂': 'closed', '笔试挂': 'closed', '面试挂': 'closed',
};

const STATUS_TO_OUTCOME = {
  '已接受': 'accepted', '已拒绝Offer': 'rejected_by_me', '我放弃': 'rejected_by_me',
  '简历挂': 'rejected_by_them', '笔试挂': 'rejected_by_them', '面试挂': 'rejected_by_them',
};

function loadStore() {
  try {
    let s = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    if (s) return s;
    // 从 v2 迁移
    const oldStore = JSON.parse(localStorage.getItem(OLD_KEY) || '{}');
    s = {};
    Object.entries(oldStore).forEach(([id, oldState]) => {
      s[id] = {
        intent: (oldState.status && oldState.status !== '未投递') ? 'target' : 'unknown',
        pipelineCol: STATUS_TO_PIPELINE[oldState.status] || 'todo',
        outcome: STATUS_TO_OUTCOME[oldState.status] || null,
        triagedAt: oldState.appliedAt || null,
        appliedAt: oldState.appliedAt || null,
        lastTouchAt: oldState.lastUpdateAt || oldState.appliedAt || null,
        interviews: oldState.interviews || [],
        notes: oldState.notes || '',
        legacyStatus: oldState.status,
      };
    });
    if (Object.keys(s).length > 0) {
      saveStore(s);
      console.log('从 v2 迁移了', Object.keys(s).length, '条记录');
    }
    return s;
  } catch (e) {
    return {};
  }
}

function saveStore(s) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(s)); }
  catch (e) { showToast('保存失败'); }
}

function jobId(j) { return j.href || `${j.company}|${j.title}`; }

function getState(j) {
  const s = loadStore();
  return s[jobId(j)] || {
    intent: 'unknown',
    pipelineCol: 'todo',
    outcome: null,
    triagedAt: null,
    appliedAt: null,
    lastTouchAt: null,
    interviews: [],
    notes: '',
  };
}

function setState(j, patch) {
  const s = loadStore();
  const id = jobId(j);
  s[id] = { ...getState(j), ...patch, lastTouchAt: new Date().toISOString() };
  saveStore(s);
}

function setIntent(j, intent) {
  const cur = getState(j);
  const patch = { intent, triagedAt: cur.triagedAt || new Date().toISOString() };
  // 如果是忽略，pipelineCol 不变；如果是 target/practice，确保至少在 todo
  setState(j, patch);
}

function markApplied(j) {
  setState(j, {
    pipelineCol: 'applied',
    appliedAt: new Date().toISOString(),
    intent: getState(j).intent === 'unknown' ? 'target' : getState(j).intent,
  });
}

function setPipelineCol(j, col) {
  const patch = { pipelineCol: col };
  if (col === 'applied' && !getState(j).appliedAt) {
    patch.appliedAt = new Date().toISOString();
  }
  setState(j, patch);
}

function addInterview(j, iv) {
  const cur = getState(j);
  cur.interviews = [...(cur.interviews || []), iv];
  // 自动推进 pipelineCol
  if (iv.type === '笔试') cur.pipelineCol = 'contacting';
  else if (['一面', '二面', '三面', '技术面', '部门面', '交叉面', 'Onsite'].includes(iv.type)) {
    if (cur.pipelineCol !== 'offer') cur.pipelineCol = 'interviewing';
  } else if (['HR 终面', '谈薪'].includes(iv.type)) {
    cur.pipelineCol = 'offer';
  }
  if (!cur.appliedAt) cur.appliedAt = new Date().toISOString();
  if (cur.intent === 'unknown') cur.intent = 'target';
  setState(j, cur);
}

// ═══════════════════════════════════════════════════════════════
// 工具
// ═══════════════════════════════════════════════════════════════

function allJobs() {
  return [...(DATA.P0||[]), ...(DATA.P1||[]), ...(DATA.P2||[]), ...(DATA.P3||[])];
}

function getJobMap() {
  const m = {};
  allJobs().forEach(j => { m[jobId(j)] = j; });
  REJECTED.forEach(j => { m[jobId(j)] = j; });
  return m;
}

function findJobById(id) {
  for (const j of allJobs()) if (jobId(j) === id) return j;
  for (const j of REJECTED) if (jobId(j) === id) return j;
  return null;
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function escapeAttr(s) {
  return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/\n/g,'').replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function daysSince(iso) {
  if (!iso) return 0;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

function hoursUntil(iso) {
  if (!iso) return 0;
  return (new Date(iso).getTime() - Date.now()) / 3600000;
}

function showToast(msg) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2200);
}

function fmtRelativeFuture(iso) {
  const h = hoursUntil(iso);
  if (h < 0) return '已过';
  if (h < 1) return `${Math.floor(h * 60)}分钟`;
  if (h < 24) return `${Math.floor(h)}小时`;
  return `${Math.floor(h / 24)}天`;
}

// ═══════════════════════════════════════════════════════════════
// 视图：Today
// ═══════════════════════════════════════════════════════════════

function renderToday() {
  const store = loadStore();
  const jobMap = getJobMap();

  // 1. 即将到来的面试（24小时内）
  const upcomingInterviews = [];
  Object.entries(store).forEach(([id, st]) => {
    const job = jobMap[id];
    if (!job || !st.interviews) return;
    st.interviews.forEach((iv, idx) => {
      const h = hoursUntil(iv.time);
      if (h >= 0 && h <= 72) {
        upcomingInterviews.push({ job, iv, idx, hoursLeft: h });
      }
    });
  });
  upcomingInterviews.sort((a, b) => a.hoursLeft - b.hoursLeft);

  // 2. 需要跟进（applied >3 days, no movement）
  const needFollowup = [];
  Object.entries(store).forEach(([id, st]) => {
    if (st.pipelineCol !== 'applied') return;
    const days = daysSince(st.appliedAt);
    if (days >= 3) {
      const job = jobMap[id];
      if (job) needFollowup.push({ job, days, st });
    }
  });
  needFollowup.sort((a, b) => b.days - a.days);

  // 3. 待 triage 的新岗位
  const toTriage = allJobs().filter(j => {
    const st = getState(j);
    return st.intent === 'unknown';
  });

  // 4. 数据
  const stats = {
    target: Object.values(store).filter(s => s.intent === 'target').length,
    practice: Object.values(store).filter(s => s.intent === 'practice').length,
    interviewing: Object.values(store).filter(s => s.pipelineCol === 'interviewing' || s.pipelineCol === 'offer').length,
    pending: Object.values(store).filter(s => s.pipelineCol === 'applied' || s.pipelineCol === 'contacting').length,
  };

  const hour = new Date().getHours();
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';

  let html = `
    <div class="today-greeting">${greeting} 👋</div>
    <div class="today-sub">
      🎯 ${stats.target} 个目标 · 💪 ${stats.practice} 个练手 · 面试中 ${stats.interviewing} · 待跟进 ${stats.pending}
    </div>
  `;

  // Section 1: 即将到来的面试
  if (upcomingInterviews.length > 0) {
    html += `
      <div class="today-section urgent">
        <div class="section-title warning">⏰ 即将到来的面试 <span class="badge">${upcomingInterviews.length}</span></div>
        ${upcomingInterviews.map(({ job, iv, hoursLeft }) => {
          const cls = hoursLeft < 6 ? 'imminent' : hoursLeft < 24 ? '' : 'relaxed';
          return `
            <div class="upcoming-item">
              <div class="countdown ${cls}">
                <div class="num">${fmtRelativeFuture(iv.time).match(/\d+/)[0]}</div>
                <div class="unit">${fmtRelativeFuture(iv.time).replace(/\d+/, '')}后</div>
              </div>
              <div class="upcoming-info">
                <div class="ui-title">${escapeHtml(iv.type)} · ${escapeHtml(job.title)}</div>
                <div class="ui-meta">🏢 ${escapeHtml(job.company || '')} · ⏰ ${fmtDate(iv.time)}${iv.location ? ' · 📍 ' + escapeHtml(iv.location) : ''}</div>
              </div>
              <button class="btn btn-secondary" onclick="goToPipeline()">查看 →</button>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // Section 2: 需要跟进
  if (needFollowup.length > 0) {
    html += `
      <div class="today-section alert">
        <div class="section-title danger">🔥 需要跟进 <span class="badge">${needFollowup.length}</span></div>
        <div class="followup-list">
          ${needFollowup.slice(0, 5).map(({ job, days }) => {
            const isDanger = days >= 7;
            return `
              <div class="followup-item">
                <div class="followup-info">
                  <div class="fi-title">${escapeHtml(job.title)}</div>
                  <div class="fi-meta">
                    ${escapeHtml(job.company || '')} · 投递于 <span class="days ${isDanger ? 'danger' : ''}">${days} 天前</span>
                  </div>
                </div>
                ${job.href ? `<a class="btn btn-secondary" href="${job.href}" target="_blank">戳 HR</a>` : ''}
                <button class="btn btn-primary" onclick="addInterviewById('${escapeAttr(jobId(job))}')">+ 添加面试</button>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  // Section 3: 待 triage
  if (toTriage.length > 0) {
    html += `
      <div class="today-section action">
        <div class="section-title">🆕 新岗位待 triage <span class="badge">${toTriage.length}</span></div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px">用 Discover 一张张快速决策，把岗位分流成「目标 / 练手 / 备选 / 忽略」</p>
        <button class="btn btn-primary" onclick="switchView('discover')">开始 Triage →</button>
      </div>
    `;
  }

  // 默认 section（如果没有任何 todo）
  if (upcomingInterviews.length === 0 && needFollowup.length === 0 && toTriage.length === 0) {
    html += `
      <div class="today-section">
        <div class="empty">
          <div class="icon">✨</div>
          <h3>今天暂无待办</h3>
          <p>所有任务都跟上了，继续保持！</p>
        </div>
      </div>
    `;
  }

  return html;
}

// ═══════════════════════════════════════════════════════════════
// 视图：Discover (Inbox 列表)
// ═══════════════════════════════════════════════════════════════

let discoverFilter = 'P0';
let expandedRowId = null;

function getDiscoverQueue() {
  const all = allJobs();
  let queue = all.filter(j => getState(j).intent === 'unknown');
  if (discoverFilter === 'P0') queue = queue.filter(j => DATA.P0.includes(j));
  else if (discoverFilter === 'P1') queue = queue.filter(j => DATA.P1.includes(j));
  else if (discoverFilter === 'high') queue = queue.filter(j => (j.final_score || 0) >= 50);
  // 按分数降序
  queue.sort((a, b) => (b.final_score || 0) - (a.final_score || 0));
  return queue;
}

function renderDiscover() {
  const queue = getDiscoverQueue();

  const toolbar = `
    <div class="discover-toolbar">
      <h2>🔍 Discover</h2>
      <div class="discover-filters">
        <button class="discover-filter ${discoverFilter === 'P0' ? 'active' : ''}" onclick="setDiscoverFilter('P0')">P0 必投</button>
        <button class="discover-filter ${discoverFilter === 'P1' ? 'active' : ''}" onclick="setDiscoverFilter('P1')">P1 应投</button>
        <button class="discover-filter ${discoverFilter === 'high' ? 'active' : ''}" onclick="setDiscoverFilter('high')">高分 ≥50</button>
        <button class="discover-filter ${discoverFilter === 'all' ? 'active' : ''}" onclick="setDiscoverFilter('all')">全部</button>
      </div>
      <span class="discover-counter">${queue.length} 个待决策</span>
      ${queue.length > 0 ? `
        <div class="batch-actions">
          <button onclick="batchSkip()">✕ 全部跳过</button>
        </div>
      ` : ''}
    </div>
  `;

  if (queue.length === 0) {
    return toolbar + `
      <div class="discover-empty">
        <div class="icon">🎉</div>
        <h3>当前过滤下没有待决策的岗位</h3>
        <p>切换其他过滤器，或去 Pipeline 看你已关注的岗位</p>
        <button class="btn btn-primary" onclick="switchView('pipeline')">查看 Pipeline →</button>
      </div>
    `;
  }

  return toolbar + `
    <div class="inbox">
      ${queue.slice(0, 100).map(job => renderInboxRow(job)).join('')}
    </div>
    ${queue.length > 100 ? `<div style="text-align:center;padding:14px;color:var(--text-muted);font-size:12px">显示前 100 条，共 ${queue.length} 条</div>` : ''}
  `;
}

function renderInboxRow(job) {
  const id = jobId(job);
  const tier = DATA.P0.includes(job) ? 'P0' : DATA.P1.includes(job) ? 'P1' : DATA.P2.includes(job) ? 'P2' : 'P3';
  const isExpanded = expandedRowId === id;

  // 取前 2 个核心簇
  const coreClusters = (job.cluster_hits || []).slice(0, 2).map(h => {
    const isCore = ['platform_ai_infra', 'go_k8s_platform', 'gpu_cloud_platform'].includes(h.name);
    return `<span class="dc-cluster ${isCore ? 'core' : ''}">${h.display}</span>`;
  }).join('');

  const detailHTML = isExpanded ? `
    <div class="inbox-detail">
      <div class="id-jd">${escapeHtml((job.jd || '暂无 JD').slice(0, 2000))}</div>
      <div class="id-actions">
        ${job.href ? `<a class="btn btn-secondary" href="${job.href}" target="_blank" onclick="event.stopPropagation()">在 BOSS 打开</a>` : ''}
        <button class="btn btn-secondary" onclick="event.stopPropagation();skipJob('${escapeAttr(id)}')">✕ 跳过</button>
        <button class="btn btn-primary" onclick="event.stopPropagation();keepJob('${escapeAttr(id)}')">👀 关注</button>
      </div>
    </div>
  ` : '';

  return `
    <div class="inbox-row ${isExpanded ? 'expanded' : ''}" onclick="toggleRow('${escapeAttr(id)}')">
      <div class="ir-score tier-${tier}">${(job.final_score || 0).toFixed(0)}</div>
      <div class="ir-main">
        <div class="ir-title">${escapeHtml(job.title)}</div>
        <div class="ir-clusters">${coreClusters}</div>
      </div>
      <div class="ir-company">${escapeHtml(job.company || '')}</div>
      <div class="ir-area">${escapeHtml(job.area || '')}</div>
      <div class="ir-exp">${escapeHtml(job.experience || '')}</div>
      <div class="ir-actions">
        <button class="btn-skip" onclick="event.stopPropagation();skipJob('${escapeAttr(id)}')">✕ 跳过</button>
        <button class="btn-keep" onclick="event.stopPropagation();keepJob('${escapeAttr(id)}')">👀 关注</button>
      </div>
    </div>
    ${detailHTML}
  `;
}

function toggleRow(id) {
  expandedRowId = expandedRowId === id ? null : id;
  render();
}

function skipJob(id) {
  const job = findJobById(id);
  if (!job) return;
  setIntent(job, 'ignored');
  if (expandedRowId === id) expandedRowId = null;
  render();
}

function keepJob(id) {
  const job = findJobById(id);
  if (!job) return;
  // 关注 = 进入 Pipeline 的待投递列，意图先标 backup（后续在 Pipeline 里再细化）
  setIntent(job, 'backup');
  setPipelineCol(job, 'todo');
  if (expandedRowId === id) expandedRowId = null;
  showToast(`👀 已加入 Pipeline 待投递`);
  render();
}

function batchSkip() {
  const queue = getDiscoverQueue();
  if (queue.length === 0) return;
  if (!confirm(`确定跳过当前过滤下的 ${queue.length} 个岗位？`)) return;
  queue.forEach(job => setIntent(job, 'ignored'));
  showToast(`✕ 已跳过 ${queue.length} 个`);
  render();
}

function setDiscoverFilter(f) {
  discoverFilter = f;
  expandedRowId = null;
  render();
}

window.toggleRow = toggleRow;
window.skipJob = skipJob;
window.keepJob = keepJob;
window.batchSkip = batchSkip;

// ═══════════════════════════════════════════════════════════════
// 视图：Pipeline
// ═══════════════════════════════════════════════════════════════

function renderPipeline() {
  const store = loadStore();
  const jobMap = getJobMap();

  // 收集所有 intent != unknown && intent != ignored 的岗位
  const groups = {};
  PIPELINE_COLS.forEach(c => groups[c.key] = []);

  Object.entries(store).forEach(([id, st]) => {
    if (st.intent === 'unknown' || st.intent === 'ignored') return;
    const job = jobMap[id];
    if (!job) return;
    const col = st.pipelineCol || 'todo';
    groups[col].push({ job, st });
  });

  // 每列按 lastTouchAt 排序
  Object.values(groups).forEach(g => g.sort((a, b) => {
    const la = a.st.lastTouchAt || a.st.appliedAt || '';
    const lb = b.st.lastTouchAt || b.st.appliedAt || '';
    return lb.localeCompare(la);
  }));

  const totalCount = Object.values(groups).reduce((s, g) => s + g.length, 0);

  if (totalCount === 0) {
    return `
      <div class="empty">
        <div class="icon">💼</div>
        <h3>Pipeline 还是空的</h3>
        <p>去 Discover 把感兴趣的岗位标记为「目标」或「练手」</p>
        <br>
        <button class="btn btn-primary" onclick="switchView('discover')">去 Discover →</button>
      </div>
    `;
  }

  return `
    <div class="kanban">
      ${PIPELINE_COLS.map(col => `
        <div class="kanban-col">
          <div class="kanban-col-header">
            ${col.label}
            <span class="kanban-col-count">${groups[col.key].length}</span>
          </div>
          <div class="kanban-cards">
            ${groups[col.key].length === 0
              ? '<div class="kanban-empty">无</div>'
              : groups[col.key].map(({ job, st }) => renderKanbanCard(job, st)).join('')
            }
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderKanbanCard(job, st) {
  const days = st.appliedAt ? daysSince(st.appliedAt) : 0;
  let urgency = '';
  if (st.pipelineCol === 'applied' && days >= 7) urgency = 'danger';
  else if (st.pipelineCol === 'applied' && days >= 3) urgency = 'urgent';

  const intentLabel = INTENT[st.intent];
  const id = jobId(job);

  return `
    <div class="kanban-card intent-${st.intent}" onclick="openJobDetail('${escapeAttr(id)}')">
      <div class="kc-title">${escapeHtml(job.title)}</div>
      <div class="kc-meta">${escapeHtml(job.company || '')}${job.salary ? ' · ' + escapeHtml(job.salary) : ''}</div>
      <div class="kc-tags">
        <span class="kc-tag intent-${st.intent}">${intentLabel.icon} ${intentLabel.label}</span>
        ${st.appliedAt ? `<span class="kc-tag ${urgency}">${days}天前</span>` : ''}
        ${st.interviews && st.interviews.length > 0 ? `<span class="kc-tag">${st.interviews.length} 场面试</span>` : ''}
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// 详情 Modal（点击 Pipeline 卡片）
// ═══════════════════════════════════════════════════════════════

// 在第一次使用前缓存 modal 原始 HTML
const ORIGINAL_MODAL_HTML = document.getElementById('modal-interview').querySelector('.modal').innerHTML;

function openJobDetail(id) {
  const job = findJobById(id);
  if (!job) return;
  const st = getState(job);

  const html = `
    <h3 style="margin-bottom:10px">${escapeHtml(job.title)}</h3>
    <div style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
      🏢 ${escapeHtml(job.company || '')} ·
      💰 ${escapeHtml(job.salary || '?')} ·
      📍 ${escapeHtml(job.area || '')} ·
      ⏱ ${escapeHtml(job.experience || '')}
    </div>

    <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap">
      ${Object.entries(INTENT).filter(([k]) => k !== 'unknown').map(([k, v]) => `
        <button class="btn ${st.intent === k ? 'btn-primary' : 'btn-secondary'}" onclick="setIntentById('${escapeAttr(id)}', '${k}')">${v.icon} ${v.label}</button>
      `).join('')}
    </div>

    <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap">
      <span style="font-size:11px;color:var(--text-muted);align-self:center;margin-right:4px">阶段:</span>
      ${PIPELINE_COLS.map(c => `
        <button class="btn ${st.pipelineCol === c.key ? 'btn-primary' : 'btn-secondary'}" style="padding:5px 10px;font-size:11px" onclick="setPipelineColById('${escapeAttr(id)}', '${c.key}')">${c.label}</button>
      `).join('')}
    </div>

    ${st.interviews && st.interviews.length > 0 ? `
      <label>面试记录</label>
      <div style="background:var(--bg-subtle);padding:10px 14px;border-radius:6px;margin-bottom:14px">
        ${st.interviews.map((iv, i) => {
          const qCount = (iv.questions || []).length;
          return `
            <div style="display:flex;gap:8px;align-items:center;padding:6px 0;font-size:12px;border-bottom:1px solid var(--border)">
              <strong>${escapeHtml(iv.type)}</strong>
              <span style="color:var(--text-muted)">${fmtDate(iv.time)}</span>
              ${iv.location ? `<span style="color:var(--text-muted);font-size:11px">📍 ${escapeHtml(iv.location)}</span>` : ''}
              ${qCount > 0 ? `<span style="background:var(--primary-light);color:var(--primary-dark);padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700">${qCount} 题</span>` : ''}
              <span style="font-weight:600;color:${iv.result === 'pass' ? 'var(--primary)' : iv.result === 'fail' ? 'var(--danger)' : 'var(--text-muted)'}">
                ${iv.result === 'pass' ? '✓ 通过' : iv.result === 'fail' ? '✗ 未通过' : '· 待定'}
              </span>
              <button class="btn btn-secondary" style="margin-left:auto;font-size:10px;padding:3px 9px" onclick="event.stopPropagation();openReflectionModal('${escapeAttr(id)}', ${i})">📝 ${qCount > 0 ? '编辑复盘' : '复盘'}</button>
            </div>
          `;
        }).join('')}
      </div>
    ` : ''}

    <button class="btn btn-secondary" onclick="addInterviewById('${escapeAttr(id)}')">+ 添加面试</button>
    ${job.href ? `<a class="btn btn-primary" href="${job.href}" target="_blank" style="margin-left:6px">在 BOSS 打开 →</a>` : ''}

    <div class="modal-jd" style="margin-top:16px">${escapeHtml(job.jd || '暂无 JD')}</div>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeJobDetail()">关闭</button>
    </div>
  `;

  // 复用 modal-interview 的容器
  const modal = document.getElementById('modal-interview');
  modal.querySelector('.modal').innerHTML = html;
  modal.classList.add('active');
  modal.dataset.detail = '1';
}

function closeJobDetail() {
  const modal = document.getElementById('modal-interview');
  modal.classList.remove('active');
  modal.dataset.detail = '';
  // 如果是详情 modal，下次打开 add interview 时需要重置 modal 内容
  setTimeout(() => {
    if (!modal.dataset.detail) {
      modal.querySelector('.modal').innerHTML = ORIGINAL_MODAL_HTML;
    }
  }, 200);
}

window.setIntentById = (id, intent) => {
  const job = findJobById(id);
  if (job) { setIntent(job, intent); openJobDetail(id); render(); }
};

window.setPipelineColById = (id, col) => {
  const job = findJobById(id);
  if (job) { setPipelineCol(job, col); openJobDetail(id); render(); }
};

window.openJobDetail = openJobDetail;
window.closeJobDetail = closeJobDetail;

// ═══════════════════════════════════════════════════════════════
// 添加面试 Modal
// ═══════════════════════════════════════════════════════════════

let editingJobId = null;

function addInterviewById(id) {
  const modal = document.getElementById('modal-interview');
  // 重置为原始 modal 内容
  modal.querySelector('.modal').innerHTML = ORIGINAL_MODAL_HTML;
  modal.dataset.detail = '';

  const job = findJobById(id);
  if (job) {
    document.getElementById('modal-job-info').innerHTML = `
      <div style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
        ${escapeHtml(job.title)} · ${escapeHtml(job.company || '')}
      </div>
    `;
  }

  editingJobId = id;
  document.getElementById('iv-time').value = '';
  document.getElementById('iv-location').value = '';
  document.getElementById('iv-result').value = 'pending';
  modal.classList.add('active');
}

function closeModal() {
  const modal = document.getElementById('modal-interview');
  modal.classList.remove('active');
  modal.dataset.detail = '';
  editingJobId = null;
}

function saveInterview() {
  const time = document.getElementById('iv-time').value;
  if (!time) { showToast('请选择时间'); return; }
  const iv = {
    type: document.getElementById('iv-type').value,
    time: new Date(time).toISOString(),
    location: document.getElementById('iv-location').value,
    result: document.getElementById('iv-result').value,
  };
  const job = findJobById(editingJobId);
  if (job) {
    addInterview(job, iv);
    showToast('✓ 面试已添加');
  }
  closeModal();
  render();
}

window.addInterviewById = addInterviewById;
window.closeModal = closeModal;
window.saveInterview = saveInterview;

// ═══════════════════════════════════════════════════════════════
// 视图：训练场 (Training Ground)
// ═══════════════════════════════════════════════════════════════

const PRESET_TOPICS = [
  // Go
  'Go 基础', 'Go 并发', 'Go 内存', 'Go GC', 'Go runtime', 'go-zero',
  // K8s
  'K8s 架构', 'K8s 调度', 'Informer', 'Operator/CRD', 'K8s 网络', 'CSI',
  // 云原生
  '容器原理', 'Docker', 'Helm', 'Service Mesh',
  // 分布式
  '分布式一致性', 'Raft/Paxos', '分布式锁', '分布式事务', 'CAP',
  // 系统设计
  '系统设计', '高并发', '高可用', '缓存设计', '限流熔断',
  // 数据库
  'MySQL', 'Redis', '索引', '事务',
  // 算法
  '数据结构', '动态规划', '树/图',
  // GPU/AI
  'GPU 调度', 'CUDA', '推理优化', '训练框架', '大模型',
  // 项目/软
  '项目深挖', '架构演进', 'HR/行为面',
];

// ─── 独立题库 storage ───
const TRAINING_KEY = 'training_v1';
const AI_ANSWER_CACHE_KEY = 'training_ai_answers_v1';
const RESUME_DRILL_KEY = 'training_resume_drill_v1';
const TRAINING_UI_KEY = 'training_ui_v1';

function loadAnswerCache() {
  try { return JSON.parse(localStorage.getItem(AI_ANSWER_CACHE_KEY) || '{}'); }
  catch (e) { return {}; }
}

function saveAnswerCache(cache) {
  try { localStorage.setItem(AI_ANSWER_CACHE_KEY, JSON.stringify(cache)); }
  catch (e) {}
}

function saveAnswerToCache(qid, field, answer, mode) {
  const c = loadAnswerCache();
  c[qid] = c[qid] || {};
  c[qid][field] = answer;
  c[qid].lastAnswerMode = mode;
  c[qid].updatedAt = new Date().toISOString();
  saveAnswerCache(c);
}

function loadResumeDrill() {
  try { return JSON.parse(localStorage.getItem(RESUME_DRILL_KEY) || '{"resumeText":"","drill":null}'); }
  catch (e) { return { resumeText: '', drill: null }; }
}

function saveResumeDrill(v) {
  try { localStorage.setItem(RESUME_DRILL_KEY, JSON.stringify(v)); }
  catch (e) {}
}

function loadTrainingUi() {
  try {
    return JSON.parse(localStorage.getItem(TRAINING_UI_KEY) || '{"mode":"lite","questionLimit":8,"bankQuery":"","bankOnlyWeak":false,"bankSort":"recent"}');
  } catch (e) {
    return { mode: 'lite', questionLimit: 8, bankQuery: '', bankOnlyWeak: false, bankSort: 'recent' };
  }
}

function saveTrainingUi(patch) {
  const cur = loadTrainingUi();
  const next = { ...cur, ...patch };
  localStorage.setItem(TRAINING_UI_KEY, JSON.stringify(next));
  return next;
}

function normalizeQuestion(q) {
  return {
    id: q.id || ('q_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)),
    text: q.text || q.q || '',
    topics: Array.isArray(q.topics) ? q.topics : [],
    rating: q.rating || null,
    reviewNote: q.reviewNote || '',
    source: q.source || 'manual',
    createdAt: q.createdAt || new Date().toISOString(),
    reviewCount: Number.isFinite(q.reviewCount) ? q.reviewCount : 0,
    lastReviewedAt: q.lastReviewedAt || null,
    nextReviewAt: q.nextReviewAt || null,
    note: q.note || '',
    actionItems: Array.isArray(q.actionItems) ? q.actionItems : [],
    nextQuestion: q.nextQuestion || '',
    speakingLogs: Array.isArray(q.speakingLogs) ? q.speakingLogs : [],
    answer: q.answer || null,
    bestPracticeAnswer: q.bestPracticeAnswer || null,
    followupAnswer: q.followupAnswer || null,
    lastAnswerMode: q.lastAnswerMode || 'default',
    decomposition: q.decomposition || null,
    parentId: q.parentId || null,
    relationReason: q.relationReason || '',
    conversation: Array.isArray(q.conversation) ? q.conversation : [],
  };
}

function loadTraining() {
  try {
    const t = JSON.parse(localStorage.getItem(TRAINING_KEY) || '{"questions":[]}');
    t.questions = (t.questions || []).map(normalizeQuestion);
    const cache = loadAnswerCache();
    (t.questions || []).forEach(q => {
      const c = cache[q.id];
      if (!c) return;
      q.answer = q.answer || c.answer || null;
      q.bestPracticeAnswer = q.bestPracticeAnswer || c.bestPracticeAnswer || null;
      q.followupAnswer = q.followupAnswer || c.followupAnswer || null;
      q.lastAnswerMode = q.lastAnswerMode || c.lastAnswerMode || q.lastAnswerMode;
    });
    return t;
  }
  catch (e) { return { questions: [] }; }
}

function saveTraining(t) {
  try {
    const next = { ...t, questions: (t.questions || []).map(normalizeQuestion) };
    localStorage.setItem(TRAINING_KEY, JSON.stringify(next));
  }
  catch (e) { showToast('保存失败'); }
}

function addStandaloneQuestion(q) {
  const t = loadTraining();
  t.questions.push({
    id: 'q_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
    text: q.text,
    topics: q.topics,
    rating: q.rating,
    reviewNote: q.reviewNote || '',
    source: 'manual',
    createdAt: new Date().toISOString(),
    reviewCount: 0,
    lastReviewedAt: null,
    nextReviewAt: null,
    note: '',
    actionItems: [],
    nextQuestion: '',
    speakingLogs: [],
    answer: null,
    conversation: [],
  });
  saveTraining(t);
}

// ─── AI 设置 ───
const SETTINGS_KEY = 'training_settings_v1';
const ASR_SETTINGS_KEY = 'training_asr_settings_v1';

const AI_PROVIDERS = {
  deepseek: { name: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  openai: { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  kimi: { name: 'Kimi (月之暗面)', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  glm: { name: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  hpcai_prod: { name: 'HPC-AI MaaS (Prod)', baseUrl: 'https://api.hpc-ai.com/inference/v1', model: 'moonshotai/kimi-k2.5' },
  hpcai_dev: { name: 'HPC-AI MaaS (Dev)', baseUrl: 'http://dev-maas.internal:31006/v1', model: 'moonshotai/kimi-k2.5' },
  custom: { name: '自定义 (OpenAI 兼容)', baseUrl: '', model: '' },
};

function loadSettings() {
  try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'); }
  catch (e) { return {}; }
}

function saveSettings(s) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}

function loadAsrSettings() {
  try { return JSON.parse(localStorage.getItem(ASR_SETTINGS_KEY) || '{}'); }
  catch (e) { return {}; }
}

function saveAsrSettings(s) {
  localStorage.setItem(ASR_SETTINGS_KEY, JSON.stringify(s));
}

function hasAIConfig() {
  const llm = getLlmConfig();
  return llm.apiKey && llm.baseUrl && llm.model;
}

function getLlmConfig() {
  const s = loadSettings();
  const llm = s.llm || {};
  return {
    bffUrl: llm.bffUrl || s.bffUrl || '',
    baseUrl: llm.baseUrl || s.baseUrl || '',
    model: llm.model || s.model || '',
    apiKey: llm.apiKey || s.apiKey || '',
    extraHeaders: llm.extraHeaders || s.extraHeaders || '',
    stream: llm.stream !== undefined ? llm.stream : (s.stream !== false),
  };
}

function getAsrConfig() {
  const s = loadAsrSettings();
  const asr = s.asr || {};
  return {
    transport: asr.transport || s.transport || 'websocket',
    wsUrl: asr.wsUrl || s.wsUrl || '',
    apiAppId: asr.apiAppId || s.apiAppId || '',
    apiAccessKey: asr.apiAccessKey || s.apiAccessKey || '',
    apiResourceId: asr.apiResourceId || s.apiResourceId || 'volc.speech.dialog',
    apiAppKey: asr.apiAppKey || s.apiAppKey || 'PlgvMymc7f3tQnJ6',
    connectId: asr.connectId || s.connectId || '',
    language: asr.language || s.language || 'zh',
  };
}

function buildTargetFromSettings() {
  const s = getLlmConfig();
  return {
    base_url: String(s.baseUrl).replace(/\/$/, ''),
    model: s.model,
    api_key: s.apiKey,
    extra_headers: s.extraHeaders,
  };
}

function getBffBaseUrl() {
  const manual = String(getLlmConfig().bffUrl || '').replace(/\/$/, '');
  if (manual) return manual;
  // 若页面由 BFF 托管，默认回源到同源 BFF
  if (location && /^http:\/\/localhost:8891/.test(location.origin)) return location.origin;
  if (location && /^http:\/\/127\.0\.0\.1:8891/.test(location.origin)) return location.origin;
  return '';
}

const DEFAULT_PROMPT = `你是一个资深面试官 + 教练。请帮我准确解答这道面试题：

【题目】
{question}

【要求】
1. 先给一个简洁的核心答案（2-3 句）
2. 然后展开讲背后的原理和实现细节
3. 列出常见的追问和陷阱
4. 用中文回答，markdown 格式

直接给答案，不要寒暄。`;

const BEST_PRACTICE_PROMPT = `你是资深面试官和一线架构师。请围绕这道题给出“可落地的最佳实践”：

【题目】
{question}

【输出要求】
1. 先给 3 句内结论（面试可直接说）
2. 给出生产环境最佳实践清单（不少于 6 条，必须具体）
3. 给出常见反模式/坑点（不少于 4 条）
4. 给出排查与观测建议（日志、指标、Tracing、压测）
5. 给出 trade-off：性能/复杂度/成本/稳定性
6. 最后给出“继续学习路线”：关键词 + 官方文档入口（可用通用权威站点）

要求：中文、markdown、务实，不要空话。`;

const FOLLOWUP_PROMPT = `你是严格但友好的技术面试官。基于题目生成“模拟追问”：

【题目】
{question}

【输出要求】
1. 生成 8 个递进式追问（从基础到深入）
2. 每个追问后给“考察点”
3. 每个追问再给“高质量回答要点（2-4条）”
4. 最后给一个 5 分制评分 rubric（维度+分档）

要求：中文、markdown，贴近一线后端/云原生面试。`;

const DECOMPOSE_PROMPT = `你是资深技术教练。请把这道题按第一性原理拆解成“可训练的题目图谱”。

【原题】
{question}

【返回格式】
只返回 JSON（不要 markdown，不要代码块），结构如下：
{
  "first_principles": ["...","..."],
  "sub_questions": [
    { "text": "...", "why": "...", "topics": ["..."] }
  ],
  "related_questions": ["..."],
  "learning_path": ["..."]
}

【要求】
1. sub_questions 产出 4-8 个，可独立训练，且难度递进
2. 每个子题要有 why（为什么练这个）
3. topics 给 1-3 个技能点
4. related_questions 给 3-6 个横向关联题
5. learning_path 给 4-8 步（从基础到实战）`;

const RESUME_DRILL_PROMPT = `你是顶级面试官。请基于这份简历做“无死角拷打”清单，目标是暴露所有薄弱点。

【简历】
{resume}

【输出要求】
只输出 JSON（不要 markdown）：
{
  "dimensions": [
    {
      "name": "项目深挖",
      "why": "为什么要拷打这个维度",
      "questions": [
        { "q": "问题", "intent": "考察点", "bar": "及格回答标准" }
      ]
    }
  ],
  "red_flags": ["潜在风险点"],
  "must_prepare": ["必须补齐的知识点"]
}

要求：
1) dimensions 至少 6 个（项目深挖/原理/场景/性能/故障/协作表达等）
2) 每个维度 4-6 问题，问题要尖锐具体
3) 必须覆盖“简历写了但可能答不深”的部分`;

const SPEAKING_FEEDBACK_PROMPT = `你是资深技术面试官。请根据候选人的口述回答给出专业点评。

【题目】
{question}

【候选人口述转写】
{transcript}

【输出要求】
1) 先给一个总分（1-5）
2) 然后分四项点评：结构、准确性、深度、表达
3) 明确指出 3 个可执行改进点
4) 给一个“30秒版本示例开场”

请用中文，简洁务实。`;

async function askAI(prompt, onChunk) {
  const s = getLlmConfig();
  if (!s.apiKey) throw new Error('请先在设置里配置 AI');
  const bffBase = getBffBaseUrl();

  if (bffBase) {
    let res;
    try {
      res = await fetch(`${bffBase}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target: buildTargetFromSettings(),
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.5,
        }),
      });
    } catch (e) {
      throw new Error(`BFF chat 网络失败: ${e.message || e}`);
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`BFF ${res.status}: ${err.slice(0, 200)}`);
    }
    const data = await res.json().catch(() => ({}));
    const text = data.output_text || '';
    if (!text) throw new Error('BFF 返回为空');
    onChunk(text);
    return text;
  }

  // 解析自定义 headers
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${s.apiKey}`,
  };
  if (s.extraHeaders) {
    s.extraHeaders.split('\n').forEach(line => {
      const idx = line.indexOf(':');
      if (idx > 0) {
        const k = line.slice(0, idx).trim();
        const v = line.slice(idx + 1).trim();
        if (k && v) headers[k] = v;
      }
    });
  }

  const preferStream = s.stream !== false;
  const res = await fetch(`${s.baseUrl}/chat/completions`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: s.model,
      messages: [{ role: 'user', content: prompt }],
      stream: preferStream,
      temperature: 0.5,
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API ${res.status}: ${errText.slice(0, 200)}`);
  }

  // 兼容: 某些 OpenAI 兼容端点会忽略 stream=true，直接返回 JSON
  const contentType = (res.headers.get('content-type') || '').toLowerCase();
  if (!contentType.includes('text/event-stream')) {
    const data = await res.json().catch(() => ({}));
    const text = data.choices?.[0]?.message?.content || data.output_text || '';
    if (!text) throw new Error('接口返回成功但没有可解析的文本内容');
    onChunk(text);
    return text;
  }

  // 解析 SSE 流
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let full = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (data === '[DONE]') continue;
      try {
        const j = JSON.parse(data);
        const delta = j.choices?.[0]?.delta?.content;
        if (delta) {
          full += delta;
          onChunk(full);
        }
      } catch (e) {}
    }
  }
  return full;
}

function getPromptByMode(mode, questionText) {
  if (mode === 'best_practice') return BEST_PRACTICE_PROMPT.replace('{question}', questionText);
  if (mode === 'followup') return FOLLOWUP_PROMPT.replace('{question}', questionText);
  return DEFAULT_PROMPT.replace('{question}', questionText);
}

function getAnswerFieldByMode(mode) {
  if (mode === 'best_practice') return 'bestPracticeAnswer';
  if (mode === 'followup') return 'followupAnswer';
  return 'answer';
}

function getModeLabel(mode) {
  if (mode === 'decompose') return '拆题图谱';
  if (mode === 'best_practice') return '最佳实践';
  if (mode === 'followup') return '模拟追问';
  return '标准答案';
}

function parseJsonFromText(raw) {
  if (!raw) return null;
  const s = raw.trim();
  try { return JSON.parse(s); } catch (e) {}
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  if (fenced) {
    try { return JSON.parse(fenced[1]); } catch (e) {}
  }
  const start = s.indexOf('{');
  const end = s.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try { return JSON.parse(s.slice(start, end + 1)); } catch (e) {}
  }
  return null;
}

async function askAIForQuestion(qid, regenerate = false, mode = 'default') {
  const t = loadTraining();
  const q = t.questions.find(x => x.id === qid);
  if (!q) return;
  const field = getAnswerFieldByMode(mode);
  const existing = q[field];

  if (existing && !regenerate) {
    // 已有答案，直接展开
    toggleAnswerExpanded(qid);
    return;
  }

  if (!hasAIConfig()) {
    if (confirm('还没配置 AI，去设置？')) openSettings();
    return;
  }

  // 在 UI 上显示流式生成
  expandedAnswers.add(qid);
  render();
  await new Promise(r => setTimeout(r, 50));

  const answerEl = document.getElementById(`answer-body-${qid}`);
  if (!answerEl) return;
  answerEl.innerHTML = `<div style="color:var(--text-soft)">⏳ AI 正在生成「${getModeLabel(mode)}」...</div>`;

  const prompt = getPromptByMode(mode, q.text);

  try {
    const answer = await askAI(prompt, (partial) => {
      answerEl.textContent = partial;
    });
    // 保存答案
    const t2 = loadTraining();
    const q2 = t2.questions.find(x => x.id === qid);
    if (q2) {
      q2[field] = answer;
      q2.lastAnswerMode = mode;
      q2.answerSource = 'ai';
      saveTraining(t2);
      saveAnswerToCache(qid, field, answer, mode);
    }
    showToast(`✓ ${getModeLabel(mode)}已保存`);
    render();
  } catch (e) {
    answerEl.innerHTML = `<div style="color:var(--danger)">✗ ${escapeHtml(e.message)}</div>`;
  }
}

let expandedAnswers = new Set();

function toggleAnswerExpanded(qid) {
  if (expandedAnswers.has(qid)) expandedAnswers.delete(qid);
  else expandedAnswers.add(qid);
  render();
}

function regenerateAnswer(qid) {
  if (!confirm('重新生成答案？将覆盖现有内容')) return;
  const t = loadTraining();
  const q = t.questions.find(x => x.id === qid);
  if (!q) return;
  const mode = q.lastAnswerMode || 'default';
  const field = getAnswerFieldByMode(mode);
  q[field] = null;
  saveTraining(t);
  askAIForQuestion(qid, true, mode);
}

window.askAIForQuestion = askAIForQuestion;
window.toggleAnswerExpanded = toggleAnswerExpanded;
window.regenerateAnswer = regenerateAnswer;

async function decomposeQuestionByAI(qid) {
  const t = loadTraining();
  const q = t.questions.find(x => x.id === qid);
  if (!q) return;
  if (!hasAIConfig()) {
    if (confirm('还没配置 AI，去设置？')) openSettings();
    return;
  }
  showToast('🧩 正在拆题...');
  const prompt = DECOMPOSE_PROMPT.replace('{question}', q.text || q.q || '');
  try {
    const out = await askAI(prompt, () => {});
    const parsed = parseJsonFromText(out);
    if (!parsed || !Array.isArray(parsed.sub_questions)) {
      throw new Error('AI 返回无法解析为图谱 JSON');
    }

    const now = new Date().toISOString();
    q.decomposition = {
      firstPrinciples: Array.isArray(parsed.first_principles) ? parsed.first_principles : [],
      relatedQuestions: Array.isArray(parsed.related_questions) ? parsed.related_questions : [],
      learningPath: Array.isArray(parsed.learning_path) ? parsed.learning_path : [],
      updatedAt: now,
    };
    q.decomposeRaw = out;
    q.updatedAt = now;

    const existingTexts = new Set(t.questions.map(item => (item.text || '').trim()));
    let created = 0;
    (parsed.sub_questions || []).forEach((sq) => {
      const text = (sq?.text || '').trim();
      if (!text || existingTexts.has(text)) return;
      t.questions.push({
        id: 'q_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
        text,
        topics: Array.isArray(sq?.topics) && sq.topics.length > 0 ? sq.topics : inferTopics(text),
        rating: null,
        reviewNote: sq?.why || '',
        source: 'derived',
        parentId: qid,
        relationReason: sq?.why || '',
        createdAt: now,
        reviewCount: 0,
        lastReviewedAt: null,
        nextReviewAt: null,
        speakingLogs: [],
        answer: null,
        conversation: [],
      });
      existingTexts.add(text);
      created += 1;
    });

    saveTraining(t);
    showToast(`✓ 拆题完成，新增 ${created} 道子题`);
    render();
  } catch (e) {
    showToast('✗ 拆题失败: ' + String(e.message || e).slice(0, 80));
  }
}

window.decomposeQuestionByAI = decomposeQuestionByAI;

function updateStandaloneQuestion(id, patch) {
  const t = loadTraining();
  const i = t.questions.findIndex(q => q.id === id);
  if (i >= 0) {
    t.questions[i] = { ...t.questions[i], ...patch, updatedAt: new Date().toISOString() };
    saveTraining(t);
  }
}

function getReviewIntervalDays(rating, reviewCount) {
  if (rating === 'bad') return 1;
  if (rating === 'ok') return reviewCount >= 5 ? 5 : 3;
  if (rating === 'good') {
    if (reviewCount >= 6) return 21;
    if (reviewCount >= 3) return 7;
    return 3;
  }
  return 2;
}

function getDueStandaloneQuestions() {
  const now = Date.now();
  return loadTraining().questions
    .filter(q => {
      if (!q.nextReviewAt) return true;
      const ts = new Date(q.nextReviewAt).getTime();
      return Number.isFinite(ts) && ts <= now;
    })
    .sort((a, b) => {
      const ta = a.nextReviewAt ? new Date(a.nextReviewAt).getTime() : 0;
      const tb = b.nextReviewAt ? new Date(b.nextReviewAt).getTime() : 0;
      return ta - tb;
    });
}

function reviewStandaloneQuestion(id, rating) {
  const t = loadTraining();
  const q = t.questions.find(x => x.id === id);
  if (!q) return;
  const reviewedAt = new Date();
  const reviewCount = (q.reviewCount || 0) + 1;
  const intervalDays = getReviewIntervalDays(rating, reviewCount);
  const next = new Date(reviewedAt.getTime() + intervalDays * 86400000);
  Object.assign(q, {
    rating,
    reviewCount,
    lastReviewedAt: reviewedAt.toISOString(),
    nextReviewAt: next.toISOString(),
    updatedAt: reviewedAt.toISOString(),
  });
  saveTraining(t);
}

function deleteStandaloneQuestion(id) {
  const t = loadTraining();
  t.questions = t.questions.filter(q => q.id !== id);
  saveTraining(t);
}

function aggregateTopics() {
  const store = loadStore();
  const topics = {}; // { topicName: { good, ok, bad, total, questions } }

  function addQ(q, source, ctx) {
    (q.topics || ['未分类']).forEach(t => {
      if (!topics[t]) topics[t] = { good: 0, ok: 0, bad: 0, none: 0, total: 0, questions: [] };
      topics[t].total++;
      if (q.rating === 'good') topics[t].good++;
      else if (q.rating === 'ok') topics[t].ok++;
      else if (q.rating === 'bad') topics[t].bad++;
      else topics[t].none++;
      topics[t].questions.push({ ...q, source, ...ctx });
    });
  }

  // 1. 面试题（来自 store.interviews.questions）
  Object.entries(store).forEach(([id, st]) => {
    if (!st.interviews) return;
    const job = findJobById(id);
    st.interviews.forEach((iv, ivIdx) => {
      (iv.questions || []).forEach(q => {
        addQ(q, 'interview', {
          jobId: id,
          jobTitle: job ? job.title : '?',
          company: job ? job.company : '?',
          interviewType: iv.type,
          interviewIdx: ivIdx,
        });
      });
    });
  });

  // 2. 自学题（独立题库）
  loadTraining().questions.forEach(q => {
    addQ({ q: q.text, ...q }, 'manual', {});
  });

  // 计算分数（只算有 rating 的）
  Object.values(topics).forEach(t => {
    const rated = t.good + t.ok + t.bad;
    t.score = rated > 0 ? (t.good + t.ok * 0.5) / rated : 0;
    t.rated = rated;
  });

  return topics;
}

function getAllReflections() {
  const store = loadStore();
  const reflections = [];
  Object.entries(store).forEach(([id, st]) => {
    if (!st.interviews) return;
    const job = findJobById(id);
    if (!job) return;
    st.interviews.forEach((iv, idx) => {
      if (iv.questions && iv.questions.length > 0 || iv.reflection) {
        const counts = { good: 0, ok: 0, bad: 0 };
        (iv.questions || []).forEach(q => { if (counts[q.rating] !== undefined) counts[q.rating]++; });
        reflections.push({ jobId: id, job, iv, ivIdx: idx, counts });
      }
    });
  });
  reflections.sort((a, b) => new Date(b.iv.time) - new Date(a.iv.time));
  return reflections;
}

let trainingTopicFilter = null;
let trainingUi = loadTrainingUi();
let trainingQuestionLimit = trainingUi.questionLimit || 8;
let trainingMode = trainingUi.mode || 'lite';
let trainingBankQuery = trainingUi.bankQuery || '';
let trainingBankOnlyWeak = !!trainingUi.bankOnlyWeak;
let trainingBankSort = trainingUi.bankSort || 'recent';

function showMoreTrainingQuestions() {
  trainingQuestionLimit += 8;
  saveTrainingUi({ questionLimit: trainingQuestionLimit });
  render();
}

function collapseTrainingQuestions() {
  trainingQuestionLimit = 8;
  saveTrainingUi({ questionLimit: trainingQuestionLimit });
  render();
}

async function generateResumeDrill() {
  const textarea = document.getElementById('resume-drill-input');
  if (!textarea) return;
  const resumeText = textarea.value.trim();
  if (!resumeText) return showToast('请先粘贴简历内容');
  if (!hasAIConfig()) {
    if (confirm('还没配置 AI，去设置？')) openSettings();
    return;
  }
  showToast('🧠 正在生成拷打清单...');
  const prompt = RESUME_DRILL_PROMPT.replace('{resume}', resumeText.slice(0, 12000));
  try {
    const out = await askAI(prompt, () => {});
    const parsed = parseJsonFromText(out);
    if (!parsed || !Array.isArray(parsed.dimensions)) throw new Error('返回格式无效');
    saveResumeDrill({ resumeText, drill: parsed, updatedAt: new Date().toISOString() });
    showToast('✓ 无死角拷打清单已生成');
    render();
  } catch (e) {
    showToast('✗ 生成失败: ' + String(e.message || e).slice(0, 80));
  }
}

function renderResumeDrillSection() {
  const rd = loadResumeDrill();
  return `
    <div class="training-section">
      <h3>🎯 简历无死角拷打</h3>
      <textarea id="resume-drill-input" rows="6" placeholder="粘贴你的简历（项目经历/技术栈/职责/指标）..." style="font-size:12px;margin-bottom:8px">${escapeHtml(rd.resumeText || '')}</textarea>
      <div style="display:flex;gap:6px;justify-content:flex-end;margin-bottom:10px">
        <button class="qbtn" onclick="generateResumeDrill()">⚔ 生成拷打清单</button>
      </div>
      ${rd.drill ? `
        <div class="q-item">
          <div class="q-text">重点风险</div>
          <div class="q-topics">${(rd.drill.red_flags || []).slice(0, 8).map(x => `<span class="q-topic-chip">${escapeHtml(x)}</span>`).join('')}</div>
        </div>
        ${(rd.drill.dimensions || []).slice(0, 8).map(d => `
          <div class="q-item">
            <div class="q-text">${escapeHtml(d.name || '维度')}</div>
            <div class="q-review">${escapeHtml(d.why || '')}</div>
            <div style="font-size:12px;margin-top:6px;line-height:1.7">
              ${(d.questions || []).slice(0, 5).map((q, i) => `
                <div style="padding:3px 0;border-bottom:1px dashed var(--border)">
                  <strong>Q${i + 1}：</strong>${escapeHtml(q.q || '')}<br>
                  <span style="color:var(--text-muted)">考察：${escapeHtml(q.intent || '')}</span><br>
                  <span style="color:var(--text-muted)">及格线：${escapeHtml(q.bar || '')}</span>
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      ` : `<div class="empty" style="padding:20px 12px"><p>还没生成拷打清单</p></div>`}
    </div>
  `;
}

function getTrainingHubState(standalone, dueStandalone) {
  const parentCount = standalone.filter(q => !q.parentId).length;
  const childCount = standalone.filter(q => !!q.parentId).length;
  const withNotes = standalone.filter(q => (q.note || '').trim().length > 0).length;
  const withActions = standalone.filter(q => (q.actionItems || []).length > 0).length;
  const pendingActions = standalone.reduce((sum, q) => sum + (q.actionItems || []).length, 0);
  const weak = standalone.filter(q => q.rating === 'bad').length;
  const mid = standalone.filter(q => q.rating === 'ok').length;
  const graphCoverage = parentCount > 0 ? Math.round((childCount / parentCount) * 100) : 0;

  const mostUrgentDue = dueStandalone[0] || null;
  let nextAction = { label: '补充题库', hint: '先新增 5 道核心题', action: 'openAddQuestion()' };
  if (mostUrgentDue) {
    nextAction = { label: '先做今日训练', hint: `优先复习：${(mostUrgentDue.text || '').slice(0, 24)}${(mostUrgentDue.text || '').length > 24 ? '...' : ''}`, action: "scrollToDueSection()" };
  } else if (weak > 0 || mid > 0) {
    nextAction = { label: '专项强化弱项', hint: '从技能熟练度最低的主题开始', action: "document.querySelector('.heatmap-row')?.click()" };
  } else if (standalone.some(q => !q.parentId && !q.decomposition)) {
    nextAction = { label: '构建知识图谱', hint: '给关键母题执行一次拆题', action: "focusFirstUndecomposed()" };
  }

  return { parentCount, childCount, withNotes, withActions, pendingActions, weak, mid, graphCoverage, nextAction };
}

function renderTrainingHub(standalone, dueStandalone) {
  const s = getTrainingHubState(standalone, dueStandalone);
  return `
    <div class="training-section">
      <h3>🧭 训练中枢（采集 → 拆解 → 训练 → 复盘 → 行动）</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:12px">
        <div class="q-item"><div class="q-text">母题 ${s.parentCount}</div><div class="q-review">知识主干</div></div>
        <div class="q-item"><div class="q-text">子题 ${s.childCount}</div><div class="q-review">可训练颗粒</div></div>
        <div class="q-item"><div class="q-text">图谱覆盖 ${s.graphCoverage}%</div><div class="q-review">子题/母题比</div></div>
        <div class="q-item"><div class="q-text">今日待练 ${dueStandalone.length}</div><div class="q-review">间隔复习入口</div></div>
        <div class="q-item"><div class="q-text">笔记题目 ${s.withNotes}</div><div class="q-review">已沉淀思考</div></div>
        <div class="q-item"><div class="q-text">行动项 ${s.pendingActions}</div><div class="q-review">待执行任务</div></div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:var(--bg-subtle);border:1px solid var(--border);border-radius:8px;padding:10px 12px">
        <strong style="font-size:12px">下一步建议：</strong>
        <span style="font-size:12px">${s.nextAction.label}</span>
        <span style="font-size:11px;color:var(--text-muted)">${s.nextAction.hint}</span>
        <button class="qbtn" style="margin-left:auto" onclick="${s.nextAction.action}">执行 →</button>
      </div>
    </div>
  `;
}

function focusFirstUndecomposed() {
  const t = loadTraining();
  const q = t.questions.find(x => !x.parentId && !x.decomposition);
  if (!q) return showToast('所有母题都已拆解');
  focusQuestion(q.id);
  showToast('已定位到待拆题母题');
}

function renderTraining() {
  if (trainingMode === 'lite') return renderTrainingLite();
  const topics = aggregateTopics();
  const sortedTopics = Object.entries(topics).sort((a, b) => a[1].score - b[1].score);
  const reflections = getAllReflections();
  const standalone = loadTraining().questions;

  const totalQuestions = Object.values(topics).reduce((s, t) => s + t.total, 0);
  const weakTopics = sortedTopics.filter(([k, t]) => t.score < 0.5 && t.rated >= 1).length;
  const strongTopics = sortedTopics.filter(([k, t]) => t.score >= 0.8 && t.rated >= 1).length;
  const unrated = Object.values(topics).reduce((s, t) => s + (t.none || 0), 0);
  const dueStandalone = getDueStandaloneQuestions();

  const aiOk = hasAIConfig();
  const header = `
    <div class="training-header">
      <h2>🥋 训练场</h2>
      <span class="sub">题库 + 弱点定位 · AI 解答 · 不依赖面试</span>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-secondary" onclick="scrollToDueSection()">🎯 今日训练 ${dueStandalone.length > 0 ? '(' + dueStandalone.length + ')' : ''}</button>
        <button class="btn btn-secondary" onclick="openSettings()">⚙ ${aiOk ? 'AI 已配置' : '配置 AI'}</button>
        <button class="btn btn-secondary" onclick="openBulkImport()">📋 批量粘贴</button>
        <button class="btn btn-primary" onclick="openAddQuestion()">+ 单条添加</button>
      </div>
    </div>
  `;

  if (totalQuestions === 0) {
    return header + `
      <div class="empty">
        <div class="icon">📝</div>
        <h3>题库还是空的</h3>
        <p>开始建立你的个人题库——可以点「+ 添加题目」录入八股、刷题，或在 Pipeline 中复盘面试题</p>
        <button class="btn btn-primary" style="margin-top:14px" onclick="openAddQuestion()">+ 添加第一题</button>
      </div>
    `;
  }

  return header + `
    <div class="training-stats">
      <div class="tstat-card">
        <div class="tstat-num">${totalQuestions}</div>
        <div class="tstat-label">题库总数</div>
      </div>
      <div class="tstat-card">
        <div class="tstat-num">${Object.keys(topics).length}</div>
        <div class="tstat-label">涉及技能</div>
      </div>
      <div class="tstat-card warning">
        <div class="tstat-num">${weakTopics}</div>
        <div class="tstat-label">弱点</div>
      </div>
      <div class="tstat-card">
        <div class="tstat-num">${strongTopics}</div>
        <div class="tstat-label">已掌握</div>
      </div>
      ${unrated > 0 ? `<div class="tstat-card"><div class="tstat-num">${unrated}</div><div class="tstat-label">待练习</div></div>` : ''}
      <div class="tstat-card">
        <div class="tstat-num">${dueStandalone.length}</div>
        <div class="tstat-label">今日应复习</div>
      </div>
    </div>

    ${renderTrainingHub(standalone, dueStandalone)}
    ${renderResumeDrillSection()}
    ${renderSpeakingReviewSection()}

    <div class="training-section" id="due-training-section">
      <h3>🎯 今日训练队列（间隔复习）</h3>
      ${dueStandalone.length === 0 ? `
        <div class="empty" style="padding:24px 12px">
          <p>今天没有到期题目，做得很好</p>
        </div>
      ` : dueStandalone.slice(0, 20).map(q => `
        <div class="q-item rating-${q.rating || 'none'}">
          <div class="q-text">${escapeHtml(q.text || '')}</div>
          <div class="q-topics">${(q.topics || []).map(t => `<span class="q-topic-chip">${escapeHtml(t)}</span>`).join('')}</div>
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:6px">
            <span class="q-rating ${q.rating || 'none'}">已复习 ${q.reviewCount || 0} 次</span>
            <span style="margin-left:auto;display:flex;gap:4px">
              <button class="qbtn" onclick="reviewDueQuestion('${escapeAttr(q.id)}','good')" title="这次会了">✓ 会</button>
              <button class="qbtn" onclick="reviewDueQuestion('${escapeAttr(q.id)}','ok')" title="一般">🟡 一般</button>
              <button class="qbtn danger" onclick="reviewDueQuestion('${escapeAttr(q.id)}','bad')" title="不会">✗ 不会</button>
            </span>
          </div>
        </div>
      `).join('')}
      ${dueStandalone.length > 20 ? `<div style="font-size:12px;color:var(--text-muted);padding-top:6px">仅展示前 20 道，剩余 ${dueStandalone.length - 20} 道</div>` : ''}
    </div>

    ${renderQuestionGraph(standalone)}

    <div class="training-section">
      <h3>📊 技能熟练度（弱点优先）</h3>
      ${sortedTopics.length === 0 ? '<div class="empty"><p>还没有数据</p></div>' :
        sortedTopics.map(([name, t]) => {
          const cls = t.rated === 0 ? 'mid' : t.score < 0.5 ? 'weak' : t.score < 0.8 ? 'mid' : 'good';
          const pct = t.rated > 0 ? Math.round(t.score * 100) : 0;
          return `
            <div class="heatmap-row ${cls}" onclick="filterByTopic('${escapeAttr(name)}')">
              <div class="hr-name">${escapeHtml(name)}</div>
              <div class="hr-bar-wrap"><div class="hr-bar" style="width:${pct}%"></div></div>
              <div class="hr-stat">${t.good}✓ / ${t.ok}🟡 / ${t.bad}✗${t.none ? ' / ' + t.none + '?' : ''}</div>
              <div class="hr-score">${t.rated > 0 ? pct + '%' : '-'}</div>
            </div>
          `;
        }).join('')}
    </div>

    ${trainingTopicFilter ? `
      <div class="training-section">
        <h3>🎯 「${escapeHtml(trainingTopicFilter)}」 题目 <button class="btn btn-secondary" onclick="filterByTopic(null)" style="margin-left:auto;font-size:11px;padding:4px 10px">清除筛选</button></h3>
        ${(topics[trainingTopicFilter]?.questions || []).map(q => renderQuestionCard(q)).join('')}
      </div>
    ` : `
      <div class="training-section">
        <h3>📚 个人题库 (${standalone.length})</h3>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
          <input type="text" placeholder="搜索题目/标签" value="${escapeHtml(trainingBankQuery)}" oninput="setTrainingBankQuery(this.value)" style="max-width:260px">
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted)">
            <input type="checkbox" ${trainingBankOnlyWeak ? 'checked' : ''} onchange="setTrainingBankOnlyWeak(this.checked)" style="width:auto;margin:0">
            仅看薄弱题
          </label>
          <select onchange="setTrainingBankSort(this.value)" style="width:auto">
            <option value="recent" ${trainingBankSort === 'recent' ? 'selected' : ''}>按最近新增</option>
            <option value="due" ${trainingBankSort === 'due' ? 'selected' : ''}>按复习优先</option>
          </select>
        </div>
        ${standalone.length === 0 ? `
          <div class="empty">
            <p>还没有自学题目</p>
            <button class="btn btn-primary" style="margin-top:10px" onclick="openAddQuestion()">+ 添加题目</button>
          </div>
        ` : getFilteredStandaloneQuestions(standalone).slice(0, trainingQuestionLimit).map(q => renderQuestionCard({ ...q, q: q.text })).join('') + `
          <div style="display:flex;justify-content:center;gap:8px;padding-top:8px">
            ${getFilteredStandaloneQuestions(standalone).length > trainingQuestionLimit ? `<button class="qbtn" onclick="showMoreTrainingQuestions()">加载更多 (+8)</button>` : ''}
            ${trainingQuestionLimit > 8 ? `<button class="qbtn" onclick="collapseTrainingQuestions()">收起</button>` : ''}
          </div>
        `
        }
      </div>

      ${reflections.length > 0 ? `
        <div class="training-section">
          <h3>📝 面试复盘 (${reflections.length})</h3>
          ${reflections.slice(0, 10).map(({ jobId: id, job, iv, ivIdx, counts }) => `
            <div class="reflection-card" onclick="openReflectionModal('${escapeAttr(id)}', ${ivIdx})">
              <div class="rc-head">
                <div class="rc-title">${escapeHtml(iv.type)} · ${escapeHtml(job.title)}</div>
              </div>
              <div class="rc-meta">🏢 ${escapeHtml(job.company || '')} · 📅 ${fmtDate(iv.time)} · 共 ${(iv.questions || []).length} 题</div>
              <div class="rc-q-summary" style="margin-top:6px">
                ${counts.good > 0 ? `<span class="good">${counts.good} ✓</span>` : ''}
                ${counts.ok > 0 ? `<span class="ok">${counts.ok} 🟡</span>` : ''}
                ${counts.bad > 0 ? `<span class="bad">${counts.bad} ✗</span>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      ` : ''}
    `}
  `;
}

function renderQuestionCardLite(q) {
  const activeMode = q.lastAnswerMode || 'default';
  const activeField = getAnswerFieldByMode(activeMode);
  const hasAnswer = q[activeField] && q[activeField].length > 0;
  const lastSpeak = (q.speakingLogs || []).slice(-1)[0];
  return `
    <div class="q-item">
      <div class="q-text">${escapeHtml(q.text || q.q || '')}</div>
      <div class="q-topics">${(q.topics || []).slice(0, 4).map(t => `<span class="q-topic-chip">${escapeHtml(t)}</span>`).join('')}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px">
        <button class="qbtn" onclick="startSpeakingDrill('${escapeAttr(q.id)}')">🎤 口述</button>
        <button class="qbtn" onclick="askAIForQuestion('${escapeAttr(q.id)}', true, 'followup')">🥊 追问</button>
        <button class="qbtn" onclick="askAIForQuestion('${escapeAttr(q.id)}', true, 'best_practice')">🧭 最佳实践</button>
        <button class="qbtn" onclick="rateStandalone('${escapeAttr(q.id)}','good')">✓ 会</button>
        <button class="qbtn" onclick="rateStandalone('${escapeAttr(q.id)}','ok')">🟡</button>
        <button class="qbtn danger" onclick="rateStandalone('${escapeAttr(q.id)}','bad')">✗</button>
      </div>
      <div id="speak-panel-${q.id}" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>
      <textarea id="note-${q.id}" rows="2" placeholder="复盘：我答得最差的点是什么？下次怎么改？" style="font-size:12px;margin-top:8px">${escapeHtml(q.note || '')}</textarea>
      <div style="display:flex;gap:6px;justify-content:flex-end;margin-top:6px">
        <button class="qbtn" onclick="saveQuestionNote('${escapeAttr(q.id)}')">💾 保存复盘</button>
      </div>
      ${lastSpeak ? `<div class="q-review">最近口述：${escapeHtml(fmtDate(lastSpeak.at))} · ${lastSpeak.speakSec || 0}s · AI评分 ${escapeHtml(lastSpeak.aiScore || '-')}</div>` : ''}
      ${hasAnswer ? `
        <div class="q-answer" style="margin-top:8px">
          <div class="q-answer-header">
            <span>📖 ${getModeLabel(activeMode)}</span>
            <button class="qbtn small" onclick="toggleAnswerExpanded('${escapeAttr(q.id)}')">${expandedAnswers.has(q.id) ? '收起' : '展开'}</button>
          </div>
          ${expandedAnswers.has(q.id) ? `<div class="q-answer-body" id="answer-body-${q.id}">${escapeHtml(q[activeField] || '')}</div>` : ''}
        </div>
      ` : ''}
    </div>
  `;
}

function renderTrainingLite() {
  const standalone = loadTraining().questions.filter(q => q.source === 'manual' || q.source === 'derived');
  const due = getDueStandaloneQuestions();
  const weak = standalone.filter(q => q.rating === 'bad').length;
  const actions = standalone.reduce((s, q) => s + ((q.actionItems || []).length), 0);
  const focusList = (due.length > 0 ? due : standalone).slice(0, 6);

  return `
    <div class="training-header">
      <h2>🥋 能力训练（Lite）</h2>
      <span class="sub">只保留主链路：口述 → 追问 → 复盘</span>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-secondary" onclick="switchTrainingMode()">切换到完整模式</button>
        <button class="btn btn-secondary" onclick="openSettings()">⚙ AI 设置</button>
      </div>
    </div>

    <div class="training-stats">
      <div class="tstat-card"><div class="tstat-num">${due.length}</div><div class="tstat-label">今日优先训练</div></div>
      <div class="tstat-card warning"><div class="tstat-num">${weak}</div><div class="tstat-label">薄弱题目</div></div>
      <div class="tstat-card"><div class="tstat-num">${actions}</div><div class="tstat-label">待执行行动项</div></div>
    </div>

    ${renderResumeDrillSection()}
    ${renderSpeakingReviewSection()}

    <div class="training-section">
      <h3>🎯 今日训练清单（最多 6 题）</h3>
      ${focusList.length === 0 ? `
        <div class="empty" style="padding:24px 12px">
          <p>先添加题目或生成简历拷打清单</p>
          <button class="btn btn-primary" style="margin-top:8px" onclick="openAddQuestion()">+ 添加题目</button>
        </div>
      ` : focusList.map(q => renderQuestionCardLite(q)).join('')}
    </div>
  `;
}

function renderSpeakingReviewSection() {
  const all = loadTraining().questions;
  const logs = [];
  all.forEach(q => {
    (q.speakingLogs || []).forEach(log => logs.push({ q, log }));
  });
  logs.sort((a, b) => new Date(b.log.at) - new Date(a.log.at));
  return `
    <div class="training-section">
      <h3>🗂 口述复盘记录</h3>
      ${logs.length === 0 ? `<div class="empty" style="padding:18px 12px"><p>还没有口述记录</p></div>` : logs.slice(0, 20).map(({ q, log }) => `
        <div class="q-item">
          <div class="q-text">${escapeHtml((q.text || '').slice(0, 80))}</div>
          <div class="q-review">🕒 ${escapeHtml(fmtDate(log.at))} · ${log.speakSec || 0}s · AI评分 ${escapeHtml(log.aiScore || '-')}</div>
          ${log.aiFeedback ? `<div class="q-answer"><div class="q-answer-body">${escapeHtml(log.aiFeedback)}</div></div>` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function getFilteredStandaloneQuestions(list) {
  let arr = [...list];
  const q = (trainingBankQuery || '').trim().toLowerCase();
  if (q) {
    arr = arr.filter(item => {
      const text = String(item.text || '').toLowerCase();
      const topics = (item.topics || []).join(' ').toLowerCase();
      return text.includes(q) || topics.includes(q);
    });
  }
  if (trainingBankOnlyWeak) arr = arr.filter(item => item.rating === 'bad' || item.rating === 'ok');
  if (trainingBankSort === 'due') {
    arr.sort((a, b) => {
      const ta = a.nextReviewAt ? new Date(a.nextReviewAt).getTime() : Number.MAX_SAFE_INTEGER;
      const tb = b.nextReviewAt ? new Date(b.nextReviewAt).getTime() : Number.MAX_SAFE_INTEGER;
      return ta - tb;
    });
  } else {
    arr.sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
  }
  return arr;
}

function setTrainingBankQuery(v) {
  trainingBankQuery = v;
  saveTrainingUi({ bankQuery: v });
  render();
}

function setTrainingBankOnlyWeak(v) {
  trainingBankOnlyWeak = !!v;
  saveTrainingUi({ bankOnlyWeak: trainingBankOnlyWeak });
  render();
}

function setTrainingBankSort(v) {
  trainingBankSort = v;
  saveTrainingUi({ bankSort: v });
  render();
}

function switchTrainingMode() {
  trainingMode = trainingMode === 'lite' ? 'full' : 'lite';
  saveTrainingUi({ mode: trainingMode });
  showToast(trainingMode === 'lite' ? '已切换到 Lite 模式' : '已切换到完整模式');
  render();
}

function renderQuestionCard(q) {
  const ratingLabel = q.rating === 'good' ? '✓ 会' : q.rating === 'ok' ? '🟡 一般' : q.rating === 'bad' ? '✗ 不会' : '· 待练';
  const sourceTag = q.source === 'manual'
    ? `<span style="background:#e0e7ff;color:#4338ca;padding:1px 7px;border-radius:8px;font-size:10px;font-weight:700">📚 自学</span>`
    : q.source === 'derived'
      ? `<span style="background:#dcfce7;color:#166534;padding:1px 7px;border-radius:8px;font-size:10px;font-weight:700">🧩 子题</span>`
      : `<span style="background:#fef3c7;color:#92400e;padding:1px 7px;border-radius:8px;font-size:10px;font-weight:700">🏢 ${escapeHtml(q.company || '面试')}${q.interviewType ? ' · ' + escapeHtml(q.interviewType) : ''}</span>`;

  const canTrainWithAI = (q.source === 'manual' || q.source === 'derived') && q.id;
  const activeMode = q.lastAnswerMode || 'default';
  const activeField = getAnswerFieldByMode(activeMode);
  const hasAnswer = q[activeField] && q[activeField].length > 0;
  const isExpanded = expandedAnswers.has(q.id);

  return `
    <div class="q-item rating-${q.rating || 'none'}">
      <div class="q-text">${escapeHtml(q.q || q.text || '')}</div>
      <div class="q-topics">${(q.topics || []).map(t => `<span class="q-topic-chip">${escapeHtml(t)}</span>`).join('')}</div>
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:4px">
        <span class="q-rating ${q.rating || 'none'}">${ratingLabel}</span>
        ${sourceTag}
        ${canTrainWithAI ? `
          <button class="btn-ai ${hasAnswer ? 'has-answer' : ''}" onclick="askAIForQuestion('${escapeAttr(q.id)}', false, 'default')">
            ${hasAnswer ? (isExpanded ? '📖 收起答案' : '📖 看答案') : '💡 AI 解答'}
          </button>
          <button class="qbtn" onclick="askAIForQuestion('${escapeAttr(q.id)}', true, 'best_practice')" title="最佳实践清单">🧭 最佳实践</button>
          <button class="qbtn" onclick="askAIForQuestion('${escapeAttr(q.id)}', true, 'followup')" title="模拟面试追问">🥊 模拟追问</button>
          <button class="qbtn" onclick="decomposeQuestionByAI('${escapeAttr(q.id)}')" title="第一性原理拆题">🧩 拆题</button>
          <span style="margin-left:auto;display:flex;gap:4px">
            <button class="qbtn" onclick="rateStandalone('${escapeAttr(q.id)}','good')" title="会">✓</button>
            <button class="qbtn" onclick="rateStandalone('${escapeAttr(q.id)}','ok')" title="一般">🟡</button>
            <button class="qbtn" onclick="rateStandalone('${escapeAttr(q.id)}','bad')" title="不会">✗</button>
            <button class="qbtn danger" onclick="deleteStandalone('${escapeAttr(q.id)}')" title="删除">×</button>
          </span>
        ` : ''}
      </div>
      ${q.reviewNote ? `<div class="q-review">📌 ${escapeHtml(q.reviewNote)}</div>` : ''}
      ${q.source === 'derived' && q.parentId ? `<div class="q-review">🔗 来自上层题拆解</div>` : ''}
      ${q.decomposition ? `
        <div class="q-review">
          🧠 已生成图谱：${(q.decomposition.firstPrinciples || []).length} 条第一性原理 · ${(q.decomposition.learningPath || []).length} 步学习路径
        </div>
      ` : ''}

      ${canTrainWithAI ? `
        <div style="margin-top:10px;background:var(--bg-subtle);border:1px solid var(--border);border-radius:6px;padding:10px 12px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
            <strong style="font-size:12px">✍ 训练笔记</strong>
            <span style="font-size:11px;color:var(--text-soft)">记录你的理解、卡点和下一步</span>
          </div>
          <textarea id="note-${q.id}" rows="3" placeholder="今天这题我真正学到了什么？哪里还不稳？" style="font-size:12px;margin-bottom:8px">${escapeHtml(q.note || '')}</textarea>
          <input id="nextq-${q.id}" type="text" placeholder="下一道追问（可选），例如：如果 QPS 翻 10 倍怎么改？" value="${escapeHtml(q.nextQuestion || '')}" style="font-size:12px;margin-bottom:8px">
          <textarea id="actions-${q.id}" rows="2" placeholder="行动项（每行一条），例如：\n- 明天复盘 informer 原理\n- 周末手写一个简版缓存淘汰策略" style="font-size:12px;margin-bottom:8px">${escapeHtml((q.actionItems || []).join('\n'))}</textarea>
          <div style="display:flex;justify-content:flex-end">
            <button class="qbtn" onclick="saveQuestionNote('${escapeAttr(q.id)}')">💾 保存笔记</button>
          </div>
        </div>
      ` : ''}

      ${canTrainWithAI ? `
        <div style="margin-top:10px;background:var(--bg-elevated);border:1px dashed var(--border-strong);border-radius:6px;padding:10px 12px">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <strong style="font-size:12px">🎤 口语答题模式</strong>
            <span style="font-size:11px;color:var(--text-soft)">口述优先，训练表达链路</span>
            <span style="margin-left:auto"><button class="qbtn" onclick="startSpeakingDrill('${escapeAttr(q.id)}')">▶ 开始口述</button></span>
          </div>
          <div id="speak-panel-${q.id}" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>
          ${(q.speakingLogs || []).length > 0 ? `
            <div style="margin-top:8px;font-size:11px;color:var(--text-muted)">
              最近一次：${escapeHtml(fmtDate((q.speakingLogs || []).slice(-1)[0].at))} ·
              准备 ${(q.speakingLogs || []).slice(-1)[0].prepSec}s ·
              口述 ${(q.speakingLogs || []).slice(-1)[0].speakSec}s ·
              AI评分 ${(q.speakingLogs || []).slice(-1)[0].aiScore || '-'}${(q.speakingLogs || []).slice(-1)[0].hasAudio ? ' · 含录音' : ''}
            </div>
          ` : ''}
        </div>
      ` : ''}

      ${canTrainWithAI && (hasAnswer || isExpanded) ? `
        <div class="q-answer">
          <div class="q-answer-header">
            <span>📖 AI ${getModeLabel(activeMode)}</span>
            <button class="qbtn small" onclick="regenerateAnswer('${escapeAttr(q.id)}')">🔄 重新生成</button>
          </div>
          <div class="q-answer-body" id="answer-body-${q.id}">${escapeHtml(q[activeField] || '')}</div>
        </div>
      ` : ''}
    </div>
  `;
}

function saveQuestionNote(id) {
  const noteEl = document.getElementById(`note-${id}`);
  const nextEl = document.getElementById(`nextq-${id}`);
  const actionsEl = document.getElementById(`actions-${id}`);
  if (!noteEl || !nextEl || !actionsEl) return;
  const actionItems = actionsEl.value
    .split('\n')
    .map(x => x.replace(/^\s*[-*]\s*/, '').trim())
    .filter(Boolean);
  updateStandaloneQuestion(id, {
    note: noteEl.value.trim(),
    nextQuestion: nextEl.value.trim(),
    actionItems,
  });
  showToast('✓ 笔记已保存');
}

function saveSpeakingLog(qid, payload) {
  const t = loadTraining();
  const q = t.questions.find(x => x.id === qid);
  if (!q) return;
  q.speakingLogs = q.speakingLogs || [];
  q.speakingLogs.push({
    at: new Date().toISOString(),
    prepSec: payload.prepSec,
    speakSec: payload.speakSec,
    aiScore: payload.aiScore || '',
    aiFeedback: payload.aiFeedback || '',
    selfNotes: payload.selfNotes || '',
    transcript: payload.transcript || '',
    hasAudio: !!payload.hasAudio,
  });
  if (q.speakingLogs.length > 20) q.speakingLogs = q.speakingLogs.slice(-20);
  saveTraining(t);
}

function getSpeechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function stopSpeakingSession(qid) {
  window.__speaking = window.__speaking || {};
  const s = window.__speaking[qid];
  if (!s) return;
  try { if (s.prepTimer) clearTimeout(s.prepTimer); } catch (e) {}
  try { if (s.speakTimer) clearTimeout(s.speakTimer); } catch (e) {}
  try { if (s.recognition) s.recognition.stop(); } catch (e) {}
  try { if (s.mediaRecorder && s.mediaRecorder.state !== 'inactive') s.mediaRecorder.stop(); } catch (e) {}
  try {
    if (s.asrWs && s.asrWs.readyState === WebSocket.OPEN) {
      s.asrWs.send('__END__');
      s.asrWs.close();
    }
  } catch (e) {}
  try { if (s.pcmProcessor) s.pcmProcessor.disconnect(); } catch (e) {}
  try { if (s.pcmSource) s.pcmSource.disconnect(); } catch (e) {}
  try { if (s.pcmContext) s.pcmContext.close(); } catch (e) {}
  delete window.__speaking[qid];
}

async function buildAudioUrlFromSession(sess) {
  if (!sess || !sess.mediaRecorder) return '';
  if (sess.mediaRecorder.state !== 'inactive') {
    await new Promise((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };
      try {
        sess.mediaRecorder.addEventListener('stop', finish, { once: true });
        sess.mediaRecorder.stop();
      } catch (e) {
        finish();
      }
      setTimeout(finish, 1500);
    });
  }
  if (!sess.audioChunks || sess.audioChunks.length === 0) return '';
  try {
    const audioBlob = new Blob(sess.audioChunks, { type: 'audio/webm' });
    if (audioBlob.size <= 0) return '';
    sess.audioBlob = audioBlob;
    return URL.createObjectURL(audioBlob);
  } catch (e) {
    return '';
  }
}

async function transcribeWithAsr(audioBlob) {
  const cfg0 = getAsrConfig();
  if (cfg0.transport === 'websocket') return '';
  const bffBase = getBffBaseUrl();
  if (bffBase) {
    const s = getAsrConfig();
    const fd = new FormData();
    fd.append('file', audioBlob, 'speaking.webm');
    fd.append('model', s.model || 'whisper-1');
    if (s.language) fd.append('language', s.language);
    const headers = {
      'X-Target-Base-Url': String(s.baseUrl || '').replace(/\/$/, ''),
      'X-Target-Api-Key': s.apiKey || '',
      'X-Target-Extra-Headers': s.extraHeaders || '',
    };
    let res;
    try {
      res = await fetch(`${bffBase}/api/v1/asr/transcribe`, {
        method: 'POST',
        headers,
        body: fd,
      });
    } catch (e) {
      throw new Error(`BFF asr 网络失败: ${e.message || e}`);
    }
    if (!res.ok) throw new Error(`ASR-BFF ${res.status}`);
    const data = await res.json().catch(() => ({}));
    return (data.text || '').trim();
  }

  const s = getAsrConfig();
  if (!audioBlob || !s.baseUrl || !s.apiKey || !s.model) return '';
  const fd = new FormData();
  fd.append('file', audioBlob, 'speaking.webm');
  fd.append('model', s.model);
  if (s.language) fd.append('language', s.language);
  const headers = { Authorization: `Bearer ${s.apiKey}` };
  const res = await fetch(`${String(s.baseUrl).replace(/\/$/, '')}/audio/transcriptions`, {
    method: 'POST',
    headers,
    body: fd,
  });
  if (!res.ok) throw new Error(`ASR ${res.status}`);
  const data = await res.json().catch(() => ({}));
  return (data.text || '').trim();
}

async function getSharedMicStream() {
  window.__mic = window.__mic || { stream: null };
  if (window.__mic.stream && window.__mic.stream.active) return window.__mic.stream;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return null;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    window.__mic.stream = stream;
    return stream;
  } catch (e) {
    return null;
  }
}

function floatTo16BitPCM(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function startPcmStreamingToWs(sess, stream) {
  if (!sess || !sess.asrWs) return;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  const ctx = new AudioCtx({ sampleRate: 16000 });
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  proc.onaudioprocess = (e) => {
    if (!sess.asrWs || sess.asrWs.readyState !== WebSocket.OPEN) return;
    const ch = e.inputBuffer.getChannelData(0);
    const pcm16 = floatTo16BitPCM(ch);
    try { sess.asrWs.send(pcm16.buffer); } catch (err) {}
  };
  source.connect(proc);
  proc.connect(ctx.destination);
  sess.pcmContext = ctx;
  sess.pcmSource = source;
  sess.pcmProcessor = proc;
}

function buildVolcWsUrl(cfg) {
  const u = new URL(cfg.wsUrl);
  // 浏览器 WebSocket 无法自定义握手 Header，这里用 query 透传配置，供后端/网关桥接使用
  if (cfg.apiAppId) u.searchParams.set('x_api_app_id', cfg.apiAppId);
  if (cfg.apiAccessKey) u.searchParams.set('x_api_access_key', cfg.apiAccessKey);
  if (cfg.apiResourceId) u.searchParams.set('x_api_resource_id', cfg.apiResourceId);
  if (cfg.apiAppKey) u.searchParams.set('x_api_app_key', cfg.apiAppKey);
  if (cfg.connectId) u.searchParams.set('x_api_connect_id', cfg.connectId);
  return u.toString();
}

function tryExtractAsrTextFromWsPayload(payload) {
  if (!payload) return '';
  if (typeof payload === 'string') {
    try {
      const j = JSON.parse(payload);
      return j.text || j.result?.text || j.payload_msg?.result?.[0]?.text || '';
    } catch (e) {
      return '';
    }
  }
  return '';
}

function initAsrWebsocketIfNeeded(qid, sess, warnEl) {
  const cfg = getAsrConfig();
  if (cfg.transport !== 'websocket' || !cfg.wsUrl) return;
  const bffBase = getBffBaseUrl();
  if (!bffBase) {
    const w = warnEl();
    if (w) w.textContent = '未配置 BFF Base URL，WebSocket 桥接不可用';
    return;
  }
  try {
    const wsBridgeUrl = bffBase.replace(/^http/, 'ws') + '/api/v1/asr/ws';
    const ws = new WebSocket(wsBridgeUrl);
    ws.binaryType = 'arraybuffer';
    sess.asrWs = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'init', config: cfg }));
      const w = warnEl();
      if (w) w.textContent = 'ASR WebSocket 桥接已连接，开始实时转写';
    };
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const j = JSON.parse(event.data);
          if (j.type === 'bridge_open') {
            const w = warnEl();
            if (w) w.textContent = 'ASR 桥接已建立，等待语音...';
            return;
          }
          if (j.type === 'upstream_error' || j.type === 'bridge_error' || j.type === 'error') {
            const w = warnEl();
            if (w) w.textContent = `ASR错误: ${j.message || 'unknown'}`;
            return;
          }
          if (j.type === 'partial' && j.text) {
            sess.transcript = (sess.transcript || '') + j.text;
            const tEl = document.getElementById(`speak-transcript-${qid}`);
            if (tEl) tEl.value = sess.transcript;
            return;
          }
        } catch (e) {}
      }
      const text = tryExtractAsrTextFromWsPayload(event.data);
      if (!text) return;
      sess.transcript = (sess.transcript || '') + text;
      const tEl = document.getElementById(`speak-transcript-${qid}`);
      if (tEl) tEl.value = sess.transcript;
    };
    ws.onerror = () => {
      const w = warnEl();
      if (w) w.textContent = 'ASR WebSocket 桥接错误（检查 BFF 日志）';
    };
    ws.onclose = (evt) => {
      const w = warnEl();
      if (w) {
        const reason = evt && evt.reason ? evt.reason : 'no-reason';
        if (evt.code === 1000) {
          w.textContent = 'ASR WebSocket 正常关闭';
        } else {
          w.textContent = `ASR WebSocket 关闭 code=${evt.code} reason=${reason}`;
        }
      }
    };
  } catch (e) {
    const w = warnEl();
    if (w) w.textContent = `ASR WebSocket 初始化失败: ${e.message || e}`;
  }
}

async function probeAsrWebsocketConnection(cfg) {
  const bffBase = getBffBaseUrl();
  if (!bffBase) throw new Error('未配置 BFF Base URL');
  return await new Promise((resolve, reject) => {
    let done = false;
    const finish = (fn, val) => {
      if (done) return;
      done = true;
      fn(val);
    };
    try {
      const ws = new WebSocket(bffBase.replace(/^http/, 'ws') + '/api/v1/asr/ws');
      const timer = setTimeout(() => {
        try { ws.close(); } catch (e) {}
        finish(reject, new Error('WS 握手超时'));
      }, 4000);
      ws.onopen = () => {
        try { ws.send(JSON.stringify({ type: 'init', config: cfg })); } catch (e) {}
      };
      ws.onmessage = (evt) => {
        clearTimeout(timer);
        try { ws.close(); } catch (e) {}
        finish(resolve, true);
      };
      ws.onerror = () => {
        clearTimeout(timer);
        finish(reject, new Error('WS 握手失败（onerror）'));
      };
      ws.onclose = (evt) => {
        clearTimeout(timer);
        if (done) return;
        if (evt.code === 1000) finish(resolve, true);
        else finish(reject, new Error(`WS 关闭 code=${evt.code} reason=${evt.reason || 'no-reason'}`));
      };
    } catch (e) {
      finish(reject, e);
    }
  });
}

function startSpeakingDrill(qid) {
  const panel = document.getElementById(`speak-panel-${qid}`);
  if (!panel) return;
  stopSpeakingSession(qid);
  const startAt = Date.now();
  panel.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span>准备 30 秒后开始口述（建议脱稿）</span>
      <button class="qbtn" onclick="beginSpeakingPhase('${escapeAttr(qid)}', ${startAt})">立即开始</button>
      <button class="qbtn danger" onclick="cancelSpeakingDrill('${escapeAttr(qid)}')">取消</button>
    </div>
  `;
  window.__speaking = window.__speaking || {};
  window.__speaking[qid] = { startAt, transcript: '', audioChunks: [] };
  window.__speaking[qid].prepTimer = setTimeout(() => beginSpeakingPhase(qid, startAt), 30000);
}

function beginSpeakingPhase(qid, startAt) {
  const panel = document.getElementById(`speak-panel-${qid}`);
  if (!panel) return;
  window.__speaking = window.__speaking || {};
  const sess = window.__speaking[qid] || { startAt, transcript: '', audioChunks: [] };
  window.__speaking[qid] = sess;
  if (sess.stage === 'speaking') return;
  if (sess.prepTimer) clearTimeout(sess.prepTimer);
  sess.stage = 'speaking';
  const speakStart = Date.now();
  sess.speakStart = speakStart;

  const RecognitionCtor = getSpeechRecognitionCtor();
  const warnEl = () => document.getElementById(`speak-warn-${qid}`);
  const asrCfg = getAsrConfig();
  const preferWsAsr = asrCfg.transport === 'websocket' && !!asrCfg.wsUrl;
  if (!preferWsAsr && RecognitionCtor) {
    const rec = new RecognitionCtor();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    sess.keepRecognition = true;
    rec.onstart = () => {
      const w = warnEl();
      if (w) w.textContent = '语音识别已启动（实时转写中）';
    };
    rec.onresult = (event) => {
      let interim = '';
      let finalText = sess.transcript || '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const txt = event.results[i][0]?.transcript || '';
        if (event.results[i].isFinal) finalText += txt;
        else interim += txt;
      }
      sess.transcript = finalText;
      const tEl = document.getElementById(`speak-transcript-${qid}`);
      if (tEl) tEl.value = (finalText + interim).trim();
    };
    rec.onerror = (e) => {
      const w = warnEl();
      if (w) w.textContent = `语音识别错误: ${e.error || 'unknown'}`;
    };
    rec.onend = () => {
      const w = warnEl();
      if (sess.keepRecognition) {
        if (w) w.textContent = '语音识别中断，尝试重连...';
        try { rec.start(); } catch (e) {}
      } else if (w) {
        w.textContent = '语音识别已结束';
      }
    };
    try { rec.start(); sess.recognition = rec; }
    catch (e) {
      const w = warnEl();
      if (w) w.textContent = `语音识别启动失败: ${e.message || e}`;
    }
  } else if (!preferWsAsr) {
    const w = warnEl();
    if (w) w.textContent = '当前浏览器不支持 SpeechRecognition，无法实时转写';
  }

  if (preferWsAsr) {
    initAsrWebsocketIfNeeded(qid, sess, warnEl);
  }

  if (window.MediaRecorder) {
    getSharedMicStream().then(stream => {
      if (!stream) {
      const warn = warnEl();
      if (warn) warn.textContent = '无法获取麦克风权限，仅记录计时（可手动填转写）';
        return;
      }
      const mr = new MediaRecorder(stream);
      sess.mediaRecorder = mr;
      mr.ondataavailable = (e) => {
        if (!e.data || e.data.size <= 0) return;
        sess.audioChunks.push(e.data);
      };
      mr.start();
      if (preferWsAsr) {
        startPcmStreamingToWs(sess, stream);
      }
    });
  }

  panel.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
      <span>🎙 已开始口述（目标 2 分钟）</span>
      <button class="qbtn" onclick="finishSpeakingDrill('${escapeAttr(qid)}', ${startAt}, ${speakStart})">结束并自评</button>
    </div>
    <div id="speak-warn-${qid}" style="font-size:11px;color:var(--text-soft);margin-bottom:6px"></div>
    <textarea id="speak-transcript-${qid}" rows="4" placeholder="实时转写会显示在这里（支持浏览器语音识别时）" style="font-size:12px"></textarea>
  `;
  sess.speakTimer = setTimeout(() => finishSpeakingDrill(qid, startAt, speakStart), 120000);
}

async function finishSpeakingDrill(qid, startAt, speakStart) {
  const panel = document.getElementById(`speak-panel-${qid}`);
  if (!panel) return;
  const now = Date.now();
  const prepSec = Math.max(0, Math.round((speakStart - startAt) / 1000));
  const speakSec = Math.max(1, Math.round((now - speakStart) / 1000));
  const sess = (window.__speaking && window.__speaking[qid]) || {};
  sess.keepRecognition = false;
  try { if (sess.prepTimer) clearTimeout(sess.prepTimer); } catch (e) {}
  try { if (sess.speakTimer) clearTimeout(sess.speakTimer); } catch (e) {}
  try { if (sess.recognition) sess.recognition.stop(); } catch (e) {}
  const transcriptEl = document.getElementById(`speak-transcript-${qid}`);
  const transcript = (transcriptEl ? transcriptEl.value : (sess.transcript || '')).trim();
  const audioUrl = await buildAudioUrlFromSession(sess);
  const audioBlob = sess.audioBlob || null;
  window.__lastSpeakingAudio = window.__lastSpeakingAudio || {};
  window.__lastSpeakingAudio[qid] = audioBlob;
  stopSpeakingSession(qid);
  panel.innerHTML = `
    <div style="display:flex;gap:6px;flex-direction:column">
      <div>口述完成：请确认转写，然后用 AI 点评。</div>
      ${audioUrl ? `
        <div style="font-size:11px;color:var(--text-muted)">录音结果（临时）</div>
        <audio controls src="${audioUrl}" style="width:100%"></audio>
      ` : `<div style="font-size:11px;color:var(--text-soft)">未生成可回放音频（可能浏览器限制）</div>`}
      <textarea id="speak-final-transcript-${qid}" rows="5" placeholder="口述转写（可修改）" style="font-size:12px">${escapeHtml(transcript)}</textarea>
      <textarea id="speak-note-${qid}" rows="2" placeholder="补充备注（可选）..." style="font-size:12px"></textarea>
      <div style="display:flex;justify-content:flex-end;gap:6px">
        <button class="qbtn" onclick="saveSpeakingReview('${escapeAttr(qid)}', ${prepSec}, ${speakSec}, ${audioUrl ? 'true' : 'false'})">🤖 ASR+AI点评并保存</button>
      </div>
      <div id="speak-ai-${qid}" style="font-size:12px;color:var(--text-muted)"></div>
    </div>
  `;
}

function cancelSpeakingDrill(qid) {
  stopSpeakingSession(qid);
  const panel = document.getElementById(`speak-panel-${qid}`);
  if (panel) panel.innerHTML = '<span style="color:var(--text-soft)">已取消</span>';
}

async function saveSpeakingReview(qid, prepSec, speakSec, hasAudio = false) {
  const noteEl = document.getElementById(`speak-note-${qid}`);
  const transcriptEl = document.getElementById(`speak-final-transcript-${qid}`);
  let transcript = transcriptEl ? transcriptEl.value.trim() : '';
  const note = noteEl ? noteEl.value.trim() : '';
  let aiFeedback = '';
  let aiScore = '';

  const aiEl = document.getElementById(`speak-ai-${qid}`);
  if (aiEl) aiEl.textContent = 'AI 点评中...';

  const audioBlob = window.__lastSpeakingAudio ? window.__lastSpeakingAudio[qid] : null;
  if (audioBlob) {
    try {
      const asrText = await transcribeWithAsr(audioBlob);
      if (asrText) transcript = asrText;
    } catch (e) {
      // ASR 失败时回退到实时转写结果
    }
  }

  if (hasAIConfig() && transcript) {
    const t = loadTraining();
    const q = t.questions.find(x => x.id === qid);
    const questionText = q ? (q.text || q.q || '') : '';
    const p = SPEAKING_FEEDBACK_PROMPT
      .replace('{question}', questionText)
      .replace('{transcript}', transcript.slice(0, 8000));
    try {
      aiFeedback = await askAI(p, () => {});
      const m = aiFeedback.match(/总分[：:\s]*([1-5](?:\.\d)?)/);
      aiScore = m ? m[1] : '';
      if (aiEl) aiEl.textContent = 'AI 点评完成，已保存';
    } catch (e) {
      if (aiEl) aiEl.textContent = 'AI 点评失败，已保存基础记录';
    }
  } else if (aiEl) {
    aiEl.textContent = transcript ? '未配置 AI，已保存转写' : '无转写内容，已保存计时';
  }

  saveSpeakingLog(qid, {
    prepSec,
    speakSec,
    aiScore,
    aiFeedback,
    selfNotes: note,
    transcript,
    hasAudio,
  });
  if (window.__lastSpeakingAudio) delete window.__lastSpeakingAudio[qid];
  showToast(aiFeedback ? '✓ 已保存并完成 AI 点评' : '✓ 已保存口述记录');
  render();
}

function rateStandalone(id, rating) {
  reviewStandaloneQuestion(id, rating);
  showToast('✓ 已更新');
  render();
}

function deleteStandalone(id) {
  if (!confirm('删除这道题？')) return;
  deleteStandaloneQuestion(id);
  render();
}

window.rateStandalone = rateStandalone;
window.deleteStandalone = deleteStandalone;

function reviewDueQuestion(id, rating) {
  reviewStandaloneQuestion(id, rating);
  showToast('✓ 已记录，下次会自动安排');
  render();
}

function scrollToDueSection() {
  switchView('training');
  setTimeout(() => {
    const el = document.getElementById('due-training-section');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 0);
}

window.reviewDueQuestion = reviewDueQuestion;
window.scrollToDueSection = scrollToDueSection;
window.saveQuestionNote = saveQuestionNote;
window.focusFirstUndecomposed = focusFirstUndecomposed;
window.showMoreTrainingQuestions = showMoreTrainingQuestions;
window.collapseTrainingQuestions = collapseTrainingQuestions;
window.generateResumeDrill = generateResumeDrill;
window.switchTrainingMode = switchTrainingMode;
window.startSpeakingDrill = startSpeakingDrill;
window.beginSpeakingPhase = beginSpeakingPhase;
window.finishSpeakingDrill = finishSpeakingDrill;
window.cancelSpeakingDrill = cancelSpeakingDrill;
window.saveSpeakingReview = saveSpeakingReview;
window.setTrainingBankQuery = setTrainingBankQuery;
window.setTrainingBankOnlyWeak = setTrainingBankOnlyWeak;
window.setTrainingBankSort = setTrainingBankSort;

function filterByTopic(topic) {
  trainingTopicFilter = topic;
  render();
}

window.filterByTopic = filterByTopic;

function calcTopicOverlap(a, b) {
  const sa = new Set((a.topics || []).map(x => String(x).trim()).filter(Boolean));
  const sb = new Set((b.topics || []).map(x => String(x).trim()).filter(Boolean));
  let inter = 0;
  sa.forEach(x => { if (sb.has(x)) inter += 1; });
  return inter;
}

function getRelatedStandaloneQuestions(target, list, limit = 4) {
  return list
    .filter(q => q.id !== target.id)
    .map(q => {
      const overlap = calcTopicOverlap(target, q);
      const parentBoost = (q.parentId && q.parentId === target.id) || (target.parentId && target.parentId === q.id) ? 2 : 0;
      return { q, score: overlap + parentBoost };
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(x => x.q);
}

function focusQuestion(id) {
  const t = loadTraining();
  const q = t.questions.find(x => x.id === id);
  if (!q) return;
  expandedAnswers.add(id);
  trainingTopicFilter = null;
  render();
  setTimeout(() => {
    const el = document.getElementById(`answer-body-${id}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 0);
}

window.focusQuestion = focusQuestion;

function renderQuestionGraph(questions) {
  const parents = questions.filter(q => !q.parentId);
  if (parents.length === 0) return '';
  return `
    <div class="training-section">
      <h3>🧠 题目知识图谱（父题 → 子题）</h3>
      ${parents.slice(0, 12).map(p => {
        const children = questions.filter(x => x.parentId === p.id);
        const related = getRelatedStandaloneQuestions(p, questions, 3);
        if (children.length === 0 && related.length === 0) return '';
        return `
          <div class="q-item">
            <div class="q-text">${escapeHtml(p.text || '')}</div>
            ${children.length > 0 ? `
              <div style="font-size:12px;color:var(--text-muted);margin-top:6px">子题 (${children.length})</div>
              <div class="q-topics">
                ${children.slice(0, 6).map(c => `<span class="q-topic-chip" style="cursor:pointer" onclick="focusQuestion('${escapeAttr(c.id)}')">${escapeHtml((c.text || '').slice(0, 28))}${(c.text || '').length > 28 ? '...' : ''}</span>`).join('')}
              </div>
            ` : ''}
            ${related.length > 0 ? `
              <div style="font-size:12px;color:var(--text-muted);margin-top:6px">关联题</div>
              <div class="q-topics">
                ${related.map(r => `<span class="q-topic-chip" style="cursor:pointer" onclick="focusQuestion('${escapeAttr(r.id)}')">${escapeHtml((r.text || '').slice(0, 24))}${(r.text || '').length > 24 ? '...' : ''}</span>`).join('')}
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// 复盘录入 Modal
// ═══════════════════════════════════════════════════════════════

let reflectionJobId = null;
let reflectionIvIdx = null;
let reflectionDraft = null; // { reflection: '', questions: [{q, topics, rating, reviewNote}] }

function openReflectionModal(jobId, ivIdx) {
  const job = findJobById(jobId);
  if (!job) return;
  const st = getState(job);
  const iv = st.interviews && st.interviews[ivIdx];
  if (!iv) return;

  reflectionJobId = jobId;
  reflectionIvIdx = ivIdx;
  reflectionDraft = {
    reflection: iv.reflection || '',
    questions: JSON.parse(JSON.stringify(iv.questions || [])),
  };

  showReflectionModal(job, iv);
}

function showReflectionModal(job, iv) {
  const modal = document.getElementById('modal-interview');
  modal.querySelector('.modal').innerHTML = `
    <h3>📝 面试复盘</h3>
    <div style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
      ${escapeHtml(iv.type)} · ${escapeHtml(job.title)} · ${escapeHtml(job.company || '')} · ${fmtDate(iv.time)}
    </div>

    <label>总体反思（可选）</label>
    <textarea id="reflection-text" rows="2" placeholder="表现如何？有什么感悟？">${escapeHtml(reflectionDraft.reflection)}</textarea>

    <label>题目录入</label>
    <div id="q-list">${reflectionDraft.questions.map((q, i) => renderQRow(q, i)).join('')}</div>
    <button class="btn btn-secondary" onclick="addQuestion()" style="width:100%;margin-top:8px">+ 添加一道题</button>

    <div class="modal-actions" style="margin-top:18px">
      <button class="btn btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveReflection()">保存复盘</button>
    </div>
  `;
  modal.classList.add('active');
  modal.dataset.detail = 'reflection';
}

function renderQRow(q, idx) {
  return `
    <div class="q-row" data-idx="${idx}">
      <textarea placeholder="题目内容..." oninput="updateQ(${idx}, 'q', this.value)" rows="2">${escapeHtml(q.q || '')}</textarea>
      <div style="display:flex;gap:6px;align-items:center;font-size:11px;color:var(--text-muted);margin-bottom:6px">
        技能点：
        <input type="text" placeholder="自定义" oninput="updateQTopicsRaw(${idx}, this.value)" value="${escapeHtml((q.topics || []).join(', '))}" style="flex:1;padding:4px 8px;border-radius:4px;border:1px solid var(--border);font-size:11px">
      </div>
      <div class="topic-chip-bar">
        ${PRESET_TOPICS.map(t => `<span class="topic-chip ${(q.topics || []).includes(t) ? 'selected' : ''}" onclick="toggleTopic(${idx}, '${escapeAttr(t)}')">${t}</span>`).join('')}
      </div>
      <div class="rating-bar">
        <button class="rating-btn good ${q.rating === 'good' ? 'selected' : ''}" onclick="setRating(${idx}, 'good')">✓ 答得好</button>
        <button class="rating-btn ok ${q.rating === 'ok' ? 'selected' : ''}" onclick="setRating(${idx}, 'ok')">🟡 一般</button>
        <button class="rating-btn bad ${q.rating === 'bad' ? 'selected' : ''}" onclick="setRating(${idx}, 'bad')">✗ 不会</button>
        <button class="rating-btn" onclick="removeQ(${idx})" style="flex:0 0 auto;padding:6px 10px;color:var(--danger)">删除</button>
      </div>
      ${q.rating === 'bad' || q.rating === 'ok' ? `
        <input type="text" placeholder="📌 复习要点..." oninput="updateQ(${idx}, 'reviewNote', this.value)" value="${escapeHtml(q.reviewNote || '')}" style="margin-top:6px;width:100%;padding:6px 10px;border-radius:4px;border:1px solid var(--border);font-size:12px">
      ` : ''}
    </div>
  `;
}

function refreshQList() {
  document.getElementById('q-list').innerHTML = reflectionDraft.questions.map((q, i) => renderQRow(q, i)).join('');
}

function addQuestion() {
  reflectionDraft.questions.push({ q: '', topics: [], rating: null, reviewNote: '' });
  refreshQList();
}

function removeQ(idx) {
  reflectionDraft.questions.splice(idx, 1);
  refreshQList();
}

function updateQ(idx, field, value) {
  reflectionDraft.questions[idx][field] = value;
}

function updateQTopicsRaw(idx, raw) {
  // 把输入框的 raw text 解析成数组
  const arr = raw.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
  reflectionDraft.questions[idx].topics = arr;
  // 不刷新整个 list，会丢失输入焦点
}

function toggleTopic(idx, topic) {
  const cur = reflectionDraft.questions[idx].topics || [];
  if (cur.includes(topic)) {
    reflectionDraft.questions[idx].topics = cur.filter(t => t !== topic);
  } else {
    reflectionDraft.questions[idx].topics = [...cur, topic];
  }
  refreshQList();
}

function setRating(idx, rating) {
  reflectionDraft.questions[idx].rating = rating;
  refreshQList();
}

function saveReflection() {
  const job = findJobById(reflectionJobId);
  if (!job) return;
  const cur = getState(job);
  const reflectionTextEl = document.getElementById('reflection-text');
  const reflection = reflectionTextEl ? reflectionTextEl.value : '';
  cur.interviews[reflectionIvIdx] = {
    ...cur.interviews[reflectionIvIdx],
    questions: reflectionDraft.questions.filter(q => q.q && q.q.trim()),
    reflection,
  };
  setState(job, cur);
  showToast('✓ 复盘已保存');
  closeModal();
  render();
}

// ─── 添加自学题目 modal ───
let addQuestionDraft = { text: '', topics: [], rating: null, reviewNote: '' };

function openAddQuestion() {
  addQuestionDraft = { text: '', topics: [], rating: null, reviewNote: '' };
  showAddQuestionModal();
}

function showAddQuestionModal() {
  const modal = document.getElementById('modal-interview');
  modal.querySelector('.modal').innerHTML = `
    <h3>📚 添加题目</h3>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:14px">
      录入八股、刷题、技术问题... 不需要绑定面试
    </div>

    <label>题目内容</label>
    <textarea id="aq-text" rows="3" placeholder="例：K8s informer 的 list-watch 机制原理" oninput="addQuestionDraft.text = this.value">${escapeHtml(addQuestionDraft.text)}</textarea>

    <label>技能点（可多选）</label>
    <div class="topic-chip-bar" id="aq-topics">
      ${PRESET_TOPICS.map(t => `<span class="topic-chip ${addQuestionDraft.topics.includes(t) ? 'selected' : ''}" onclick="toggleAddTopic('${escapeAttr(t)}')">${t}</span>`).join('')}
    </div>
    <input type="text" placeholder="自定义技能点（用 , 分隔）" oninput="updateAddTopicsRaw(this.value)" value="${escapeHtml(addQuestionDraft.topics.filter(t => !PRESET_TOPICS.includes(t)).join(', '))}" style="margin-bottom:14px">

    <label>当前掌握程度</label>
    <div class="rating-bar" style="margin-bottom:14px">
      <button class="rating-btn good ${addQuestionDraft.rating === 'good' ? 'selected' : ''}" onclick="setAddRating('good')">✓ 会</button>
      <button class="rating-btn ok ${addQuestionDraft.rating === 'ok' ? 'selected' : ''}" onclick="setAddRating('ok')">🟡 一般</button>
      <button class="rating-btn bad ${addQuestionDraft.rating === 'bad' ? 'selected' : ''}" onclick="setAddRating('bad')">✗ 不会</button>
      <button class="rating-btn ${!addQuestionDraft.rating ? 'selected ok' : ''}" onclick="setAddRating(null)">· 待练</button>
    </div>

    <label>笔记 / 复习要点（可选）</label>
    <textarea id="aq-note" rows="2" placeholder="参考答案 / 待复习的点" oninput="addQuestionDraft.reviewNote = this.value">${escapeHtml(addQuestionDraft.reviewNote)}</textarea>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveAddQuestion()">保存</button>
    </div>
  `;
  modal.classList.add('active');
  modal.dataset.detail = 'add-q';
}

function toggleAddTopic(t) {
  if (addQuestionDraft.topics.includes(t)) {
    addQuestionDraft.topics = addQuestionDraft.topics.filter(x => x !== t);
  } else {
    addQuestionDraft.topics = [...addQuestionDraft.topics, t];
  }
  // 局部刷新 chips
  document.getElementById('aq-topics').innerHTML = PRESET_TOPICS.map(t2 =>
    `<span class="topic-chip ${addQuestionDraft.topics.includes(t2) ? 'selected' : ''}" onclick="toggleAddTopic('${escapeAttr(t2)}')">${t2}</span>`
  ).join('');
}

function updateAddTopicsRaw(raw) {
  const custom = raw.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean);
  // 保留预设的，加上自定义的
  const presetSelected = addQuestionDraft.topics.filter(t => PRESET_TOPICS.includes(t));
  addQuestionDraft.topics = [...presetSelected, ...custom];
}

function setAddRating(r) {
  addQuestionDraft.rating = r;
  // 重新渲染 rating bar
  document.querySelectorAll('#modal-interview .rating-btn').forEach(btn => btn.classList.remove('selected'));
  if (r === 'good') document.querySelector('#modal-interview .rating-btn.good').classList.add('selected');
  else if (r === 'ok') document.querySelector('#modal-interview .rating-btn.ok').classList.add('selected');
  else if (r === 'bad') document.querySelector('#modal-interview .rating-btn.bad').classList.add('selected');
  else document.querySelectorAll('#modal-interview .rating-btn')[3].classList.add('selected');
}

function saveAddQuestion() {
  const text = document.getElementById('aq-text').value.trim();
  if (!text) { showToast('请输入题目内容'); return; }
  addStandaloneQuestion({
    text,
    topics: addQuestionDraft.topics,
    rating: addQuestionDraft.rating,
    reviewNote: document.getElementById('aq-note').value.trim(),
  });
  showToast('✓ 已添加');
  closeModal();
  render();
}

// ─── 批量导入 ───

// 关键词 → 技能点 自动映射
const TOPIC_KEYWORDS = {
  'Go 基础': ['go ', 'golang', '语言', 'slice', 'map', 'interface', '反射', 'reflect'],
  'Go 并发': ['goroutine', 'channel', 'mutex', 'sync', 'waitgroup', 'context', '并发', '协程'],
  'Go 内存': ['内存', '逃逸', 'escape', 'heap', 'stack', '栈', '堆'],
  'Go GC': ['gc', '垃圾回收', '三色标记', '写屏障'],
  'Go runtime': ['runtime', 'gmp', 'gpm', '调度器', 'g0'],
  'go-zero': ['go-zero', 'gozero'],
  'K8s 架构': ['k8s', 'kubernetes', 'apiserver', 'etcd', 'kubelet', 'controller-manager', 'scheduler'],
  'K8s 调度': ['调度', 'scheduler', 'predicate', 'priority', 'preempt'],
  'Informer': ['informer', 'list-watch', 'reflector', 'delta fifo', 'workqueue'],
  'Operator/CRD': ['operator', 'crd', 'controller', 'reconcile', 'kubebuilder', 'finalizer'],
  'K8s 网络': ['cni', 'service', 'kube-proxy', 'iptables', 'ipvs', 'ingress', '网络'],
  'CSI': ['csi', 'pv', 'pvc', '存储卷', 'storageclass'],
  '容器原理': ['容器', 'cgroup', 'namespace', 'overlay', 'unionfs', 'rootfs'],
  'Docker': ['docker', 'dockerfile', '镜像'],
  'Helm': ['helm', 'chart'],
  'Service Mesh': ['istio', 'envoy', 'sidecar', 'service mesh', '服务网格'],
  '分布式一致性': ['一致性', '分布式', 'consistency', 'cap', 'base'],
  'Raft/Paxos': ['raft', 'paxos', '共识', 'leader 选举'],
  '分布式锁': ['分布式锁', 'redis 锁', 'zookeeper 锁', 'redlock'],
  '分布式事务': ['分布式事务', '2pc', '3pc', 'tcc', 'saga'],
  '系统设计': ['系统设计', '设计一个', '设计系统', '架构设计'],
  '高并发': ['高并发', 'qps', 'tps', '秒杀'],
  '高可用': ['高可用', 'ha', '容灾', '故障转移'],
  '缓存设计': ['缓存', 'cache', '穿透', '雪崩', '击穿'],
  '限流熔断': ['限流', '熔断', '降级', '令牌桶', '漏桶', 'sentinel', 'hystrix'],
  'MySQL': ['mysql', 'innodb', 'mvcc'],
  'Redis': ['redis', '哨兵', 'cluster', 'rdb', 'aof'],
  '索引': ['索引', 'index', 'b+树', 'btree'],
  '事务': ['事务', '隔离级别', 'acid'],
  '数据结构': ['数组', '链表', '栈', '队列', '哈希', '堆排序', '快排'],
  '动态规划': ['动态规划', 'dp', 'dynamic programming'],
  '树/图': ['二叉树', '前序', '中序', '后序', '图', 'bfs', 'dfs', '拓扑'],
  'GPU 调度': ['gpu', '算力', 'mig', 'vgpu', 'device plugin', 'volcano'],
  'CUDA': ['cuda', 'cudnn', 'kernel'],
  '推理优化': ['推理', 'inference', 'tensorrt', '量化', 'kv cache'],
  '训练框架': ['训练', 'training', 'pytorch', 'tensorflow', 'deepspeed', 'fsdp'],
  '大模型': ['llm', '大模型', 'transformer', 'attention', '微调', 'rlhf', 'sft'],
  'HR/行为面': ['职业规划', '为什么', '优点', '缺点', '冲突', '失败'],
};

function inferTopics(text) {
  const lower = text.toLowerCase();
  const matched = new Set();
  for (const [topic, keywords] of Object.entries(TOPIC_KEYWORDS)) {
    for (const kw of keywords) {
      if (lower.includes(kw.toLowerCase())) {
        matched.add(topic);
        break;
      }
    }
  }
  return [...matched];
}

let bulkImportRaw = '';
let bulkImportPreview = []; // [{text, topics}]
let bulkImportDefaultTopic = '';

function openBulkImport() {
  bulkImportRaw = '';
  bulkImportPreview = [];
  bulkImportDefaultTopic = '';
  showBulkImportModal();
}

function showBulkImportModal() {
  const modal = document.getElementById('modal-interview');
  modal.querySelector('.modal').innerHTML = `
    <h3>📋 批量导入题目</h3>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:14px">
      一行一道题，会自动从内容里识别技能点。空行和 Markdown 标题会被忽略。
    </div>

    <label>粘贴你的题目列表</label>
    <textarea id="bulk-text" rows="10" placeholder="K8s informer 的工作原理&#10;Go map 是线程安全的吗？&#10;设计一个 GPU 调度器&#10;Redis 缓存穿透怎么解决&#10;..." oninput="updateBulkPreview(this.value)" style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px"></textarea>

    <label>默认技能点（可选，作用于所有自动识别失败的题）</label>
    <div class="topic-chip-bar" id="bulk-topics">
      ${PRESET_TOPICS.map(t => `<span class="topic-chip" onclick="setBulkDefaultTopic('${escapeAttr(t)}')">${t}</span>`).join('')}
    </div>

    <div id="bulk-preview" style="margin-top:14px;font-size:12px;color:var(--text-muted)"></div>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="confirmBulkImport()" id="bulk-confirm" disabled>导入 0 道</button>
    </div>
  `;
  modal.classList.add('active');
  modal.dataset.detail = 'bulk';
}

function updateBulkPreview(raw) {
  bulkImportRaw = raw;
  // 解析：每行一题，去掉空行、纯 markdown 标题、bullet 前缀
  const lines = raw.split('\n')
    .map(l => l.trim())
    .filter(l => l && !l.match(/^#+\s/) && !l.match(/^---/))
    .map(l => l.replace(/^[\*\-\+•]\s*/, '').replace(/^\d+[\.、)]\s*/, '').trim())
    .filter(l => l.length >= 3);

  bulkImportPreview = lines.map(text => ({
    text,
    topics: inferTopics(text),
  }));

  const taggedCount = bulkImportPreview.filter(p => p.topics.length > 0).length;
  const untaggedCount = bulkImportPreview.length - taggedCount;

  document.getElementById('bulk-preview').innerHTML = bulkImportPreview.length === 0 ? '' : `
    <div style="background:var(--bg-subtle);padding:10px 14px;border-radius:6px">
      <strong>识别到 ${bulkImportPreview.length} 道题</strong> · 自动打标 ${taggedCount} 道${untaggedCount > 0 ? ` · ${untaggedCount} 道未识别` : ''}
      <div style="margin-top:8px;max-height:140px;overflow-y:auto">
        ${bulkImportPreview.slice(0, 30).map(p => `
          <div style="padding:3px 0;border-bottom:1px solid var(--border)">
            <span style="font-size:11px">${escapeHtml(p.text.slice(0, 60))}${p.text.length > 60 ? '...' : ''}</span>
            ${p.topics.length > 0
              ? p.topics.map(t => `<span style="font-size:9px;background:var(--primary-light);color:var(--primary-dark);padding:1px 6px;border-radius:6px;margin-left:4px;font-weight:700">${t}</span>`).join('')
              : `<span style="font-size:9px;color:var(--text-soft);margin-left:4px">未识别</span>`
            }
          </div>
        `).join('')}
        ${bulkImportPreview.length > 30 ? `<div style="font-size:11px;color:var(--text-soft);padding-top:4px">... 还有 ${bulkImportPreview.length - 30} 道</div>` : ''}
      </div>
    </div>
  `;

  const btn = document.getElementById('bulk-confirm');
  btn.textContent = `导入 ${bulkImportPreview.length} 道`;
  btn.disabled = bulkImportPreview.length === 0;
}

function setBulkDefaultTopic(t) {
  bulkImportDefaultTopic = bulkImportDefaultTopic === t ? '' : t;
  document.querySelectorAll('#bulk-topics .topic-chip').forEach(el => {
    el.classList.toggle('selected', el.textContent === bulkImportDefaultTopic);
  });
}

function confirmBulkImport() {
  if (bulkImportPreview.length === 0) return;
  bulkImportPreview.forEach(({ text, topics }) => {
    const finalTopics = topics.length > 0 ? topics : (bulkImportDefaultTopic ? [bulkImportDefaultTopic] : ['未分类']);
    addStandaloneQuestion({
      text,
      topics: finalTopics,
      rating: null, // 全部默认待练
      reviewNote: '',
    });
  });
  showToast(`✓ 已导入 ${bulkImportPreview.length} 道题`);
  closeModal();
  render();
}

// ─── 设置 modal ───

function openSettings() {
  const s = getLlmConfig();
  const asr = getAsrConfig();
  const modal = document.getElementById('modal-interview');
  modal.querySelector('.modal').innerHTML = `
    <h3>⚙ 模型配置</h3>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:14px">
      支持任何 OpenAI 兼容的 API。本地存储 API Key，不上传任何数据。
    </div>

    <div style="font-size:12px;font-weight:700;margin:8px 0 6px">文字大模型（LLM）</div>
    <label>提供商</label>
    <select id="set-provider" onchange="onProviderChange(this.value)">
      ${Object.entries(AI_PROVIDERS).map(([k, v]) => `<option value="${k}">${v.name}</option>`).join('')}
    </select>

    <label>BFF Base URL（推荐）</label>
    <input type="text" id="set-bffurl" value="${escapeHtml(s.bffUrl || '')}" placeholder="http://localhost:8891">

    <label>Base URL</label>
    <input type="text" id="set-baseurl" value="${escapeHtml(s.baseUrl || AI_PROVIDERS.deepseek.baseUrl)}">

    <label>Model</label>
    <input type="text" id="set-model" value="${escapeHtml(s.model || AI_PROVIDERS.deepseek.model)}">

    <label>API Key</label>
    <input type="password" id="set-apikey" value="${escapeHtml(s.apiKey || '')}" placeholder="sk-xxx 或 DevAccessToken">

    <label>额外 Headers（可选，每行 Key: Value）</label>
    <textarea id="set-headers" rows="3" placeholder="X-MaaS-Main-UID: your-user-id&#10;X-Resource: playground" style="font-family:'SF Mono',Menlo,monospace;font-size:11px">${escapeHtml(s.extraHeaders || '')}</textarea>

    <label style="display:flex;align-items:center;gap:8px;margin-top:-2px;margin-bottom:10px;text-transform:none;letter-spacing:0;font-weight:500">
      <input type="checkbox" id="set-stream" ${s.stream === false ? '' : 'checked'} style="width:auto;margin:0">
      优先使用流式输出（不兼容时可关闭）
    </label>

    <hr style="border:none;border-top:1px solid var(--border);margin:10px 0 12px">
    <div style="font-size:12px;font-weight:700;margin:8px 0 6px">语音转写（ASR 最小 Demo）</div>
    <div style="font-size:11px;color:var(--text-soft);margin-bottom:8px">先只支持 WebSocket 实时转写，确保链路跑通。</div>
    <label>ASR WebSocket URL</label>
    <input type="text" id="set-asr-wsurl" value="${escapeHtml(asr.wsUrl || '')}" placeholder="wss://...">
    <label>X-Api-App-ID（WebSocket）</label>
    <input type="text" id="set-asr-api-app-id" value="${escapeHtml(asr.apiAppId || '')}" placeholder="123456789">
    <label>X-Api-Access-Key（WebSocket）</label>
    <input type="password" id="set-asr-api-access-key" value="${escapeHtml(asr.apiAccessKey || '')}" placeholder="your-access-key">
    <label>X-Api-Resource-Id（WebSocket）</label>
    <input type="text" id="set-asr-api-resource-id" value="${escapeHtml(asr.apiResourceId || 'volc.speech.dialog')}" placeholder="volc.speech.dialog">
    <label>X-Api-App-Key（WebSocket）</label>
    <input type="text" id="set-asr-api-app-key" value="${escapeHtml(asr.apiAppKey || 'PlgvMymc7f3tQnJ6')}" placeholder="PlgvMymc7f3tQnJ6">
    <label>X-Api-Connect-Id（可选）</label>
    <input type="text" id="set-asr-connect-id" value="${escapeHtml(asr.connectId || '')}" placeholder="d1dcd999-...">
    <label>ASR 语言（可选）</label>
    <input type="text" id="set-asr-language" value="${escapeHtml(asr.language || 'zh')}" placeholder="zh / en">

    <div style="font-size:11px;color:var(--text-soft);margin-bottom:14px;background:var(--bg-subtle);padding:8px 12px;border-radius:6px">
      💡 提供商指南：<br>
      · <strong>DeepSeek</strong> - 最便宜，¥0.001/千 token<br>
      · <strong>HPC-AI MaaS (Prod)</strong> - 推荐模型可用 <code>moonshotai/kimi-k2.5</code><br>
      · <strong>HPC-AI MaaS (Dev)</strong> - API Key 用 DevAccessToken（浏览器 cookie 里复制）；<br>
      &nbsp;&nbsp;额外 Header 填 <code>X-MaaS-Main-UID: 你的用户ID</code><br>
      · <strong>目标：</strong>先让 WebSocket 实时转写稳定工作，再逐步加高级配置
    </div>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">取消</button>
      <button class="btn btn-secondary" onclick="testAI()">🧪 测试 LLM</button>
      <button class="btn btn-secondary" onclick="testAsr()">🎙 测试 ASR</button>
      <button class="btn btn-primary" onclick="saveAISettings()">保存</button>
    </div>
  `;
  modal.classList.add('active');
  modal.dataset.detail = 'settings';

  // 根据当前 baseUrl 选择 provider
  const provider = Object.entries(AI_PROVIDERS).find(([k, v]) => v.baseUrl === s.baseUrl);
  if (provider) document.getElementById('set-provider').value = provider[0];
}

function onProviderChange(key) {
  const p = AI_PROVIDERS[key];
  if (p && p.baseUrl) {
    document.getElementById('set-baseurl').value = p.baseUrl;
    document.getElementById('set-model').value = p.model;
    const streamEl = document.getElementById('set-stream');
    if (streamEl) streamEl.checked = key !== 'hpcai_dev';
  }
}

async function testAI() {
  const settings = {
    llm: {
      bffUrl: document.getElementById('set-bffurl').value.replace(/\/$/, ''),
      baseUrl: document.getElementById('set-baseurl').value.replace(/\/$/, ''),
      model: document.getElementById('set-model').value,
      apiKey: document.getElementById('set-apikey').value,
      extraHeaders: document.getElementById('set-headers').value,
      stream: document.getElementById('set-stream').checked,
    },
  };
  if (!settings.llm.apiKey) { showToast('请填 LLM API Key'); return; }
  saveSettings(settings);
  showToast('🧪 测试中...');
  try {
    const bff = getBffBaseUrl();
    if (bff) {
      const ping = await fetch(`${bff}/api/v1/diag/ping`).then(r => r.json());
      if (!ping.ok) throw new Error('BFF ping failed');
    }
    await askAI('用一句话回答：1+1=?', () => {});
    showToast('✓ 连接成功');
  } catch (e) {
    showToast('✗ ' + e.message.slice(0, 80));
  }
}

async function testAsr() {
  const asr = {
    asr: {
      transport: 'websocket',
      wsUrl: document.getElementById('set-asr-wsurl').value.replace(/\/$/, ''),
      apiAppId: document.getElementById('set-asr-api-app-id').value.trim(),
      apiAccessKey: document.getElementById('set-asr-api-access-key').value.trim(),
      apiResourceId: document.getElementById('set-asr-api-resource-id').value.trim(),
      apiAppKey: document.getElementById('set-asr-api-app-key').value.trim(),
      connectId: document.getElementById('set-asr-connect-id').value.trim(),
      language: document.getElementById('set-asr-language').value.trim(),
    },
  };
  saveAsrSettings(asr);
  const cfg = getAsrConfig();
  if (!cfg.wsUrl) return showToast('请填 ASR WebSocket URL');
  if (!cfg.apiAppId || !cfg.apiAccessKey || !cfg.apiResourceId || !cfg.apiAppKey) {
    return showToast('请填 X-Api-App-ID / Access-Key / Resource-Id / App-Key');
  }
  showToast('🎙 ASR 配置已保存，测试握手中...');
  try {
    await probeAsrWebsocketConnection(cfg);
    showToast('✓ ASR WebSocket 握手成功');
  } catch (e) {
    showToast('✗ ' + String(e.message || e).slice(0, 90));
  }
}

function saveAISettings() {
  const settings = {
    llm: {
      bffUrl: document.getElementById('set-bffurl').value.replace(/\/$/, ''),
      baseUrl: document.getElementById('set-baseurl').value.replace(/\/$/, ''),
      model: document.getElementById('set-model').value,
      apiKey: document.getElementById('set-apikey').value,
      extraHeaders: document.getElementById('set-headers').value,
      stream: document.getElementById('set-stream').checked,
    },
  };
  if (!settings.llm.apiKey || !settings.llm.baseUrl || !settings.llm.model) {
    showToast('请填完整 LLM 配置');
    return;
  }
  saveSettings(settings);
  const asrSettings = {
    asr: {
      transport: 'websocket',
      wsUrl: document.getElementById('set-asr-wsurl').value.replace(/\/$/, ''),
      apiAppId: document.getElementById('set-asr-api-app-id').value.trim(),
      apiAccessKey: document.getElementById('set-asr-api-access-key').value.trim(),
      apiResourceId: document.getElementById('set-asr-api-resource-id').value.trim(),
      apiAppKey: document.getElementById('set-asr-api-app-key').value.trim(),
      connectId: document.getElementById('set-asr-connect-id').value.trim(),
      language: document.getElementById('set-asr-language').value.trim(),
    },
  };
  if (
    !asrSettings.asr.wsUrl ||
    !asrSettings.asr.apiAppId ||
    !asrSettings.asr.apiAccessKey ||
    !asrSettings.asr.apiResourceId ||
    !asrSettings.asr.apiAppKey
  ) {
    showToast('请填 ASR WebSocket URL + X-Api-* 必填项');
    return;
  }
  saveAsrSettings(asrSettings);
  showToast('✓ 已保存');
  closeModal();
  render();
}

window.openSettings = openSettings;
window.onProviderChange = onProviderChange;
window.testAI = testAI;
window.testAsr = testAsr;
window.saveAISettings = saveAISettings;
window.openBulkImport = openBulkImport;
window.updateBulkPreview = updateBulkPreview;
window.setBulkDefaultTopic = setBulkDefaultTopic;
window.confirmBulkImport = confirmBulkImport;
window.openAddQuestion = openAddQuestion;
window.toggleAddTopic = toggleAddTopic;
window.updateAddTopicsRaw = updateAddTopicsRaw;
window.setAddRating = setAddRating;
window.saveAddQuestion = saveAddQuestion;
window.openReflectionModal = openReflectionModal;
window.addQuestion = addQuestion;
window.removeQ = removeQ;
window.updateQ = updateQ;
window.updateQTopicsRaw = updateQTopicsRaw;
window.toggleTopic = toggleTopic;
window.setRating = setRating;
window.saveReflection = saveReflection;

// ═══════════════════════════════════════════════════════════════
// 占位
// ═══════════════════════════════════════════════════════════════

function renderDecision() {
  return `
    <div class="empty">
      <div class="icon">📊</div>
      <h3>Decision · 即将上线</h3>
      <p>Offer 横向对比 · 谈薪辅助 · 决策支持</p>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// 主路由
// ═══════════════════════════════════════════════════════════════

let currentView = 'training';

function switchView(v) {
  currentView = v;
  render();
}

window.switchView = switchView;
window.goToPipeline = () => switchView('pipeline');
window.setDiscoverFilter = setDiscoverFilter;

function render() {
  // 更新 view tabs
  document.querySelectorAll('.view-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === currentView);
  });

  // Update badges
  const toTriage = allJobs().filter(j => getState(j).intent === 'unknown').length;
  const inPipeline = Object.values(loadStore()).filter(s =>
    s.intent !== 'unknown' && s.intent !== 'ignored' && s.pipelineCol !== 'closed'
  ).length;
  document.getElementById('discover-badge').textContent = toTriage;
  document.getElementById('pipeline-badge').textContent = inPipeline;
  document.getElementById('discover-badge').style.display = toTriage > 0 ? 'inline-flex' : 'none';
  document.getElementById('pipeline-badge').style.display = inPipeline > 0 ? 'inline-flex' : 'none';

  const main = document.getElementById('main-content');
  if (currentView === 'today') main.innerHTML = renderToday();
  else if (currentView === 'discover') main.innerHTML = renderDiscover();
  else if (currentView === 'pipeline') main.innerHTML = renderPipeline();
  else if (currentView === 'training') main.innerHTML = renderTraining();
  else if (currentView === 'decision') main.innerHTML = renderDecision();
}

document.querySelectorAll('.view-tab').forEach(btn => {
  btn.onclick = () => switchView(btn.dataset.view);
});

// 键盘快捷键 (Discover Inbox)
document.addEventListener('keydown', (e) => {
  if (currentView !== 'discover') return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  // 当前展开的行
  if (!expandedRowId) return;
  if (e.key === 'x' || e.key === 'X') skipJob(expandedRowId);
  else if (e.key === 'k' || e.key === 'K') keepJob(expandedRowId);
});

// 数据导入导出
document.getElementById('btn-export').onclick = () => {
  const data = {
    exportedAt: new Date().toISOString(),
    store: loadStore(),
    training: loadTraining(),
    settings: loadSettings(),
    asrSettings: loadAsrSettings(),
    resumeDrill: loadResumeDrill(),
    answerCache: loadAnswerCache(),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `job_tracker_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('✓ 已导出');
};

document.getElementById('btn-import').onclick = () => document.getElementById('import-file').click();
document.getElementById('import-file').onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target.result);
      if (!confirm('导入会覆盖当前进度，确定吗？')) return;
      if (data.store) saveStore(data.store);
      if (data.training) saveTraining(data.training);
      if (data.settings) saveSettings(data.settings);
      if (data.asrSettings) saveAsrSettings(data.asrSettings);
      if (data.resumeDrill) saveResumeDrill(data.resumeDrill);
      if (data.answerCache) saveAnswerCache(data.answerCache);
      render();
      showToast('✓ 已导入');
    } catch (err) { showToast('导入失败'); }
  };
  reader.readAsText(file);
};

// 触发首次迁移
loadStore();
render();
</script>
</body>
</html>
"""


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        tiered = json.load(f)
    with open(REJECTED, "r", encoding="utf-8") as f:
        rejected = json.load(f)

    for tj in tiered.values():
        for j in tj:
            clean_job(j)
    for r in rejected:
        clean_job(r)
        r["tier"] = "Rejected"

    data_json = json.dumps(tiered, ensure_ascii=False)
    rejected_json = json.dumps(rejected, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json)
    html = html.replace("__REJECTED_PLACEHOLDER__", rejected_json)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ v5 HTML 已生成: {OUTPUT}")


if __name__ == "__main__":
    main()
