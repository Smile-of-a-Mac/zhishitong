export const APPROVAL_STATUS = {
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  NEEDS_REVISION: 'needs_revision',
  CANCELLED: 'cancelled',
  WITHDRAWN: 'withdrawn',
} as const

export type ApprovalStatus = (typeof APPROVAL_STATUS)[keyof typeof APPROVAL_STATUS]

/** 状态中文标签映射 */
export const APPROVAL_STATUS_LABEL: Record<string, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  needs_revision: '需修改',
  cancelled: '已取消',
  withdrawn: '已撤回',
}

/** 带 emoji 的状态标签 */
export const APPROVAL_STATUS_EMOJI: Record<string, string> = {
  pending: '⏳ 待审批',
  approved: '✅ 已通过',
  rejected: '❌ 退回',
  needs_revision: '📝 需修改',
  cancelled: '⊘ 已取消',
  withdrawn: '↩️ 已撤回',
}
