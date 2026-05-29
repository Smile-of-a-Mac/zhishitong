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
    "contact_info": "phone", "联系电话": "phone",
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
    """请假单字段兜底：从 OCR 原文补齐关键字段"""
    fixed = dict(data or {})

    # 两个联系方式：优先填充 phone / advisor_phone
    phones = re.findall(r"1\d{10}", raw_text or "")
    if phones:
        if not fixed.get("phone"):
            fixed["phone"] = phones[0]
        if len(phones) > 1 and not fixed.get("advisor_phone"):
            fixed["advisor_phone"] = phones[1]

    # 学院（示例：安全与环境工程学院）
    if not fixed.get("college"):
        m = re.search(r"([\u4e00-\u9fa5]{2,20}学院)", raw_text or "")
        if m:
            fixed["college"] = m.group(1)

    # 班级（示例：硕研25级2班）
    if not fixed.get("class_name"):
        m = re.search(r"([\u4e00-\u9fa50-9]{2,20}班)", raw_text or "")
        if m:
            fixed["class_name"] = m.group(1)

    # 时间区间（请假时间 自 X 至 Y）
    if not fixed.get("start_date") or not fixed.get("end_date"):
        m = re.search(r"请假时间[^\n]{0,80}?自\s*([^\s]+)\s*至\s*([^\s]+)", raw_text or "")
        if m:
            fixed.setdefault("start_date", m.group(1))
            fixed.setdefault("end_date", m.group(2))

    # 去向
    if not fixed.get("destination"):
        m = re.search(r"去向\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,30})", raw_text or "")
        if m:
            fixed["destination"] = m.group(1)

    # 交通工具
    if not fixed.get("transportation"):
        m = re.search(r"交通工具\s*([\u4e00-\u9fa5A-Za-z0-9-]{1,20})", raw_text or "")
        if m:
            fixed["transportation"] = m.group(1)

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
                "max_tokens": 4096,
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
        raw_text = content  # 默认
        filled: dict = {}
        candidates_texts = [content, reasoning]  # 两个都试

        for ct in candidates_texts:
            if not ct:
                continue
            # Step 1: 去掉 markdown 代码块标记
            cleaned = ct.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]

            # Step 2: 尝试直接解析
            for attempt in [cleaned.strip(), ct.strip()]:
                if not attempt:
                    continue
                try:
                    parsed = json.loads(attempt)
                    if isinstance(parsed, dict):
                        filled = parsed
                        raw_text = ct
                        break
                except json.JSONDecodeError:
                    pass
            if filled:
                break

        # Step 3: 正则找 JSON 对象（兜底）
        if not filled:
            for ct in candidates_texts:
                if not ct:
                    continue
                import re as _re
                candidates = list(_re.finditer(r'\{[^{}]*\}', ct))
                for m in reversed(candidates):
                    try:
                        parsed = json.loads(m.group(0))
                        if isinstance(parsed, dict) and len(parsed) >= 1:
                            filled = parsed
                            raw_text = ct
                            break
                    except json.JSONDecodeError:
                        continue
                if filled:
                    break

    # 归一化字段名
    filled = _normalize_json_keys(filled)

    # 发票/报销场景兜底：即使模型未按 schema 返回，也尽量抽取关键字段
    if not filled or not any(v not in (None, "") for v in filled.values()):
        reimburse_fallback = _extract_reimbursement_fields_from_text("\n".join([content, reasoning]))
        if reimburse_fallback:
            filled.update(reimburse_fallback)
            raw_text = "\n".join([content, reasoning]).strip() or raw_text

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
        result = json.loads(content)
        result = _normalize_json_keys(result)
        if document_type == "leave":
            result = _postprocess_leave_fields(result, raw_text)
        return result


# ========== 主路由 ==========
async def ocr_with_tier(
    image_bytes: bytes,
    tier: str,
    llm_quota_remaining: int,
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    fill_api_base: str = "",
    fill_api_key: str = "",
    fill_model: str = "",
) -> tuple[str, str, Optional[dict]]:
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
