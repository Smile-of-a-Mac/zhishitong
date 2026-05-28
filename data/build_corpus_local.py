#!/usr/bin/env python3
"""
从本地 pages/ 目录读取已下载的 HTML，构建微调语料。
完全离线运行，零 HTTP 请求，避免被误判为恶意访问。

用法:  python build_corpus_local.py
输出:
  - sdust_process_corpus_raw.jsonl   原始语料（含完整正文）
  - sdust_process_corpus_lora.jsonl  LoRA 微调格式
  - sdust_process_corpus_meta.json   元数据
"""

import json
import os
import re
import time
from html import unescape
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
PAGES_DIR = BASE_DIR / "pages"

# ====== URL -> 本地文件映射 ======
URL_MAP: dict[str, Path] = {}
for root, dirs, files in os.walk(PAGES_DIR):
    for fname in files:
        if fname.endswith((".htm", ".html")):
            full = Path(root) / fname
            rel = full.relative_to(PAGES_DIR)
            URL_MAP[f"https://{rel.as_posix()}"] = full
# 补充确认
EXTRA = {
    "https://jwc.sdust.edu.cn/gzlc/jwgl.htm": PAGES_DIR / "jwc.sdust.edu.cn/gzlc/jwgl.htm",
    "https://jwc.sdust.edu.cn/gzlc/xjgl.htm": PAGES_DIR / "jwc.sdust.edu.cn/gzlc/xjgl.htm",
    "https://yjsy.sdust.edu.cn/gzb/gzzd.htm": PAGES_DIR / "yjsy.sdust.edu.cn/gzb/gzzd.htm",
    "https://yjsy.sdust.edu.cn/gzzd/xj.htm": PAGES_DIR / "yjsy.sdust.edu.cn/gzzd/xj.htm",
}
URL_MAP.update(EXTRA)

KEYWORDS = [
    "请假", "请销假", "销假", "审批", "审核", "申请", "流程", "管理规定", "学籍",
    "休学", "复学", "缓考", "补考", "调课", "考试", "成绩单", "学历学位证明", "报销",
    "证明", "办理", "教务", "教学管理", "研究生", "本科生", "成绩", "课程",
]


# ==================== 工具函数 ====================

def read_local(url: str) -> Optional[str]:
    fp = URL_MAP.get(url)
    if fp and fp.exists():
        return fp.read_text(encoding="utf-8", errors="ignore")
    candidate = PAGES_DIR / url.replace("https://", "")
    if candidate.exists():
        return candidate.read_text(encoding="utf-8", errors="ignore")
    return None


def strip_html(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<!--[\s\S]*?-->", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    title = unescape(m.group(1))
    title = re.sub(r"\s*[-–—|]\s*山东科技大学.*$", "", title)
    return re.sub(r"\s+", " ", title).strip()


def extract_article_body(html: str) -> str:
    """从详情页提取正文（wp_articlecontent 容器）"""
    # 方法1: wp_articlecontent（大部分详情页）
    m = re.search(
        r'<div\s+class="wp_articlecontent">(.*?)</div>\s*</div>\s*</div>',
        html, re.I | re.S,
    )
    if m:
        text = strip_html(m.group(1))
        # 去掉开头的 "标题 发布时间：YYYY-MM-DD" 元数据行
        text = re.sub(r'^.{1,60}?发布时间[：:]\s*\d{4}[-/]\d{2}[-/]\d{2}\s*', '', text)
        return text.strip()

    # 方法2: paging_content
    m = re.search(
        r'class="paging_content"[^>]*>(.*?)</div>\s*</div>',
        html, re.I | re.S,
    )
    if m:
        text = strip_html(m.group(1))
        text = re.sub(r'^.{1,60}?发布时间[：:]\s*\d{4}[-/]\d{2}[-/]\d{2}\s*', '', text)
        return text.strip()

    # 方法3: 正文标记定位
    text = strip_html(html)
    m = re.search(r"正文\s+(.*?)(?:Copyright\s*©|联系电话)", text, re.I | re.S)
    if m and len(m.group(1).strip()) > 50:
        return m.group(1).strip()
    return ""


def extract_list_articles(html: str) -> list[dict]:
    """从列表页提取文章列表"""
    items = []
    pattern = re.compile(
        r'<a\s[^>]*href="([^"]*)"[^>]*(?:title="([^"]*)")?[^>]*>'
        r'\s*([^<]+?)\s*</a>'
        r'(?:[^<]*<span[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</span>)?',
        re.I,
    )
    for m in pattern.finditer(html):
        href = m.group(1)
        title = (m.group(2) or m.group(3)).strip()
        date = m.group(4) or ""
        if any(s in title for s in ["首页", "上页", "下页", "尾页", "本站", "学校", "部门", "加入收藏"]):
            continue
        if len(title) < 4 or "info/" not in href:
            continue
        items.append({"title": re.sub(r"\s+", " ", title).strip(), "href": href, "date": date})
    # 去重
    seen = set()
    return [x for x in items if not (x["title"] in seen or seen.add(x["title"]))]


def extract_attachments(html: str, base_url: str) -> list[str]:
    result = []
    for m in re.finditer(r'href="([^"]+)"', html, re.I):
        href = m.group(1)
        lo = href.lower()
        if any(lo.endswith(e) for e in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")) or "download.jsp" in lo:
            if href.startswith("http"):
                result.append(href)
            elif href.startswith("/"):
                dom = re.match(r"https?://([^/]+)", base_url)
                if dom:
                    result.append(f"https://{dom.group(1)}{href}")
            else:
                result.append(f"{base_url.rstrip('/')}/{href}")
    return list(dict.fromkeys(result))


def classify_topics(title: str, content: str) -> list[str]:
    topics = []
    for topic, kws in [
        ("成绩单", ["成绩单"]),
        ("学历学位证明", ["学历学位证明", "学历证明", "学位证明", "在读证明"]),
        ("学籍管理", ["学籍", "休学", "复学", "保留学籍", "修业年限"]),
        ("考试事务", ["考试", "监考", "缓考", "补考", "试卷", "成绩"]),
        ("调停课", ["调课", "停课", "调停课"]),
        ("请假销假", ["请假", "销假", "请销假"]),
        ("审批流程", ["审批", "审核"]),
        ("教学管理", ["教学管理", "教务", "教学资料"]),
        ("研究生事务", ["研究生"]),
        ("体质健康", ["体质", "健康测试"]),
        ("申请表", ["申请表", "表格"]),
        ("管理规定", ["管理规定", "规定", "办法", "守则", "条例"]),
        ("学生证", ["学生证", "火车票"]),
    ]:
        if any(k in title or k in content for k in kws):
            topics.append(topic)
    return topics if topics else ["其他"]


def is_list_page(url: str) -> bool:
    return "/info/" not in url


# ==================== 构建语料 ====================

def build_raw_corpus() -> list[dict]:
    records = []
    all_urls = set(URL_MAP.keys())

    # 从列表页发现详情链接
    for lp in [
        "https://jwc.sdust.edu.cn/gzlc/jwgl.htm",
        "https://jwc.sdust.edu.cn/gzlc/xjgl.htm",
        "https://yjsy.sdust.edu.cn/gzb/gzzd.htm",
    ]:
        html = read_local(lp)
        if not html:
            continue
        for item in extract_list_articles(html):
            href = item["href"]
            if href.startswith("/"):
                dom = re.match(r"https?://([^/]+)", lp)
                if dom:
                    all_urls.add(f"https://{dom.group(1)}{href}")
            elif href.startswith("http") and "sdust.edu.cn" in href:
                all_urls.add(href)

    for url in sorted(all_urls):
        html = read_local(url)
        if not html:
            continue
        title = get_title(html)
        if not title:
            continue

        if is_list_page(url):
            articles = extract_list_articles(html)
            if not articles:
                continue
            lines = [f"本栏目包含以下 {len(articles)} 个事项："]
            for a in articles[:20]:
                lines.append(f"- {a['title']}（{a['date']}）")
            content = "\n".join(lines)
            source_type = "list_page"
            list_data = articles
        else:
            content = extract_article_body(html)
            if not content or len(content) < 15:
                continue
            source_type = "detail_page"
            list_data = []

        hit = [k for k in KEYWORDS if k in title or k in content]
        if not hit:
            continue

        attachments = extract_attachments(html, url)
        topics = classify_topics(title, content)

        rec = {
            "url": url,
            "title": title,
            "source_type": source_type,
            "topics": topics,
            "keyword_hits": hit,
            "content": content[:3000],
            "content_length": len(content),
            "attachments": attachments,
        }
        if list_data:
            rec["list_items"] = list_data[:15]
        records.append(rec)

    # 去重
    uniq, seen = [], set()
    for r in records:
        k = (r["title"], r["content"][:100])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def build_lora_corpus(raw_records: list[dict]) -> list[dict]:
    SYS_DETAIL = (
        "你是山东科技大学事务流程助手。请根据提供的制度原文，"
        "提炼「办理条件-提交材料-审批链路-办理时限-结果与后续动作（含销假/归档）」结构化信息。"
        "若原文未明确某项，写「未明确」。只输出这五个字段。"
    )
    SYS_LIST = (
        "你是山东科技大学事务流程助手。请根据提供的栏目列表页信息，"
        "输出该栏目下可办理的事项清单，帮助用户快速定位需要的流程。"
    )

    items = []
    for r in raw_records:
        content = r["content"]
        title = r["title"]
        url = r["url"]

        if r["source_type"] == "list_page":
            inp = f"栏目: {url}\n标题: {title}\n事项列表:\n{content}"
            out = f"该栏目下包含以下可办理事项：\n{content}"
            items.append({
                "instruction": SYS_LIST,
                "input": inp,
                "output": out,
                "meta": {"source": url, "title": title, "type": "list_navigation"},
            })
            continue

        # ---- 详情页 ----
        inp = (
            f"来源: {url}\n"
            f"标题: {title}\n"
            f"关键词: {'、'.join(r['keyword_hits'])}\n"
            f"正文: {content}\n"
            f"附件: {'; '.join(r['attachments'][:3]) if r['attachments'] else '无'}"
        )
        # 智能分句：先按句号分，再按换行/分号分，过滤噪音
        raw_sents = []
        for part in re.split(r"[。\n]", content):
            for sub in re.split(r"[；;]", part):
                s = sub.strip()
                # 过滤噪音行：纯元数据、太短、纯数字/标点
                if len(s) < 6:
                    continue
                if re.match(r'^(?:发布时间|附件[【\[]|点击|下载|浏览|首页|上页|下页|尾页)', s):
                    continue
                if re.match(r'^[\d\s\.,;:：、\-–—/]+$', s):
                    continue
                raw_sents.append(s)

        def find_best(keys: list[str], bad_words: list[str] = None) -> str:
            """在 raw_sents 中找到匹配 keys 最多的句子，排除含 bad_words 的"""
            bad_words = bad_words or []
            best, best_score = None, 0
            for s in raw_sents:
                if any(b in s for b in bad_words):
                    continue
                sc = sum(1 for k in keys if k in s)
                if sc > best_score:
                    best_score, best = sc, s
            if best and best_score > 0:
                return best.strip()[:150]
            # 宽泛搜索：在原文中找关键词，取上下文
            for k in keys:
                idx = content.find(k)
                if idx >= 0:
                    start, end = max(0, idx - 15), min(len(content), idx + 100)
                    snip = content[start:end].strip()
                    for sep in ["。", "；", "\n"]:
                        p = snip.find(sep)
                        if p > 10:
                            snip = snip[:p]; break
                    snip = snip.strip()
                    if len(snip) > 8 and not re.match(r'^(?:发布时间|附件|点击|下载)', snip):
                        if not any(b in snip for b in bad_words):
                            return snip[:150]
            return "未明确"

        # 对于极短页面（<100字实质内容）或纯列表型页面，内容在附件中
        is_thin = len(content) < 100
        # 检测内容是否主要为学院名称翻译列表（大量英文单词+中文学院名）
        eng_ratio = len(re.findall(r'[A-Za-z]{3,}', content)) / max(len(content), 1)
        is_name_list = eng_ratio > 0.05 and len(content) > 500

        if is_thin or is_name_list:
            has_attach = bool(r["attachments"])
            if is_name_list:
                attach_note = "此页面主要为学院/专业中英文对照表，办理流程信息请查阅附件或联系教务处"
            else:
                attach_note = "详细规定请下载附件查阅" if has_attach else "页面内容较少，请参考原始网页"
            out_lines = [
                f"办理条件: {attach_note}",
                f"提交材料: {attach_note}",
                f"审批链路: {attach_note}",
                f"办理时限: {attach_note}",
                f"结果与后续动作: {attach_note}",
            ]
        else:
            out_lines = [
                "办理条件: " + find_best(["适用于", "对象", "在校生", "毕业生", "本科生", "研究生",
                                        "条件", "范围", "需要满足", "可以申请", "方可"], ["教学条件"]),
                "提交材料: " + find_best(["申请表", "附件", "证明", "材料", "票据", "成绩单",
                                        "证件", "学生证", "身份证", "提交", "携带", "出示"]),
                "审批链路: " + find_best(["学院", "部门", "教务", "研究生院", "财务", "审核",
                                        "审批", "签字", "盖章", "办公室", "辅导员", "教务员",
                                        "导师", "分管"]),
                "办理时限: " + find_best(["工作日", "时间", "日期", "截止", "提前", "规定时间",
                                        "时限", "及时"], ["课程设置", "开课时间", "教学时间"]),
                "结果与后续动作: " + find_best(["打印", "出具", "通过", "驳回", "归档", "销假",
                                            "领取", "下载", "通知", "录入", "加盖", "核验",
                                            "反馈", "记录"]),
            ]
        if r["attachments"]:
            out_lines.append("可下载附件: " + "；".join(r["attachments"][:3]))

        items.append({
            "instruction": SYS_DETAIL,
            "input": inp,
            "output": "\n".join(out_lines),
            "meta": {"source": url, "title": title, "topics": r["topics"]},
        })
    return items


def main():
    print("=" * 60)
    print("从本地 pages/ 构建语料（完全离线，零 HTTP 请求）")
    print(f"已索引 {len(URL_MAP)} 个本地页面")
    print("=" * 60)

    print("\n[1/3] 构建 raw 语料...")
    raw = build_raw_corpus()
    d_cnt = sum(1 for r in raw if r["source_type"] == "detail_page")
    l_cnt = sum(1 for r in raw if r["source_type"] == "list_page")
    print(f"  详情页: {d_cnt} | 列表页: {l_cnt} | 合计: {len(raw)}")

    raw_path = BASE_DIR / "sdust_process_corpus_raw.jsonl"
    with open(raw_path, "w", encoding="utf-8") as f:
        for r in raw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  -> {raw_path}")

    print("\n[2/3] 构建 lora 语料...")
    lora = build_lora_corpus(raw)
    print(f"  生成 {len(lora)} 条训练样本")
    lora_path = BASE_DIR / "sdust_process_corpus_lora.jsonl"
    with open(lora_path, "w", encoding="utf-8") as f:
        for item in lora:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  -> {lora_path}")

    print("\n[3/3] 保存元数据...")
    meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "local_offline_zero_http",
        "total_local_pages": len(URL_MAP),
        "raw_records": len(raw),
        "lora_samples": len(lora),
        "detail_pages": d_cnt,
        "list_pages": l_cnt,
    }
    meta_path = BASE_DIR / "sdust_process_corpus_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  -> {meta_path}")

    print("\n" + "=" * 60)
    print("语料生成完成!")
    for r in raw:
        tag = "[列表]" if r["source_type"] == "list_page" else "[详情]"
        print(f"  {tag} [{', '.join(r['topics'][:3])}] {r['title']}  ({r['content_length']}字)")

    # 打印一个样本验证
    if lora:
        print("\n--- lora 样本预览 (第一条详情) ---")
        for item in lora:
            if item["meta"].get("type") != "list_navigation":
                print(f"TITLE: {item['meta']['title']}")
                print(f"OUTPUT:\n{item['output'][:400]}")
                break
    print()


if __name__ == "__main__":
    main()
