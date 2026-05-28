import React from 'react'
import { WORKFLOW_STAGES, FALLBACK_STAGES } from '../utils/constants'

interface Props {
  currentStage: string
  documentType?: string | null
}

export default function ApprovalProgressBar({ currentStage, documentType }: Props) {
  const stages = (documentType && WORKFLOW_STAGES[documentType]) || FALLBACK_STAGES
  const currentIdx = stages.findIndex(s => s.key === currentStage)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, flexWrap: 'wrap' }}>
      {stages.map((s, i) => {
        let bg = 'var(--divider)'
        let color = 'var(--text-secondary)'
        if (i < currentIdx) { bg = '#34C759'; color = '#34C759' }
        else if (i === currentIdx) { bg = 'var(--accent-color)'; color = 'var(--accent-color)' }
        return (
          <React.Fragment key={s.key}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: bg,
              display: 'inline-block', flexShrink: 0,
            }} />
            <span style={{ color, fontWeight: i === currentIdx ? 600 : 400 }}>{s.label}</span>
            {i < stages.length - 1 && (
              <span style={{ color: 'var(--divider)', margin: '0 2px' }}>→</span>
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}
