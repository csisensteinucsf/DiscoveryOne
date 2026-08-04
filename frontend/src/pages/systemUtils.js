import {
  BUILT_IN_PRESERVATION,
  CASE_NAMING_OPTIONS,
  EMPTY_INTEGRATION_CONFIG_DEFAULTS,
  PROVIDER_DEFAULTS,
  SYSTEM_INTEGRATION_FLAGS,
} from './setupCatalog.js'

const ROLE_OPTIONS = [
  { value: 'sys_admin', label: 'Sys Admin' },
  { value: 'analyst', label: 'Analyst' },
  { value: 'tech', label: 'Tech' },
  { value: 'requestor', label: 'Requestor' },
  { value: 'tester', label: 'Tester' },
]
const MASKED_SECRET_VALUE = '__configured__'
const INTEGRATION_FLAGS = SYSTEM_INTEGRATION_FLAGS
const INTEGRATION_CONFIG_DEFAULTS = EMPTY_INTEGRATION_CONFIG_DEFAULTS
const formatDateTime = (value) => {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}
const secretInputValue = (value) => (value === MASKED_SECRET_VALUE ? '' : (value || ''))

const ADMIN_USERNAME = 'admin'
const normalizeGroupValue = (value) => String(value || '').trim().toLowerCase()

const makeEmptyForm = () => ({ first_name:'', last_name:'', email:'', password:'', confirm:'', role:'analyst', requestor_group:'', employee_id:'', local_auth_only:false, is_active:true })

export {
  ROLE_OPTIONS,
  MASKED_SECRET_VALUE,
  INTEGRATION_FLAGS,
  PROVIDER_DEFAULTS,
  INTEGRATION_CONFIG_DEFAULTS,
  BUILT_IN_PRESERVATION,
  CASE_NAMING_OPTIONS,
  formatDateTime,
  secretInputValue,
  ADMIN_USERNAME,
  normalizeGroupValue,
  makeEmptyForm
}

