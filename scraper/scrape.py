#!/usr/bin/python3
"""
v4 - 扩大召回
改动：
1. 关键词扩展到 20 组（覆盖更多角度）
2. 多城市并行（全国 + 北京 + 上海 + 杭州 + 深圳）
3. 增量保存（每个关键词完成后立即保存，防丢失）
4. 合并 v2 已有数据（不重新爬已有的）
5. 复用 v3.1 的评分模型

输出到 v4_output/
"""

import asyncio
import json
import random
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import requests
import websockets

OUTPUT_DIR = Path(__file__).parent / "v4_output"
OUTPUT_DIR.mkdir(exist_ok=True)

CDP_PORT = 9222
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
AUTH_DIR = str(Path(__file__).parent / ".auth")

# ─── 扩展关键词 20 组 ───
RECALL_KEYWORDS = [
    # Go 生态
    "Golang", "Go 后端", "Go 微服务", "Go 平台",
    # K8s / 云原生
    "Kubernetes", "K8s 开发", "云原生", "容器 开发", "Operator",
    # GPU / 算力
    "GPU", "算力", "AI Infra", "大模型 平台", "推理 平台", "训练平台",
    # 基础设施
    "基础设施 后端", "分布式 Go", "中间件 Go", "平台开发 Go",
    # 框架级
    "go-zero",
]

# ─── 城市 ───
CITIES = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "杭州": "101210100",
    "深圳": "101280600",
}

# 经验段（只搜初级+中级）
EXPERIENCE_CODE = "101,102,103,104"  # 应届+1年内+1-3年+3-5年

PAGES_PER_SEARCH = 5

# ═════════════════════════════════════════════
# CDP
# ═════════════════════════════════════════════

class CDPChrome:
    def __init__(self):
        self.process = None
        self.ws = None
        self.msg_id = 0
        self.target_id = None

    async def start(self):
        try:
            r = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            if r.status_code == 200:
                print("  ✓ 连接已有 Chrome")
                return
        except Exception:
            pass
        print("  启动 Chrome...")
        self.process = subprocess.Popen(
            [CHROME_PATH, f"--remote-debugging-port={CDP_PORT}",
             f"--user-data-dir={AUTH_DIR}", "--no-first-run",
             "--window-size=1,1", "--window-position=-9999,-9999", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(15):
            try:
                r = requests.get(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
                if r.status_code == 200:
                    print("  ✓ Chrome 已启动")
                    return
            except Exception:
                await asyncio.sleep(1)
        raise RuntimeError("Chrome 启动超时")

    async def new_tab(self):
        r = requests.put(f"http://127.0.0.1:{CDP_PORT}/json/new?about:blank", timeout=5)
        data = r.json()
        self.target_id = data["id"]
        self.ws = await websockets.connect(data["webSocketDebuggerUrl"], max_size=10*1024*1024)
        await self.send("Page.enable")

    async def send(self, method, params=None):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params
        await self.ws.send(json.dumps(msg))
        while True:
            try:
                resp = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=20))
            except asyncio.TimeoutError:
                raise RuntimeError(f"CDP timeout: {method}")
            if resp.get("id") == self.msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def navigate(self, url):
        await self.send("Page.navigate", {"url": url})
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                resp = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                break
            if resp.get("method") == "Page.loadEventFired":
                break
        await asyncio.sleep(random.uniform(2.5, 4))

    async def evaluate(self, expression):
        r = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return r.get("result", {}).get("value")

    async def close_tab(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
        if self.target_id:
            try:
                requests.get(f"http://127.0.0.1:{CDP_PORT}/json/close/{self.target_id}", timeout=3)
            except Exception:
                pass
            self.target_id = None

    def shutdown(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


# ═════════════════════════════════════════════
# 提取
# ═════════════════════════════════════════════

LIST_JS = r"""
(function(){
  var jobs = [];
  document.querySelectorAll('.job-card-wrapper, .job-card-body, [class*="job-card"]').forEach(function(card){
    try {
      var title = (card.querySelector('.job-name, .job-title') || {}).innerText || '';
      var company = (card.querySelector('.company-name a, .company-name') || {}).innerText || '';
      var salary = (card.querySelector('.salary') || {}).innerText || '';
      var area = (card.querySelector('.job-area') || {}).innerText || '';
      var link = card.querySelector('a[href*="job_detail"]');
      var href = link ? (link.href || '') : '';
      var text = card.innerText || '';
      var exp = '';
      var desc = (card.querySelector('.info-desc') || {}).innerText || '';
      var m = text.match(/(应届|在校|1年以内|经验不限|\d+-\d+年|\d+年以上)/);
      if (m) exp = m[1];
      if (!exp && desc) exp = desc;
      if (title) jobs.push({title:title, company:company, salary:salary, area:area, href:href, text:text.substring(0,800), exp:exp});
    } catch(e){}
  });
  return JSON.stringify(jobs);
})()
"""


async def recall(chrome):
    print("\n" + "=" * 60)
    print(f"  v4 广谱召回：{len(RECALL_KEYWORDS)} 关键词 × {len(CITIES)} 城市 × {PAGES_PER_SEARCH} 页")
    print("=" * 60)

    all_raw = []
    seen_href = set()

    # 加载已有 raw 数据（如果有）避免重复爬
    existing_file = OUTPUT_DIR / "raw.json"
    if existing_file.exists():
        try:
            with open(existing_file) as f:
                existing = json.load(f)
                all_raw.extend(existing)
                for j in existing:
                    if j.get("href"):
                        seen_href.add(j["href"])
            print(f"  加载已有数据: {len(existing)} 条")
        except Exception:
            pass

    # 也加载 v2 的数据作为 base
    v2_raw = Path(__file__).parent / "v2_output" / "raw.json"
    if v2_raw.exists():
        try:
            with open(v2_raw) as f:
                v2_data = json.load(f)
                for j in v2_data:
                    if j.get("href") and j["href"] not in seen_href:
                        all_raw.append(j)
                        seen_href.add(j["href"])
            print(f"  合并 v2 数据: {len(v2_data)} 条")
        except Exception:
            pass

    await chrome.new_tab()

    total = len(RECALL_KEYWORDS) * len(CITIES)
    idx = 0
    stats = {}

    for kw in RECALL_KEYWORDS:
        for city_name, city_code in CITIES.items():
            idx += 1
            key = f"{kw}@{city_name}"
            stats[key] = 0

            for page in range(1, PAGES_PER_SEARCH + 1):
                url = (
                    f"https://www.zhipin.com/web/geek/job?"
                    f"query={quote(kw)}&city={city_code}"
                    f"&experience={EXPERIENCE_CODE}&page={page}"
                )
                print(f"  [{idx}/{total}] {kw}@{city_name} p{page}", end=" ", flush=True)

                try:
                    await chrome.navigate(url)
                except Exception as e:
                    print(f"✗ {e}")
                    break

                title = await chrome.evaluate("document.title") or ""
                if "安全验证" in title:
                    print(f"⚠ 验证 → 等 40s")
                    await asyncio.sleep(40)
                    break
                if "注册登录" in title:
                    print("⚠ 未登录")
                    break

                for _ in range(2):
                    await chrome.evaluate(f"window.scrollBy(0, {random.randint(400,600)})")
                    await asyncio.sleep(0.5)

                try:
                    result = await chrome.evaluate(LIST_JS)
                    raw = json.loads(result) if result else []
                except Exception as e:
                    print(f"✗ {e}")
                    break

                if not raw:
                    print("(空)")
                    break

                new_count = 0
                for rj in raw:
                    href = rj.get("href", "")
                    if href and href not in seen_href:
                        seen_href.add(href)
                        rj["source_keyword"] = kw
                        rj["source_city"] = city_name
                        rj["source"] = "BOSS直聘"
                        all_raw.append(rj)
                        new_count += 1

                stats[key] += new_count
                print(f"✓ 新增 {new_count}/{len(raw)}")

                # 每次保存一次，防止中途崩溃
                if idx % 5 == 0:
                    with open(existing_file, "w", encoding="utf-8") as f:
                        json.dump(all_raw, f, ensure_ascii=False)

                await asyncio.sleep(random.uniform(2, 4))

            await asyncio.sleep(random.uniform(3, 6))

    await chrome.close_tab()

    # 最终保存
    with open(existing_file, "w", encoding="utf-8") as f:
        json.dump(all_raw, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "recall_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n  ✓ 总计 {len(all_raw)} 条（含 v2 数据）")
    return all_raw, stats


# ═════════════════════════════════════════════
# 详情补全
# ═════════════════════════════════════════════

DETAIL_JS = r"""
(function() {
  var jd = (document.querySelector('.job-sec-text') || {}).innerText || '';
  var company = '';
  var sider = document.querySelector('.sider-company .company-info');
  if (sider) company = sider.innerText.trim();
  if (!company) {
    var t = document.title || '';
    var m = t.match(/[_](.+?)招聘-BOSS/);
    if (m) company = m[1].trim();
  }
  var salary = '';
  var salEl = document.querySelector('.salary');
  if (salEl) salary = salEl.innerText.trim();
  if (!salary || salary === '元') {
    var primary = (document.querySelector('.info-primary') || {}).innerText || '';
    var sm = primary.match(/(\d+-\d+K[^\s]*)/);
    if (sm) salary = sm[1];
  }
  var primary = (document.querySelector('.info-primary') || {}).innerText || '';
  var lines = primary.split('\n').map(function(l){return l.trim()}).filter(Boolean);
  var exp = '';
  var area = '';
  for (var i=0; i<lines.length; i++) {
    if (/[年经验本科硕士]/.test(lines[i])) { exp = lines[i]; break; }
  }
  var locEl = document.querySelector('.location-address');
  if (locEl) area = locEl.innerText.trim();
  else {
    var em = (exp || '').match(/^(\S+?)\s/);
    if (em) area = em[1];
  }
  var companyInfo = '';
  var siderFull = document.querySelector('.sider-company');
  if (siderFull) companyInfo = siderFull.innerText.trim();
  var tags = Array.from(document.querySelectorAll('.job-tags .tag-item, .job-banner .tag-list li')).map(function(t){return t.innerText.trim()});
  tags = tags.filter(function(v,i,a){return a.indexOf(v)===i});
  return JSON.stringify({jd:jd, company:company, salary:salary, area:area, tags:tags.join(', '), companyInfo:companyInfo, exp:exp});
})()
"""


async def enrich_top(chrome, jobs, top_n=150):
    print("\n" + "=" * 60)
    print(f"  详情补全 Top {top_n}")
    print("=" * 60)

    await chrome.new_tab()
    top = [j for j in jobs if j.get("href") and not j.get("fetched_detail")][:top_n]
    print(f"  待补全: {len(top)}（已补全的跳过）")

    for i, job in enumerate(top):
        print(f"  [{i+1}/{len(top)}] {job['title'][:40]}", end=" ", flush=True)
        try:
            await chrome.navigate(job["href"])
            await chrome.evaluate("window.scrollBy(0, 400)")
            await asyncio.sleep(0.5)
            result = await chrome.evaluate(DETAIL_JS)
            if result:
                d = json.loads(result)
                job["jd"] = d.get("jd", "").strip() or job.get("jd", "")
                job["company"] = d.get("company", "").strip() or job.get("company", "")
                job["salary"] = d.get("salary", "").strip() or job.get("salary", "")
                job["area"] = d.get("area", "").strip() or job.get("area", "")
                job["tags"] = d.get("tags", "")
                job["company_info"] = d.get("companyInfo", "").strip()
                job["experience"] = d.get("exp", "").strip() or job.get("exp", "")
                job["fetched_detail"] = True
                print(f"✓ {job['company'][:15]}")
            else:
                print("✗")
        except Exception as e:
            print(f"✗ {e}")
        await asyncio.sleep(random.uniform(2, 4))

    await chrome.close_tab()
    return top


# ═════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("  v4 扩大召回")
    print(f"  输出: {OUTPUT_DIR}")
    print("=" * 60)

    start = time.time()
    chrome = CDPChrome()

    try:
        await chrome.start()

        # Stage 1: 召回
        raw_jobs, stats = await recall(chrome)

        # 这里加载 v3.1 的评分逻辑
        # 先保存 raw，后续由 score_v4.py 独立评分
        print(f"\n  ✓ 召回完成，共 {len(raw_jobs)} 条")

        # Stage 2: 对新增的岗位补全详情（已有 v2 详情的跳过）
        # 但先需要预过滤，不然会补全太多无用的
        # 简单预过滤：按 title 去重 + 去掉明显不相关的
        filtered = []
        seen_keys = set()
        for j in raw_jobs:
            key = (j.get("company", "") + "|" + j.get("title", "")).lower().strip()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)

            title_lower = j.get("title", "").lower()
            # 快速黑名单
            if any(bl in title_lower for bl in ["销售", "商务", "bd ", "产品经理",
                                                   "前端", "ios", "android", "测试", "qa",
                                                   "实习生", "总监", "vp", "cto"]):
                continue
            filtered.append(j)

        print(f"  预过滤后: {len(filtered)}")

        # 只补全前 200 条没补过的
        to_enrich = [j for j in filtered if not j.get("fetched_detail")][:200]
        if to_enrich:
            await enrich_top(chrome, to_enrich, top_n=200)

        # 最终保存
        with open(OUTPUT_DIR / "raw.json", "w", encoding="utf-8") as f:
            json.dump(raw_jobs, f, ensure_ascii=False, indent=2)

    finally:
        chrome.shutdown()

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  召回完成，耗时 {elapsed/60:.1f} 分钟")
    print(f"  共 {len(raw_jobs)} 条（去重前）")
    print(f"  下一步：python3 score_v4.py 运行评分")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
