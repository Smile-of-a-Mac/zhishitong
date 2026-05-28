import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from html import unescape

ssl._create_default_https_context = ssl._create_unverified_context

LIST_PAGES = [
    "https://jwc.sdust.edu.cn/gzlc/jwgl.htm",
    "https://jwc.sdust.edu.cn/gzlc/xjgl.htm",
    "https://yjsy.sdust.edu.cn/gzb/gzzd.htm",
]

DETAIL_WHITELIST = [
    "https://jwc.sdust.edu.cn/info/1037/4262.htm",
    "https://jwc.sdust.edu.cn/info/1037/2026.htm",
    "https://jwc.sdust.edu.cn/info/1036/3019.htm",
    "https://jwc.sdust.edu.cn/info/1036/3488.htm",
    "https://jwc.sdust.edu.cn/info/1036/3491.htm",
    "https://yjsy.sdust.edu.cn/gzb/info/1010/4512.htm",
]

KEYWORDS = [
    "请假", "请销假", "销假", "审批", "审核", "申请", "流程", "管理规定", "学籍",
    "休学", "复学", "缓考", "补考", "调课", "考试", "成绩单", "学历学位证明", "报销",
]


def fetch(url: str, retries: int = 2, timeout: int = 8) -> str:
    last_error = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(500_000)
            return body.decode("utf-8", "ignore")
        except Exception as e:
            last_error = e
            time.sleep(0.8 * (i + 1))
    raise last_error


def strip_html(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip()


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def main() -> None:
    candidate = set(DETAIL_WHITELIST)
    list_ok = []
    list_failed = []

    for page in LIST_PAGES:
        try:
            html = fetch(page)
            list_ok.append(page)
        except Exception as e:
            list_failed.append({"url": page, "error": str(e)})
            continue

        for href in re.findall(r'href="([^"]+)"', html, re.I):
            if "info/" in href and href.endswith(".htm"):
                u = abs_url(page, href)
                if "sdust.edu.cn" in urllib.parse.urlparse(u).netloc:
                    candidate.add(u)
            if "download.jsp" in href:
                candidate.add(abs_url(page, href))

    # 防止抓取规模过大导致长时间阻塞：仅保留白名单和同栏目少量详情页
    candidate = set([u for u in candidate if u in DETAIL_WHITELIST or ("/info/103" in u and u.endswith(".htm"))])

    records = []
    detail_failed = []

    for u in sorted(candidate):
        if not u.endswith(".htm") and "download.jsp" not in u:
            continue
        try:
            html = fetch(u)
        except Exception as e:
            detail_failed.append({"url": u, "error": str(e)})
            continue

        title = get_title(html)
        text = strip_html(html)
        hit = [k for k in KEYWORDS if k in title or k in text]
        if not hit:
            continue

        attachments = []
        for href in re.findall(r'href="([^"]+)"', html, re.I):
            hu = abs_url(u, href)
            lower = hu.lower()
            if "download.jsp" in lower or lower.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):
                attachments.append(hu)
        attachments = list(dict.fromkeys(attachments))

        records.append({
            "url": u,
            "title": title,
            "keyword_hits": hit,
            "content": text[:2600],
            "attachments": attachments,
        })

    uniq = []
    seen = set()
    for r in records:
        key = (r["title"], r["content"][:140])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    raw_path = "/Users/wangdaoyu/VSCode/sito/zhishitong/data/sdust_process_corpus_raw.jsonl"
    lora_path = "/Users/wangdaoyu/VSCode/sito/zhishitong/data/sdust_process_corpus_lora.jsonl"
    meta_path = "/Users/wangdaoyu/VSCode/sito/zhishitong/data/sdust_process_corpus_meta.json"

    with open(raw_path, "w", encoding="utf-8") as f:
        for r in uniq:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(lora_path, "w", encoding="utf-8") as f:
        for r in uniq:
            instruction = (
                "你是高校事务流程助手。请根据提供的制度原文，提炼“办理条件-提交材料-审批链路-办理时限-结果与后续动作（含销假/归档）”。"
                "若原文未明确某项，写“未明确”。"
            )
            inp = (
                f"来源: {r['url']}\n"
                f"标题: {r['title']}\n"
                f"关键词: {'、'.join(r['keyword_hits'])}\n"
                f"正文: {r['content']}\n"
                f"附件: {'; '.join(r['attachments']) if r['attachments'] else '无'}"
            )

            sentences = [s.strip() for s in re.split(r"[。；;\n]", r["content"]) if s.strip()]
            picked = []
            for s in sentences:
                if any(k in s for k in ["申请", "提交", "审核", "审批", "办理", "流程", "管理规定", "休学", "复学", "调课", "成绩单", "证明", "考试", "学籍", "销假", "请假"]):
                    picked.append(s)
                if len(picked) >= 10:
                    break

            def find_line(keys):
                for s in picked:
                    if any(k in s for k in keys):
                        return s
                return "未明确"

            output_lines = [
                "办理条件: " + find_line(["适用于", "对象", "在校生", "毕业生", "本科生", "研究生"]),
                "提交材料: " + find_line(["申请表", "附件", "证明", "材料", "票据", "成绩单"]),
                "审批链路: " + find_line(["学院", "部门", "教务", "研究生院", "财务", "审核", "审批"]),
                "办理时限: " + find_line(["工作日", "时间", "日期", "截止", "办理"]),
                "结果与后续动作: " + find_line(["打印", "出具", "通过", "驳回", "归档", "销假", "领取"]),
            ]
            if r["attachments"]:
                output_lines.append("可下载附件: " + "；".join(r["attachments"][:3]))

            item = {
                "instruction": instruction,
                "input": inp,
                "output": "\n".join(output_lines),
                "meta": {"source": r["url"], "title": r["title"]},
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed_list_pages": LIST_PAGES,
        "list_pages_ok": list_ok,
        "list_pages_failed": list_failed,
        "candidate_pages": len(candidate),
        "matched_records": len(uniq),
        "failed_detail_pages_count": len(detail_failed),
        "failed_detail_pages_sample": detail_failed[:20],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("matched_records=", len(uniq))
    print("raw=", raw_path)
    print("lora=", lora_path)
    print("meta=", meta_path)
    print("sample_titles=")
    for r in uniq[:10]:
        print("-", r["title"])


if __name__ == "__main__":
    main()
