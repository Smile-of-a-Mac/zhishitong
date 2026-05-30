"""
OCR 服务层 — 三档路由 + 本地小模型 JSON 填充

层级路由:
  free:      EasyOCR 提取文字 → 本地 llama-server 填充 JSON
  pro:       外部 LLM 多模态 OCR + JSON 填充（有配额）
  pro_plus:  外部 LLM 多模态 OCR + JSON 填充（无限制）
"""
import base64, io, json, logging, re
from enum import Enum
from typing import Optional
import httpx
from PIL import Image
from config import LLAMA_SERVER_URL, EASYOCR_LANGS, EASYOCR_GPU
from services.template_service import detect_document_type

logger = logging.getLogger(__name__)


class OCRProvider(str, Enum):
    LOCAL = "local_easyocr"
    LLM = "llm_multimodal"
    PDF_TEXT = "pdf_text"


# ========== EasyOCR（懒加载，ARM/x86 通用） ==========
_easy_reader = None

def _get_easyocr():
    global _easy_reader
    if _easy_reader is None:
        logger.info("初始化 EasyOCR (跨架构纯 CPU)...")
        import easyocr
        _easy_reader = easyocr.Reader(EASYOCR_LANGS, gpu=EASYOCR_GPU)
        logger.info("EasyOCR 就绪")
    return _easy_reader


def local_easyocr(image_bytes: bytes) -> str:
    """本地 EasyOCR 提取图片中的文字"""
    import numpy as np
    img = Image.open(io.BytesIO(image_bytes))
    img_array = np.array(img)
    reader = _get_easyocr()
    results = reader.readtext(img_array, paragraph=True)
    text = "\n".join([res[1] for res in results])
    return text.strip() or "[EasyOCR] 未识别到文字"


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 20) -> str:
    """从文字型 PDF 直接提取文本；扫描件通常会返回空文本。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf 依赖，无法提取 PDF 文本") from exc

    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts: list[str] = []
    for page in reader.pages[:max_pages]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            texts.append(page_text.strip())

    text = "\n\n".join(texts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_page_to_image(pdf_bytes: bytes, page_index: int = 0) -> bytes:
    """将 PDF 指定页渲染为 PNG 图片字节。需要 pymupdf。"""
    import fitz  # pymupdf
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_index >= len(doc):
        page_index = 0
    page = doc[page_index]
    # 200 DPI 渲染
    mat = fitz.Matrix(200 / 72, 200 / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


async def pdf_text_ocr(
    pdf_bytes: bytes,
    fill_api_key: str = "",
    fill_api_base: str = "",
    fill_model: str = "",
) -> tuple[str, Optional[dict], bool]:
    """
    文字型 PDF：直接提取文本，再复用现有字段填充链路。
    返回 (raw, filled, is_scanned)。
    is_scanned=True 表示 PDF 是扫描件（无文本层），需走图片 OCR。
    """
    raw = extract_pdf_text(pdf_bytes)
    if len(raw.strip()) < 20:
        return "", None, True  # 扫描件，标记 is_scanned

    doc_type = detect_document_type(raw)
    try:
        filled = await _fill_with_best(raw, fill_api_key, fill_api_base, fill_model, document_type=doc_type)
    except Exception as exc:
        logger.warning(f"PDF 文本字段填充失败，仅返回原文: {exc}")
        filled = {}
    if filled and "error" not in str(filled):
        filled = _normalize_json_keys(filled)
        if doc_type == "leave":
            filled = _postprocess_leave_fields(filled, raw)
    return raw, filled or {}, False  # 文字型 PDF


# ========== 本地小模型 JSON 填充 ==========
# 中英文 field key 映射表（模型输出中文字段名时的兜底）
_FIELD_KEY_MAP: dict[str, str] = {
    "申请人": "applicant", "申请金额": "amount", "报销金额": "amount",
    "金额": "amount", "发票号码": "invoice_no", "发票号": "invoice_no",
    "学院": "college", "班级": "class_name",
    "发生日期": "date", "日期": "date", "开始日期": "start_date",
    "结束日期": "end_date", "天数": "days", "请假类型": "leave_type",
    "事由": "reason", "事由说明": "reason", "说明": "reason",
    "费用类别": "category", "社团名称": "club_name",
    "活动名称": "activity", "活动日期": "date",
    "场地需求": "venue", "预计人数": "participants",
    "涉及校外人员": "external", "活动简介": "description",
    "教室编号": "room_no", "使用日期": "date",
    "开始时间": "start_time", "结束时间": "end_time",
    "用途": "purpose", "需多媒体设备": "need_multimedia",
    "目的地": "destination", "出发日期": "start_date",
    "返回日期": "end_date", "出差事由": "purpose",
    "预估费用": "estimated_cost", "是否出境": "international",
    "学号": "student_id", "工号": "student_id",
    "名称": "name", "姓名": "applicant",
    "学生姓名": "applicant", "辅导员姓名": "advisor",
    "辅导员联系方式": "advisor_phone", "导师联系方式": "advisor_phone",
    "联系方式": "phone", "联系电话": "phone",
    "外卖电话": "phone", "紧急联系人": "emergency_contact",
    "外出时间": "start_date", "离校时间": "start_date",
    "出发时间": "start_date", "开始时间": "start_time",
    "返校时间": "end_date", "预计返校": "end_date",
    "返校时间（此处由保安填写）": "return_time",
    "结束时间": "end_time", "返回时间": "end_time",
    "去向": "destination", "前往地点": "destination",
    "交通工具": "transportation", "交通方式": "transportation",
    "往返交通": "transportation",
    # 多模态 LLM 常见输出（兜底映射）
    "name": "applicant", "姓名": "applicant",
    "class": "class_name",
    "contact_info": "phone", "联系电话": "phone", "contact": "phone",
    "counselor_name": "advisor", "辅导员": "advisor",
    "counselor_contact": "advisor_phone",
    "reason_for_leave": "reason", "请假原因": "reason",
    "leave_period": "duration",
    "supervisor_signature": "advisor_signature",
    "counselor_signature": "counselor_signature",
    "official_seal": "official_seal",
    # 发票常见英文字段（多模态模型常输出）
    "invoice_number": "invoice_no",
    "invoice_no": "invoice_no",
    "invoice_date": "date",
    "date_issued": "date",
    "total_amount": "amount",
    "amount_total": "amount",
    "tax_amount": "tax",
    "buyer_name": "applicant",
    "seller_name": "department",
    "item_name": "reason",
    "project_name": "reason",
}


def _normalize_json_keys(data: dict) -> dict:
    """将 JSON 中的中文字段名映射为模板英文 key（兜底降噪）"""
    normalized = {}
    for k, v in data.items():
        if k in _FIELD_KEY_MAP:
            normalized[_FIELD_KEY_MAP[k]] = v
        else:
            normalized[k] = v
    return normalized


def _fallback_extract(raw_text: str, document_type: Optional[str] = None) -> dict:
    """纯正则兜底：从原文直接提取关键字段"""
    from services.template_service import get_template
    result: dict[str, str] = {}
    text = raw_text or ""

    tpl = get_template(document_type) if document_type else None

    # 先尝试按模板字段名提取
    if tpl:
        for field in tpl.get("fields", []):
            key = field["key"]
            label = field["label"]
            # "label：value" 或 "label value" 模式
            pattern = re.escape(label) + r"[：:]\s*([^\n，,。；;]{1,60})"
            m = re.search(pattern, text)
            if m:
                result[key] = m.group(1).strip()

    # 请假类型自动检测
    if document_type == "leave" and "leave_type" not in result:
        if re.search(r"事假", text):
            result["leave_type"] = "事假"
        elif re.search(r"病假", text):
            result["leave_type"] = "病假"
        elif re.search(r"公假", text):
            result["leave_type"] = "公假"

    # 日期自动提取
    if document_type == "leave":
        date_pattern = r"(\d{4})[年](\d{1,2})[月](\d{1,2})[日]?"
        # 尝试提取正式日期格式
        dates = re.findall(date_pattern, text)
        if not dates:
            # 尝试 "自 X 至 Y" 格式
            m = re.search(r"自\s*([^\s]+)\s*至\s*([^\s]+)", text)
            if m:
                result.setdefault("start_date", m.group(1))
                result.setdefault("end_date", m.group(2))
        elif len(dates) >= 1:
            y, mth, d = dates[0]
            result.setdefault("start_date", f"{y}-{mth.zfill(2)}-{d.zfill(2)}")
            if len(dates) >= 2:
                y, mth, d = dates[1]
                result.setdefault("end_date", f"{y}-{mth.zfill(2)}-{d.zfill(2)}")

    # 姓名
    if "applicant" not in result:
        m = re.search(r"姓名[：:]\s*([\u4e00-\u9fa5]{2,4})", text)
        if m:
            result["applicant"] = m.group(1)

    # 学院
    if "college" not in result:
        m = re.search(r"([\u4e00-\u9fa5]{2,20}学院)", text)
        if m:
            result["college"] = m.group(1)

    # 班级
    if "class_name" not in result:
        m = re.search(r"([\u4e00-\u9fa50-9]{2,20}班)", text)
        if m:
            result["class_name"] = m.group(1)

    # 两个联系方式：优先 phone / advisor_phone
    phones = re.findall(r"1\d{10}", text)
    if phones:
        result.setdefault("phone", phones[0])
        if len(phones) > 1:
            result.setdefault("advisor_phone", phones[1])

    # 辅导员姓名
    if "advisor" not in result:
        m = re.search(r"辅导员[：:]\s*([\u4e00-\u9fa5]{2,4})", text)
        if m:
            result["advisor"] = m.group(1)

    # 去向
    if "destination" not in result:
        m = re.search(r"去向[：:]\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,30})", text)
        if m:
            result["destination"] = m.group(1)

    # 交通工具
    if "transportation" not in result:
        m = re.search(r"交通工具[：:]\s*([\u4e00-\u9fa5A-Za-z0-9-]{1,20})", text)
        if m:
            result["transportation"] = m.group(1)

    # 事由
    if "reason" not in result:
        m = re.search(r"事由[：:]\s*([^\n]{2,60})", text)
        if m:
            result["reason"] = m.group(1)

    # 金额（报销）
    if document_type == "reimbursement":
        amounts = re.findall(r"(\d+[.]?\d*)\s*元", text)
        if amounts:
            result["amount"] = amounts[0]

    return result if result else {"raw": text[:200]}


def _extract_reimbursement_fields_from_text(text: str) -> dict:
    """发票/报销场景兜底提取，避免多模态返回空字段。"""
    if not text:
        return {}

    result: dict[str, str] = {}

    m = re.search(r"发票号码\s*[：:]?\s*([0-9A-Za-z]{8,30})", text)
    if m:
        result["invoice_no"] = m.group(1)

    # 小写金额优先（如：小写 ¥228060.00）
    amount_patterns = [
        r"小写\s*[)）]?\s*[¥￥]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"价税合计[^\n]{0,20}[¥￥]\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"合\s*计[^\n]{0,20}[¥￥]\s*([0-9]+(?:\.[0-9]{1,2})?)",
    ]
    for p in amount_patterns:
        m = re.search(p, text)
        if m:
            result["amount"] = m.group(1)
            break

    m = re.search(r"开票日期\s*[：:]?\s*(\d{4})[年/-]?(\d{1,2})[月/-]?(\d{1,2})", text)
    if m:
        y, mon, day = m.groups()
        result["date"] = f"{y}-{mon.zfill(2)}-{day.zfill(2)}"

    m = re.search(r"项目名称\s*[：:]?\s*([^\n]{2,80})", text)
    if m:
        result["reason"] = m.group(1).strip()

    # 发票场景给一个默认类别，避免前端全空提示
    if result and "category" not in result:
        result["category"] = "其他"

    return result


def _postprocess_leave_fields(data: dict, raw_text: str) -> dict:
    """请假单字段兜底：从 OCR 原文补齐关键字段（包括 MiMo 推理文本）"""
    fixed = dict(data or {})

    # ── 两个联系方式：从 raw_text 中提取所有手机号 ──
    phones = re.findall(r"1\d{10}", raw_text or "")
    if phones:
        # 去重
        seen = set()
        uniq_phones = []
        for p in phones:
            if p not in seen:
                seen.add(p)
                uniq_phones.append(p)
        if not fixed.get("phone"):
            fixed["phone"] = uniq_phones[0]
        if len(uniq_phones) > 1 and not fixed.get("advisor_phone"):
            fixed["advisor_phone"] = uniq_phones[1]
        # 如果 advisor_phone 还是空但有第3个号码，也尝试
        if len(uniq_phones) > 2 and not fixed.get("advisor_phone"):
            fixed["advisor_phone"] = uniq_phones[1]
        if len(uniq_phones) > 2 and not fixed.get("parent_phone"):
            fixed["parent_phone"] = uniq_phones[2] if len(uniq_phones) > 2 else uniq_phones[1]

    # ── 学院 ──
    if not fixed.get("college"):
        m = re.search(r"([\u4e00-\u9fa5]{2,20}学院)", raw_text or "")
        if m:
            fixed["college"] = m.group(1)

    # ── 班级 ──
    if not fixed.get("class_name"):
        m = re.search(r"([\u4e00-\u9fa50-9]{2,20}班)", raw_text or "")
        if m:
            fixed["class_name"] = m.group(1)

    # ── 姓名（从 raw_text 提取 "姓名：XXX" 模式） ──
    if not fixed.get("applicant"):
        m = re.search(r"姓名[：:]\s*([\u4e00-\u9fa5]{2,4})", raw_text or "")
        if m:
            fixed["applicant"] = m.group(1)

    # ── 学号 ──
    if not fixed.get("student_id"):
        m = re.search(r"学号[：:]\s*(\d{6,15})", raw_text or "")
        if m:
            fixed["student_id"] = m.group(1)

    # ── 辅导员姓名 ──
    if not fixed.get("advisor"):
        m = re.search(r"辅导员[：:]\s*([\u4e00-\u9fa5]{2,4})", raw_text or "")
        if m:
            fixed["advisor"] = m.group(1)

    # ── 请假类型 ──
    if not fixed.get("leave_type"):
        for lt in ["事假", "病假", "公假"]:
            if lt in (raw_text or ""):
                fixed["leave_type"] = lt
                break

    # ── duration 拆分 ──
    duration_val = fixed.pop("duration", None) or fixed.pop("leave_period", None)
    if duration_val and isinstance(duration_val, str):
        m = re.search(r'自\s*(.+?)\s*至\s*(.+?)$', duration_val)
        if m:
            if not fixed.get("start_date"):
                fixed["start_date"] = m.group(1).strip()
            if not fixed.get("end_date"):
                fixed["end_date"] = m.group(2).strip()
        elif not fixed.get("start_date"):
            fixed["start_date"] = duration_val

    # ── 时间区间：多种模式从 raw_text 提取 ──
    if not fixed.get("start_date") or not fixed.get("end_date"):
        patterns = [
            r"请假时间[^\n]{0,80}?自\s*([^\s]+)\s*至\s*([^\s]+)",
            r"自\s*(\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)\s*至\s*(\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)",
            r"(\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)\s*[至到\-]\s*(\d{1,2}月\d{1,2}日\d{1,2}时\d{1,2}分)",
            r"自\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})",
        ]
        for pat in patterns:
            m = re.search(pat, raw_text or "")
            if m:
                if not fixed.get("start_date"):
                    fixed["start_date"] = m.group(1).strip()
                if not fixed.get("end_date"):
                    fixed["end_date"] = m.group(2).strip()
                break

    # ── 日期标准化：将中文日期转为 ISO 格式 (YYYY-MM-DDTHH:MM) ──
    def _normalize_date(val: str) -> str:
        """将各种日期格式转为 ISO datetime-local 兼容格式"""
        if not val:
            return val
        # 已是 ISO 格式：2026-05-26 或 2026-05-26T00:00
        if re.match(r'^\d{4}-\d{2}-\d{2}', val):
            if 'T' not in val:
                val += 'T00:00'
            return val
        # 中文格式：5月26日0时00分 / 5月26日 0时00分
        m = re.match(r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时(\d{1,2})分', val)
        if m:
            from datetime import datetime
            now = datetime.now()
            mon, day, hour, minu = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return f"{now.year:04d}-{mon:02d}-{day:02d}T{hour:02d}:{minu:02d}"
        # 其他格式原样返回
        return val

    for key in ("start_date", "end_date", "date"):
        if fixed.get(key):
            fixed[key] = _normalize_date(str(fixed[key]))

    # ── 去向 ──
    if not fixed.get("destination"):
        m = re.search(r"去向[：:]\s*([\u4e00-\u9fa5A-Za-z0-9]{2,30})", raw_text or "")
        if m:
            fixed["destination"] = m.group(1)

    # ── 交通工具 ──
    if not fixed.get("transportation"):
        m = re.search(r"交通工具[：:]\s*([\u4e00-\u9fa5A-Za-z0-9]{1,20})", raw_text or "")
        if m:
            fixed["transportation"] = m.group(1)

    # ── 请假事由 ──
    if not fixed.get("reason"):
        m = re.search(r"(?:请假事由|事由)[：:]\s*([^\n]{2,60})", raw_text or "")
        if m:
            fixed["reason"] = m.group(1).strip()

    return fixed


async def local_model_fill_json(raw_text: str, document_type: Optional[str] = None) -> dict:
    """调用本地推理服务将 OCR 文本填充为结构化 JSON"""
    from services.template_service import get_template

    tpl = get_template(document_type) if document_type else None
    fields_desc = ""
    if tpl:
        fields_desc = "\n".join([
            f"  - \"{f['key']}\": {f['label']} (类型: {f['type']})"
            for f in tpl.get("fields", [])
        ])

    prompt = f"""你是一个审批表单自动填写助手。根据 OCR 文本提取信息。

文档类型: {document_type or '未知'}
字段定义（用英文 key）:
{fields_desc if fields_desc else '按文本内容判断'}

OCR 文本:
{raw_text}

严格要求：
1. 你的整个回复必须是一个合法 JSON，以 {{ 开头、}} 结尾
2. 不要在 JSON 前后加任何解释、推理、代码块标记
3. 日期统一 YYYY-MM-DD，数字只保留数值不要单位
4. 无法确定的字段填 null
5. JSON key 必须用上面字段定义中的英文名

立即输出纯 JSON："""

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{LLAMA_SERVER_URL}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning_content") or "").strip()
            stop_reason = data["choices"][0].get("finish_reason", "")
            # 推理模型：content 可能是思考过程，reasoning_content 含 JSON，优先用后者
            if reasoning:
                content = reasoning
            # 如果模型输出被截断，尝试恢复
            if stop_reason == "length":
                logger.warning("本地模型输出可能被截断 (finish_reason=length)，尝试恢复 JSON")
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            if not content:
                raise ValueError("本地模型返回内容为空")

            # 尝试解析 JSON，如果截断则尝试修复
            try:
                result = json.loads(content)
            except json.JSONDecodeError as je:
                logger.warning(f"JSON 解析失败 (pos={je.pos})，尝试修复截断: {je}")
                # 在错误位置截断，尝试闭合未配对的括号
                fixed = content[:je.pos]
                # 去掉尾部不完整的 key-value（找到最后一个完整的逗号）
                last_comma = fixed.rfind(',')
                if last_comma > 0:
                    fixed = fixed[:last_comma]

                # 统计未闭合的括号
                open_braces = fixed.count('{') - fixed.count('}')
                open_brackets = fixed.count('[') - fixed.count(']')
                # 闭合适配的括号
                if open_brackets > 0:
                    fixed += '\n' + ']' * open_brackets
                if open_braces > 0:
                    fixed += '\n' + '}' * open_braces

                # 尝试多次修复（最多 3 次）
                for attempt in range(3):
                    try:
                        result = json.loads(fixed)
                        logger.info(f"JSON 修复成功 (尝试 {attempt + 1})")
                        break
                    except json.JSONDecodeError as e2:
                        if attempt == 0:
                            # 第二次尝试：移除尾部可能残留的逗号
                            fixed = fixed.rstrip().rstrip(',').rstrip()
                        elif attempt == 1:
                            # 第三次尝试：尝试包裹在一层大括号中
                            fixed = '{' + fixed + '}'
                        else:
                            raise je
                else:
                    raise je

            # 兜底归一化：如果模型仍然输出了中文字段名，映射为英文
            result = _normalize_json_keys(result)
            if document_type == "leave":
                result = _postprocess_leave_fields(result, raw_text)
            return result
    except Exception as e:
        logger.error(f"本地模型 JSON 填充失败: {e}")
        return {"error": "填充失败", "raw_text": raw_text}


# ========== PII 遮蔽检测 ==========

def _is_masked_output(text: str, filled: dict | None = None) -> bool:
    """
    检测 LLM 输出是否被隐私遮蔽（MiMo 等模型会将中文 PII 替换为 X）。
    判断标准：
      1. text 中连续 X 超过 6 个
      2. filled dict 中字符串类型的值超过 50% 是纯 X 串
    """
    if not text:
        return False
    # 去掉 JSON 语法字符后检查
    stripped = re.sub(r'[{}\[\]",:\s]', '', text)
    if len(stripped) < 10:
        return False
    # 连续 X 占比
    x_ratio = len(re.findall(r'X+', stripped)) / max(len(stripped), 1)
    if x_ratio > 0.4:
        return True
    # 检查 filled dict 的值
    if isinstance(filled, dict) and filled:
        str_values = [v for v in filled.values() if isinstance(v, str) and len(v) > 0]
        if str_values:
            x_count = sum(1 for v in str_values if re.fullmatch(r'X{3,}', v))
            if x_count / len(str_values) > 0.5:
                return True
    return False


# ========== 外部 LLM API ==========
async def llm_multimodal_ocr(
    image_bytes: bytes, api_base: str, api_key: str, model: str,
    document_type: Optional[str] = None,
) -> tuple[str, dict]:
    """多模态大模型：一步完成文字提取 + 结构化字段提取。
    返回 (raw_text, filled_dict)。"""
    from services.template_service import get_template
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"

    tpl = get_template(document_type) if document_type else None
    fields_desc = ""
    if tpl:
        fields_desc = "\n".join([
            f'  - "{f["key"]}": {f["label"]}'
            + (f' (选项: {",".join(f["options"])})' if f.get("options") else "")
            for f in tpl.get("fields", [])
        ])

    # 构建字段提取的字段描述和示例
    example_json = '{"applicant": "张三", "college": "计算机学院"}'
    if tpl:
        example_items = []
        for f in tpl.get("fields", [])[:3]:
            example_items.append(f'    "{f["key"]}": "示例值"')
        example_json = "{\n" + ",\n".join(example_items) + "\n  }"

    prompt = f"""你是一个审批表单处理助手。从图片中提取表单字段。

图片内容是：{document_type or '一张审批表单'}

需要的字段（用英文 key，值从图片中提取）：
{fields_desc if fields_desc else '从图片中识别'}

严格要求：
1. 你的整个回复必须是一个合法的 JSON 对象，以 {{ 开头、以 }} 结尾
2. 不要在 JSON 前后添加任何解释、推理过程、代码块标记
3. 日期格式 YYYY-MM-DD（如 2026-05-26）
4. 数字只保留数值，不要单位（如 500 而不是 500元）
5. 找不到的字段填 null，不要编造
6. 值必须从图片中真实提取

输出示例：
{example_json}

立即输出纯 JSON："""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }],
                "temperature": 0.05,
                "max_tokens": 32768,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()
        # 诊断日志：记录 MiMo 返回了什么
        logger.info(
            f"MiMo 响应: content_len={len(content)}, reasoning_len={len(reasoning)}, "
            f"content_preview={content[:150]}, reasoning_preview={reasoning[:150]}"
        )
        # 推理模型（MiMo/DeepSeek-R1 等）可能把真实答案放在 reasoning_content 中，
        # content 只放了推理过程。优先取 reasoning_content 中能解析成 JSON 的部分
        raw_text = content if content else reasoning  # 默认
        filled: dict = {}
        candidates_texts = [content, reasoning]  # 两个都试

        # 辅助函数：修复 MiMo 常见的 JSON 语法错误
        def _repair_json(text: str) -> str:
            """修复 LLM 输出中常见的 JSON 格式错误。"""
            # 1. 移除尾随逗号（在 } 或 ] 之前）
            text = re.sub(r',\s*}', '}', text)
            text = re.sub(r',\s*]', ']', text)
            # 2. 修复 "key": , → "key": null
            text = re.sub(r':\s*,', ': null,', text)
            text = re.sub(r':\s*}', ': null}', text)
            # 3. 修复 "key": ] → "key": []
            text = re.sub(r':\s*]', ': []', text)
            # 4. 修复连续逗号
            text = re.sub(r',\s*,', ', null,', text)
            # 5. 修复缺少引号的 key（简单情况）
            # 6. 修复截断的字符串：如果最后一个 " 后面没有闭合
            return text

        # 辅助函数：从文本中提取最后一个完整 JSON 对象（支持嵌套）
        def _extract_last_json(text: str) -> dict | None:
            if not text:
                return None
            # 优先：查找 ```json ... ``` 代码块（取最后一个）
            json_blocks = list(re.finditer(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL))
            for m in reversed(json_blocks):
                try:
                    parsed = json.loads(m.group(1).strip())
                    if isinstance(parsed, dict) and len(parsed) >= 1:
                        return parsed
                except json.JSONDecodeError:
                    continue
            # 兜底：平衡括号匹配，从最后一个 { 开始找配对的 }
            # 从后往前扫，找到第一个有效 JSON 对象
            braces = [(i, c) for i, c in enumerate(text) if c in '{}']
            # 从最后一个 { 开始尝试
            open_positions = [i for i, c in braces if c == '{']
            for start_pos in reversed(open_positions):
                depth = 0
                end_pos = -1
                for i, c in braces:
                    if i < start_pos:
                        continue
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end_pos = i
                            break
                if end_pos > start_pos:
                    candidate = text[start_pos:end_pos + 1]
                    # 先尝试原始解析，失败则修复后重试
                    for cand in [candidate, _repair_json(candidate)]:
                        try:
                            parsed = json.loads(cand)
                            if isinstance(parsed, dict) and len(parsed) >= 1:
                                return parsed
                        except json.JSONDecodeError:
                            continue
            return None

        # 尝试从两个候选文本中提取
        for ct in candidates_texts:
            if not ct:
                continue
            # Step 1: 去掉 markdown 代码块标记后直接解析
            cleaned = ct.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]

            # Step 2: 尝试直接解析完整文本（含 JSON 修复）
            for attempt in [cleaned.strip(), ct.strip()]:
                if not attempt:
                    continue
                # 先尝试原始解析
                try:
                    parsed = json.loads(attempt)
                    if isinstance(parsed, dict):
                        filled = parsed
                        raw_text = ct
                        break
                except json.JSONDecodeError:
                    pass
                # 修复后再试
                repaired = _repair_json(attempt)
                try:
                    parsed = json.loads(repaired)
                    if isinstance(parsed, dict):
                        logger.info(f"JSON 修复成功: 原始错误已自动修正")
                        filled = parsed
                        raw_text = ct
                        break
                except json.JSONDecodeError:
                    pass
            if filled:
                break

            # Step 3: 使用平衡括号提取最后一个 JSON（兜底）
            parsed = _extract_last_json(ct)
            if parsed and len(parsed) >= 1:
                filled = parsed
                raw_text = ct
                break

    # 归一化字段名
    filled = _normalize_json_keys(filled)

    # ★★★ 将 content + reasoning 合并为 raw_text，供后续正则兜底提取 ★★★
    # MiMo 等推理模型的 JSON 在 content 中，但原始 OCR 文字在 reasoning 中
    combined_text = "\n".join([t for t in [content, reasoning] if t and t.strip()])
    if combined_text and len(combined_text) > len(raw_text):
        raw_text = combined_text

    # 发票/报销场景兜底：即使模型未按 schema 返回，也尽量抽取关键字段
    if not filled or not any(v not in (None, "") for v in filled.values()):
        reimburse_fallback = _extract_reimbursement_fields_from_text("\n".join([content, reasoning]))
        if reimburse_fallback:
            filled.update(reimburse_fallback)
            raw_text = "\n".join([content, reasoning]).strip() or raw_text

    # ★ 检测 PII 遮蔽输出（MiMo 等模型的隐私过滤）
    if _is_masked_output(raw_text, filled):
        logger.warning(
            f"检测到 LLM 返回遮蔽内容 (model={model})，"
            f"text_preview={str(raw_text)[:120]}，触发降级"
        )
        raise ValueError(f"LLM 返回了隐私遮蔽内容，可能是 MiMo 模型的 PII masking 导致")

    return raw_text, filled


async def llm_api_fill_json(raw_text: str, api_base: str, api_key: str, model: str,
                            document_type: Optional[str] = None) -> dict:
    """调用外部 LLM API 将 OCR 文本填充为结构化 JSON（两步流）"""
    from services.template_service import get_template

    tpl = get_template(document_type) if document_type else None
    fields_desc = ""
    if tpl:
        fields_desc = "\n".join([
            f"  - \"{f['key']}\": {f['label']} (类型: {f['type']})"
            for f in tpl.get("fields", [])
        ])

    prompt = f"""你是一个审批表单自动填写助手。根据 OCR 文本提取信息。

文档类型: {document_type or '未知'}
字段定义（用英文 key）:
{fields_desc if fields_desc else '按文本内容判断'}

OCR 文本:
{raw_text}

严格要求：
1. 你的整个回复必须是一个合法 JSON，以 {{ 开头、}} 结尾
2. 不要在 JSON 前后加任何解释、推理、代码块标记
3. 日期统一 YYYY-MM-DD，数字只保留数值不要单位
4. 无法确定的字段填 null
5. JSON key 必须用上面字段定义中的英文名

立即输出纯 JSON："""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()
        # 推理模型 JSON 通常在 reasoning_content，优先用它
        if reasoning:
            content = reasoning
        # 清理代码块标记
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = content.strip()
        if not content:
            raise ValueError("LLM 返回内容为空")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as je:
            logger.warning(f"外部 LLM JSON 填充解析失败: {je}，content={content[:200]}")
            # 尝试从 content 中提取 JSON 片段
            m = re.search(r'\{[^{}]*\}', content)
            if m:
                try:
                    result = json.loads(m.group(0))
                except json.JSONDecodeError:
                    raise ValueError(f"LLM 返回了无效 JSON: {je}")
            else:
                raise ValueError(f"LLM 返回了无效 JSON: {je}")
        result = _normalize_json_keys(result)
        
        # 检测遮蔽输出
        if _is_masked_output(raw_text, result):
            logger.warning(f"检测到 LLM 填充返回遮蔽内容 (model={model})，触发降级")
            raise ValueError("LLM 填充返回了隐私遮蔽内容")
        
        if document_type == "leave":
            result = _postprocess_leave_fields(result, raw_text)
        return result


# ========== 主路由 ==========
async def ocr_with_tier(
    image_bytes: bytes,
    tier: str,
    llm_quota_remaining: int,
    mime_type: str = "",
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    fill_api_base: str = "",
    fill_api_key: str = "",
    fill_model: str = "",
) -> tuple[str, str, Optional[dict]]:
    if mime_type == "application/pdf":
        raw, filled, is_scanned = await pdf_text_ocr(image_bytes, fill_api_key, fill_api_base, fill_model)

        # 文字型 PDF：直接返回
        if not is_scanned:
            return raw, OCRProvider.PDF_TEXT, filled

        # 扫描件 PDF：提取首页为图片，走图片 OCR 流程
        logger.info("PDF 为扫描件，提取首页图片进行 OCR")
        try:
            image_bytes = pdf_page_to_image(image_bytes, page_index=0)
        except Exception as e:
            logger.error(f"PDF 转图片失败: {e}")
            raise ValueError("无法处理此 PDF：文本层为空且转图片失败") from e

        # 扫描件继续走下面的图片 OCR 逻辑（不 return）

    if tier == "free":
        raw = local_easyocr(image_bytes)
        try:
            filled = await local_model_fill_json(raw)
            if filled and "error" not in str(filled):
                filled = _normalize_json_keys(filled)
        except Exception:
            filled = None
        return raw, OCRProvider.LOCAL, filled

    # Pro / Pro+: 优先尝试外部 LLM
    if tier in ("pro", "pro_plus"):
        if tier == "pro" and llm_quota_remaining <= 0:
            logger.warning("LLM 配额用尽，降级本地")
            raw = local_easyocr(image_bytes)
            filled = await _fill_with_best(raw, fill_api_key, fill_api_base, fill_model)
            return raw, OCRProvider.LOCAL, filled

        have_multimodal = bool(api_key)  # 有多模态 Key 才走一步到位

        if have_multimodal:
            # 直接交给多模态 LLM，无需 EasyOCR 预扫（多模态模型自己能识别文档类型）
            try:
                raw, filled = await llm_multimodal_ocr(
                    image_bytes, api_base, api_key, model, document_type=None,
                )
                doc_type = detect_document_type(raw)
                if not doc_type:
                    # raw 可能是 JSON 文本，补做发票字段级兜底提取
                    fallback_fields = _extract_reimbursement_fields_from_text(raw)
                    if fallback_fields:
                        filled = {**fallback_fields, **(filled or {})}
                # 如果多模态返回了空 JSON，降级走文本填充
                if not filled or all(v in (None, "") for v in filled.values()):
                    logger.warning("多模态返回空 JSON，降级 EasyOCR + 外部填充")
                    raise ValueError("多模态返回空")
                # leave 后处理辅助
                if doc_type == "leave" and filled:
                    filled = _postprocess_leave_fields(filled, raw)
                return raw, OCRProvider.LLM, filled
            except Exception as e:
                logger.warning(f"多模态 LLM OCR 失败: {e}，降级 EasyOCR + 外部填充")
                raw = local_easyocr(image_bytes)
                filled = await _fill_with_best(raw, fill_api_key, fill_api_base, fill_model, document_type=detect_document_type(raw))
                return raw, OCRProvider.LOCAL, filled

        # 无多模态 Key：EasyOCR + 外部 LLM 填充
        raw = local_easyocr(image_bytes)
        filled = await _fill_with_best(raw, fill_api_key, fill_api_base, fill_model)
        return raw, OCRProvider.LOCAL, filled

    # free / 其他：EasyOCR + 本地模型填充
    raw = local_easyocr(image_bytes)
    try:
        filled = await local_model_fill_json(raw)
        if filled and "error" not in str(filled):
            filled = _normalize_json_keys(filled)
    except Exception:
        filled = None
    return raw, OCRProvider.LOCAL, filled


async def _fill_with_best(
    raw_text: str,
    fill_api_key: str = "",
    fill_api_base: str = "",
    fill_model: str = "",
    document_type: Optional[str] = None,
) -> Optional[dict]:
    """选择最佳填充方式：优先外部 LLM，失败则降级本地模型"""
    # 1. 尝试外部 LLM 填充
    if fill_api_key:
        try:
            filled = await llm_api_fill_json(
                raw_text, fill_api_base, fill_api_key, fill_model,
                document_type=document_type,
            )
            if filled and "error" not in str(filled):
                filled = _normalize_json_keys(filled)
                logger.info(f"外部 LLM ({fill_model}) 填充成功")
                return filled
        except Exception as e:
            logger.warning(f"外部 LLM 填充失败: {e}，降级本地模型")

    # 2. 降级本地模型
    try:
        filled = await local_model_fill_json(raw_text, document_type=document_type)
        if filled and "error" not in str(filled):
            filled = _normalize_json_keys(filled)
            return filled
    except Exception as e:
        logger.error(f"本地模型 JSON 填充失败: {e}")

    return None
