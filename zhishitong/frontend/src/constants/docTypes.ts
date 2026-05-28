// 文档类型中文名映射
export const DOC_TYPE_LABELS: Record<string, string> = {
  reimbursement: '💰 报销申请',
  leave: '📝 请假申请',
  club_application: '🎉 社团活动申请',
  classroom_booking: '🏫 教室借用',
  business_trip: '✈️ 出差申请',
  seal_application: '🔖 用章申请',
  dorm_change: '🏠 宿舍调换',
  scholarship: '🏆 奖学金申请',
  suspend_resume: '🎓 休学/复学',
  enrollment_proof: '📄 在读证明',
  abroad_application: '🌍 因公出国',
  onboarding: '💼 入职报到',
  office_supplies: '🖊️ 办公用品领用',
  book_purchase: '📚 图书采购',
}

// 纯文本（无 emoji）
const DOC_LABEL_TEXT: Record<string, string> = {
  reimbursement: '报销申请', leave: '请假申请', club_application: '社团活动申请',
  classroom_booking: '教室借用', business_trip: '出差申请',
  seal_application: '用章申请', dorm_change: '宿舍调换', scholarship: '奖学金申请',
  suspend_resume: '休学/复学', enrollment_proof: '在读证明',
  abroad_application: '因公出国', onboarding: '入职报到',
  office_supplies: '办公用品领用', book_purchase: '图书采购',
}

// emoji 图标
const DOC_ICON: Record<string, string> = {
  reimbursement: '💰', leave: '📝', club_application: '🎉',
  classroom_booking: '🏫', business_trip: '✈️',
  seal_application: '🔖', dorm_change: '🏠', scholarship: '🏆',
  suspend_resume: '🎓', enrollment_proof: '📄',
  abroad_application: '🌍', onboarding: '💼',
  office_supplies: '🖊️', book_purchase: '📚',
}

export const getDocTypeLabel = (key: string | null | undefined): string => {
  if (!key) return '未知'
  return DOC_TYPE_LABELS[key] || key
}

export const getDocLabel = (key: string | null | undefined): string => {
  if (!key) return '未知事务'
  return DOC_LABEL_TEXT[key] || key
}

export const getDocIcon = (key: string | null | undefined): string => {
  if (!key) return '📋'
  return DOC_ICON[key] || '📋'
}

export const VALID_DOC_TYPES = Object.keys(DOC_TYPE_LABELS)
