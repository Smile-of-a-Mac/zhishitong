/** 共享 UI 常量（STATUS_LABELS / STAGE_LABELS 等） */

export const STATUS_LABELS: Record<string, string> = {
  pending: '⏳ 待审批',
  approved: '✅ 已通过',
  rejected: '❌ 不通过',
  needs_revision: '📝 需修改',
  cancelled: '⊘ 申请已取消',
  withdrawn: '↩️ 已撤回',
}

export const STAGE_LABELS: Record<string, string> = {
  dept_review: '📋 部门审批',
  finance_review: '💰 财务审批',
  school_review: '🏫 学校审批',
  completed: '✅ 已完成',
}

/** 各文档类型的审批阶段 */
export const WORKFLOW_STAGES: Record<string, { key: string; label: string }[]> = {
  reimbursement: [
    { key: 'dept_review', label: '部门审核' },
    { key: 'finance_review', label: '财务审核' },
    { key: 'school_review', label: '学校审核' },
  ],
  leave: [
    { key: 'dept_review', label: '辅导员审核' },
  ],
  club_application: [
    { key: 'dept_review', label: '学院审核' },
    { key: 'school_review', label: '团委审核' },
  ],
}

export const FALLBACK_STAGES = [
  { key: 'dept_review', label: '部门审核' },
  { key: 'school_review', label: '上级审核' },
]
