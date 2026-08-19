import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('paired row actions use accessible shared pencil and trash icons', () => {
  const componentSource = readSource('../../src/components/RowActionIconButton.jsx')
  assert.match(componentSource, /import \{ Pencil, Trash2 \} from 'lucide-react'/)
  assert.match(componentSource, /title=\{title \|\| label\}/)
  assert.match(componentSource, /aria-label=\{label\}/)

  const pairedActionSources = [
    '../../src/components/NotesPanel.jsx',
    '../../src/pages/CaseDetailSearchesTab.jsx',
    '../../src/pages/CasesTableRow.jsx',
    '../../src/pages/SystemCaseTemplatesPanel.jsx',
    '../../src/pages/SystemEmailIntakeWorkspace.jsx',
    '../../src/pages/SystemNtpPanel.jsx',
    '../../src/pages/SystemUsersPanel.jsx',
  ]

  for (const relativePath of pairedActionSources) {
    const source = readSource(relativePath)
    assert.match(source, /EditIconButton/, relativePath)
    assert.match(source, /DeleteIconButton/, relativePath)
    assert.doesNotMatch(source, />(?:Edit|Remove|Delete)<\/button>/, relativePath)
  }
})

test('case close or reopen action appears before the edit action', () => {
  const source = readSource('../../src/pages/CasesTableRow.jsx')
  const closeActionPosition = source.indexOf("{c.closed ? 'Reopen' : 'Close'}")
  const editActionPosition = source.indexOf('<EditIconButton')

  assert.notEqual(closeActionPosition, -1)
  assert.notEqual(editActionPosition, -1)
  assert.ok(closeActionPosition < editActionPosition)
})

test('Case Detail custodian rows are read only', () => {
  const source = readSource('../../src/pages/CaseDetailCustodiansTab.jsx')

  assert.match(source, /values are read only here/)
  assert.doesNotMatch(source, /EditIconButton|DeleteIconButton/)
  assert.doesNotMatch(source, /onToggleHold\(|onChangeNtp\(|onChangeConsent\(/)
})
