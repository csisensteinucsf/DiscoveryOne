const sameTemplateId = (left, right) => String(left) === String(right)

export function reorderCaseTemplates(templates = [], sourceId, targetId, placement = 'before') {
  const sourceIndex = templates.findIndex(template => sameTemplateId(template.id, sourceId))
  if (sourceIndex < 0 || !templates.some(template => sameTemplateId(template.id, targetId))) {
    return [...templates]
  }
  if (sameTemplateId(sourceId, targetId)) return [...templates]

  const reordered = [...templates]
  const [moved] = reordered.splice(sourceIndex, 1)
  const targetIndex = reordered.findIndex(template => sameTemplateId(template.id, targetId))
  const insertionIndex = targetIndex + (placement === 'after' ? 1 : 0)
  reordered.splice(insertionIndex, 0, moved)
  return reordered
}

export function templateOrderUpdates(templates = []) {
  return templates.map((template, index) => ({
    id: template.id,
    sort_order: (index + 1) * 10,
  }))
}

export function nextCaseTemplateSortOrder(templates = []) {
  const currentMaximum = Math.max(
    0,
    ...templates.map(template => Number(template.sort_order) || 0),
  )
  return currentMaximum + 10
}

export function mergeSavedCaseTemplate(templates = [], savedTemplate) {
  if (!savedTemplate?.id) return [...templates]
  const merged = templates
    .filter(template => !sameTemplateId(template.id, savedTemplate.id))
    .map(template => (
      savedTemplate.is_default && template.is_default
        ? { ...template, is_default: false }
        : template
    ))
  merged.push(savedTemplate)
  return merged.sort((left, right) => {
    const orderDifference = (Number(left.sort_order) || 0) - (Number(right.sort_order) || 0)
    if (orderDifference) return orderDifference
    return String(left.name || '').localeCompare(String(right.name || ''))
  })
}
