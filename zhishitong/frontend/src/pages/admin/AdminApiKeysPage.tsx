import React, { useEffect, useState } from 'react'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'

// ===== 供应商预设 =====
const PRESETS: Record<string, { label: string; api_base: string; ocr_models: string[]; fill_models: string[]; llm_models: string[] }> = {
  aliyun: {
    label: '阿里百炼',
    api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    ocr_models: ['qwen3.6-plus', 'qwen3.6-flash', 'qwen-vl-ocr'],
    fill_models: ['qwen3.7-max', 'qwen3.6-plus', 'qwen3.6-flash'],
    llm_models: ['qwen3.7-max', 'qwen3.6-plus', 'qwen3.6-flash'],
  },
  volc: {
    label: '火山引擎（模型ID请按控制台）',
    api_base: 'https://ark.cn-beijing.volces.com/api/v3',
    ocr_models: [], fill_models: [], llm_models: [],
  },
  deepseek: {
    label: 'DeepSeek',
    api_base: 'https://api.deepseek.com/v1',
    ocr_models: [],
    fill_models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
    llm_models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
  },
  zhipu: {
    label: '智谱AI',
    api_base: 'https://open.bigmodel.cn/api/paas/v4',
    ocr_models: ['glm-5v-turbo', 'glm-4.6v', 'glm-ocr'],
    fill_models: ['glm-5.1', 'glm-5', 'glm-4.7'],
    llm_models: ['glm-5.1', 'glm-5', 'glm-4.7'],
  },
  baidu: {
    label: '百度千帆（模型ID请按控制台）',
    api_base: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop',
    ocr_models: [], fill_models: [], llm_models: [],
  },
  mimo: {
    label: '小米 MiMo',
    api_base: 'https://api.xiaomimimo.com/v1',
    ocr_models: ['mimo-v2.5', 'mimo-v2.5-pro', 'mimo-v2-omni'],
    fill_models: ['mimo-v2.5', 'mimo-v2.5-pro', 'mimo-v2-pro'],
    llm_models: ['mimo-v2.5', 'mimo-v2.5-pro', 'mimo-v2-pro'],
  },
  custom: {
    label: '自定义',
    api_base: '',
    ocr_models: [], fill_models: [], llm_models: [],
  },
}

export default function AdminApiKeysPage() {
  const [ocrKeys, setOcrKeys] = useState<any[]>([])
  const [fillKeys, setFillKeys] = useState<any[]>([])
  const [llmKeys, setLlmKeys] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState<'ocr' | 'fill' | 'llm' | null>(null)
  const [provider, setProvider] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [apiKeyPlain, setApiKeyPlain] = useState('')
  const [model, setModel] = useState('')
  const [note, setNote] = useState('')

  const fetch = async () => {
    const [ocr, fill, llm] = await Promise.all([
      axios.get('/api/admin/api-keys?key_type=ocr').then(r => r.data).catch(() => []),
      axios.get('/api/admin/api-keys?key_type=json_fill').then(r => r.data).catch(() => []),
      axios.get('/api/admin/api-keys?key_type=llm').then(r => r.data).catch(() => []),
    ])
    setOcrKeys(ocr); setFillKeys(fill); setLlmKeys(llm)
  }
  useEffect(() => { fetch() }, [])

  const handleProviderChange = (p: string) => {
    setProvider(p)
    const preset = PRESETS[p]
    if (preset) {
      setApiBase(preset.api_base)
      setModel('')
    }
  }

  const resetForm = () => {
    setProvider('')
    setApiBase('')
    setApiKeyPlain('')
    setModel('')
    setNote('')
    setShowAdd(null)
  }

  const addKey = async (keyType: string) => {
    if (!provider || !apiKeyPlain) { alert('请选择供应商并填写 API Key'); return }
    if (!model) { alert('请选择模型'); return }
    // DeepSeek 无视觉能力，阻止误添加为 OCR Key
    if (keyType === 'ocr' && provider === 'deepseek') {
      if (!confirm('⚠️ DeepSeek 模型不支持图片识别（多模态），用于 OCR 会返回 400 错误。\n\n确定仍要添加？')) return
    }
    try {
      await axios.post('/api/admin/api-keys', {
        key_type: keyType, provider, api_base: apiBase,
        api_key_plain: apiKeyPlain, default_model: model, note,
      })
      alert('✅ Key 添加成功')
      resetForm()
      fetch()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '添加失败，请检查网络连接'
      alert('❌ ' + msg)
    }
  }

  const disableKey = async (id: number) => {
    if (!confirm('确认停用该 Key？停用后仍可重新启用。')) return
    try {
      await axios.delete(`/api/admin/api-keys/${id}`)
      fetch()
    } catch (e: any) {
      alert('❌ ' + (e?.response?.data?.detail || e?.message || '操作失败'))
    }
  }

  const restoreKey = async (id: number) => {
    if (!confirm('确认重新启用该 Key？')) return
    try {
      await axios.put(`/api/admin/api-keys/${id}/restore`)
      fetch()
    } catch (e: any) {
      alert('❌ ' + (e?.response?.data?.detail || e?.message || '操作失败'))
    }
  }

  const hardDeleteKey = async (id: number, info: string) => {
    if (!confirm(`⚠️ 确认永久删除 Key「${info}」？\n\n此操作不可恢复，密文将彻底销毁。`)) return
    try {
      await axios.delete(`/api/admin/api-keys/${id}/hard`)
      alert('✅ Key 已永久删除')
      fetch()
    } catch (e: any) {
      alert('❌ ' + (e?.response?.data?.detail || e?.message || '操作失败'))
    }
  }

  const modelOptions = provider
    ? (showAdd === 'ocr' ? PRESETS[provider]?.ocr_models
      : showAdd === 'llm' ? PRESETS[provider]?.llm_models
      : PRESETS[provider]?.fill_models) || []
    : []

  const renderTable = (keys: any[]) => (
    <div className="glass-table-wrapper">
      <table className="glass-table">
        <thead>
          <tr>
            <th>服务商</th>
            <th>模型</th>
            <th>状态</th>
            <th>用量</th>
            <th>备注</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {keys.length === 0 ? (
            <tr><td colSpan={6} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>暂无 Key</td></tr>
          ) : keys.map(k => (
            <tr key={k.id}>
              <td>
                <div style={{ fontWeight: 500 }}>{k.provider}</div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' }}>{k.api_base}</div>
              </td>
              <td>{k.default_model}</td>
              <td>
                <span className={k.is_active ? 'glass-tag glass-tag-green' : 'glass-tag glass-tag-red'}>
                  {k.is_active ? '🟢 正常' : '🔴 停用'}
                </span>
                {k.fail_count > 0 && (
                  <span style={{ fontSize: 10, color: 'var(--orange)', marginLeft: 4 }}>
                    失败×{k.fail_count}
                  </span>
                )}
              </td>
              <td style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                {k.usage_count?.toLocaleString() || 0} 次
              </td>
              <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{k.note || '—'}</td>
              <td style={{ whiteSpace: 'nowrap' }}>
                {k.is_active ? (
                  <>
                    <button onClick={() => disableKey(k.id)} className="glass-btn glass-btn-outline glass-btn-sm" style={{ marginRight: 4, color: 'var(--orange)', borderColor: 'var(--orange)' }}>停用</button>
                    <button onClick={() => hardDeleteKey(k.id, `${k.provider}/${k.default_model}`)} className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => restoreKey(k.id)} className="glass-btn glass-btn-success glass-btn-sm" style={{ marginRight: 4 }}>启用</button>
                    <button onClick={() => hardDeleteKey(k.id, `${k.provider}/${k.default_model}`)} className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  const addForm = (keyType: string) => (
    <GlassCard size="sm" style={{ marginTop: 12, background: 'var(--glass-bg)' }}>
      {/* 1. 选择供应商 */}
      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>① 选择供应商</label>
        <select value={provider} onChange={e => handleProviderChange(e.target.value)} className="glass-input">
          <option value="">-- 请选择 --</option>
          {Object.entries(PRESETS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </div>

      {/* 2. API Base URL */}
      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', fontSize: 12, color: '#888', marginBottom: 4 }}>② API 地址</label>
        <input value={apiBase} onChange={e => setApiBase(e.target.value)} className="glass-input"
          placeholder={provider === 'custom' ? '输入自定义 API 地址' : '已自动填充'} />
      </div>

      {/* 3. API Key */}
      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>③ API Key</label>
        <input type="password" value={apiKeyPlain} onChange={e => setApiKeyPlain(e.target.value)}
          placeholder="输入 API Key" className="glass-input" />
      </div>

      {/* 4. 选择模型 */}
      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          ④ 选择模型 {keyType === 'ocr' ? '(多模态 OCR)' : keyType === 'llm' ? '(AI 服务)' : '(JSON 填充)'}
        </label>
        {modelOptions.length > 0 ? (
          <select value={model} onChange={e => setModel(e.target.value)} className="glass-input">
            <option value="">-- 请选择模型 --</option>
            {modelOptions.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        ) : (
          <input value={model} onChange={e => setModel(e.target.value)}
            placeholder={provider ? '当前供应商无可选项，手动输入' : '先选择供应商'} className="glass-input" />
        )}
        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-tertiary)' }}>
          提示：部分供应商模型更新频繁，请以官方控制台/API文档中的最新模型 ID 为准。
        </div>
      </div>

      {/* 5. 备注 */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>备注（可选）</label>
        <input value={note} onChange={e => setNote(e.target.value)} placeholder="如：经费账号-张三" className="glass-input" />
      </div>

      <div>
        <button onClick={() => addKey(keyType)} className="glass-btn" style={{ marginRight: 8 }}>✅ 确认添加</button>
        <button onClick={resetForm} className="glass-btn glass-btn-outline">取消</button>
      </div>
    </GlassCard>
  )

  return (
    <div>
      <h1 className="page-title">API Key 管理</h1>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      <GlassCard strong>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', rowGap: 6, marginBottom: 12 }}>
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>📷 OCR 专用 Keys（多模态模型，用于识别图片）</h2>
            <div style={{ fontSize: 11, color: 'var(--orange)', marginTop: 2 }}>
              ⚠️ 仅支持视觉/多模态模型（如 MIMO、GPT-4o、Qwen-VL），纯文本模型会返回 400 错误
            </div>
          </div>
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{ocrKeys.length} / 100</span>
        </div>
        {renderTable(ocrKeys)}
        {showAdd === 'ocr' ? addForm('ocr') : (
          <button onClick={() => setShowAdd('ocr')} className="glass-btn glass-btn-outline" style={{ marginTop: 12, borderStyle: 'dashed', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
            + 添加 OCR Key
          </button>
        )}
      </GlassCard>

      <GlassCard strong>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', rowGap: 6, marginBottom: 12 }}>
          <h2 className="section-title" style={{ margin: 0 }}>✍️ JSON 填充专用 Keys（对话模型，用于结构化填写）</h2>
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{fillKeys.length} / 100</span>
        </div>
        {renderTable(fillKeys)}
        {showAdd === 'fill' ? addForm('json_fill') : (
          <button onClick={() => setShowAdd('fill')} className="glass-btn glass-btn-outline" style={{ marginTop: 12, borderStyle: 'dashed', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
            + 添加填充 Key
          </button>
        )}
      </GlassCard>
      <GlassCard strong>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', rowGap: 6, marginBottom: 12 }}>
          <h2 className="section-title" style={{ margin: 0 }}>🤖 AI 服务 Keys（RAG 合规分析 / 意图识别 / 意见生成）</h2>
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{llmKeys.length} / 100</span>
        </div>
        {renderTable(llmKeys)}
        {showAdd === 'llm' ? addForm('llm') : (
          <button onClick={() => setShowAdd('llm')} className="glass-btn glass-btn-outline" style={{ marginTop: 12, borderStyle: 'dashed', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
            + 添加 AI Key
          </button>
        )}
      </GlassCard>
      </div>
    </div>
  )
}
