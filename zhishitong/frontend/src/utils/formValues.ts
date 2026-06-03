export interface FormTemplateField {
  key: string
  type: string
}

export interface FormTemplate {
  key: string
  fields: FormTemplateField[]
}

export function normalizeFormInputValue(
  key: string,
  value: string,
  docType: string,
  templates: FormTemplate[],
) {
  const tpl = templates.find(t => t.key === docType)
  const field = tpl?.fields.find(f => f.key === key)
  const expectsDateTime = field?.type === 'datetime' || (docType === 'leave' && ['start_date', 'end_date'].includes(key))
  if (expectsDateTime && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return `${value}T00:00`
  }
  return value
}

export function normalizeFormInputValues(
  fields: Record<string, string>,
  docType: string,
  templates: FormTemplate[],
) {
  const normalized: Record<string, string> = {}
  for (const [key, value] of Object.entries(fields)) {
    normalized[key] = normalizeFormInputValue(key, String(value ?? ''), docType, templates)
  }
  return normalized
}
