const PERSON_LOOKUP_FIELDS = {
  employment_end_date: null,
  external_id: null,
  first_name: null,
  last_name: null,
  department_id: null,
  department: null,
  title: null,
  current_employee: null,
}

export function personLookupExternalId(record) {
  return record?.external_id || record?.employee_id || record?.person_id || null
}

export function personLookupDepartment(record) {
  return record?.department || record?.department_name || null
}

export function personLookupDepartmentId(record) {
  return record?.department_id || null
}

export function personLookupTitle(record) {
  return record?.title || record?.job_title_official || null
}

export function personLookupCurrentEmployee(record) {
  if (typeof record?.current_employee === 'boolean') return record.current_employee
  return null
}

export function emptyPersonLookupFields() {
  return { ...PERSON_LOOKUP_FIELDS }
}

export function personLookupFieldsFromRecord(record) {
  const externalId = personLookupExternalId(record)
  const firstName = record?.first_name || null
  const lastName = record?.last_name || null
  const departmentId = personLookupDepartmentId(record)
  const department = personLookupDepartment(record)
  const title = personLookupTitle(record)
  const currentEmployee = personLookupCurrentEmployee(record)
  const employmentEndDate = record?.employment_end_date || record?.separation_date || record?.employee_end_date || null
  return {
    employment_end_date: employmentEndDate,
    external_id: externalId,
    employee_id: externalId,
    first_name: firstName,
    last_name: lastName,
    department_id: departmentId,
    department,
    title,
    current_employee: currentEmployee,
  }
}

export function personLookupFieldsFromMatch(match) {
  return personLookupFieldsFromRecord(match)
}

export function editablePersonLookupFieldsFromRecord(record) {
  const fields = personLookupFieldsFromRecord(record)
  return {
    employment_end_date: fields.employment_end_date || '',
    external_id: fields.external_id || '',
    employee_id: fields.employee_id || fields.external_id || '',
    first_name: fields.first_name || '',
    last_name: fields.last_name || '',
    department_id: fields.department_id || '',
    department: fields.department || '',
    title: fields.title || '',
    current_employee: fields.current_employee,
  }
}
