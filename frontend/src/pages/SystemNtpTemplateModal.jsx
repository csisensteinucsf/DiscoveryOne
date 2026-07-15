import Modal from '../components/Modal.jsx'
import RichTextEditor from '../components/RichTextEditor.jsx'

export default function SystemNtpTemplateModal({
  open,
  editingTemplate,
  closeTemplateModal,
  saveTemplate,
  templateSaving,
  templateForm,
  setTemplateForm,
  canManageNtp,
  formatGroupLabel,
  removeTemplateGroup,
  ntpGroupOptions,
  toggleTemplateGroupOption,
  ntpGroupInput,
  setNtpGroupInput,
  handleAddGroupInput,
  userGroup,
  captureTemplateSelection,
  setShowVarModal,
  templateBodyRef,
  templateSelectionRef,
  templateStatus,
}) {
  if (!open) return null
  return (
<Modal
          open
          title={editingTemplate ? 'Edit NTP Template' : 'New NTP Template'}
          onClose={closeTemplateModal}
          dismissOnBackdrop={false}
          width={1200}
          bodyStyle={{ maxHeight: '70vh', overflowY: 'auto' }}
          footer={(
            <>
              <button className="btn" onClick={closeTemplateModal}>Cancel</button>
              <button className="btn secondary" onClick={saveTemplate} disabled={templateSaving}>
                {templateSaving ? 'Saving' : 'Save Template'}
              </button>
            </>
          )}
        >
          <div className="form-grid">
            <label>
              Name
              <input value={templateForm.name} onChange={e => setTemplateForm(prev => ({ ...prev, name: e.target.value }))} />
            </label>
            <label style={{ gridColumn: '1 / -1' }}>
              Subject
              <input value={templateForm.subject} onChange={e => setTemplateForm(prev => ({ ...prev, subject: e.target.value }))} />
            </label>
            <label style={{ gridColumn: '1 / -1' }}>
              Description
              <textarea
                rows={3}
                value={templateForm.description}
                onChange={e => setTemplateForm(prev => ({ ...prev, description: e.target.value }))}
                style={{ resize: 'vertical' }}
              ></textarea>
            </label>
            <label style={{ gridColumn: '1 / -1' }}>
              CC Recipients (comma separated)
              <input
                value={templateForm.cc}
                onChange={e => setTemplateForm(prev => ({ ...prev, cc: e.target.value }))}
              />
            </label>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-start', gap: 10, fontWeight: 600, whiteSpace: 'normal', textAlign: 'left' }}>
                <input
                  type="checkbox"
                  checked={!!templateForm.is_default}
                  onChange={(e) => setTemplateForm(prev => ({ ...prev, is_default: e.target.checked }))}
                />
                Use as default for NTP sends
              </label>
              <div style={{ fontSize: 12, color: 'var(--muted,#6b7280)', marginTop: 4 }}>
                Your default template is pre-selected when opening the case &quot;Send NTPs&quot; modal.
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-start', gap: 10, fontWeight: 600, whiteSpace: 'normal', textAlign: 'left' }}>
                <input
                  type="checkbox"
                  checked={!!templateForm.high_importance}
                  onChange={(e) => setTemplateForm(prev => ({ ...prev, high_importance: e.target.checked }))}
                />
                Mark NTP emails as high importance
              </label>
              <div style={{ fontSize: 12, color: 'var(--muted,#6b7280)', marginTop: 4 }}>
                Adds Outlook-compatible importance headers (red exclamation) to emails sent with this template.
              </div>
            </div>
            {canManageNtp ? (
              <label style={{ gridColumn: '1 / -1' }}>
                Group Access
                <p style={{ color: 'var(--muted,#6b7280)', margin: '4px 0 8px' }}>
                  Requestors in the selected groups can send this template. Leave blank to restrict usage to analysts and system administrators.
                </p>
                {templateForm.groups.length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    {templateForm.groups.map(group => (
                      <span
                        key={group}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '4px 10px',
                          borderRadius: 999,
                          background: '#e0f2fe',
                          color: '#0f172a',
                          fontSize: 12,
                        }}
                      >
                        {formatGroupLabel(group)}
                        <button
                          type="button"
                          onClick={() => removeTemplateGroup(group)}
                          style={{
                            border: 'none',
                            background: 'transparent',
                            color: '#0f172a',
                            cursor: 'pointer',
                            fontSize: 12,
                            padding: 0,
                          }}
                          title="Remove group"
                        >

                        </button>
                      </span>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: 'var(--muted,#6b7280)', marginBottom: 8 }}>
                    No requestor groups assigned.
                  </div>
                )}
                {ntpGroupOptions.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
                    {ntpGroupOptions.map(option => (
                      <label key={option} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input
                          type="checkbox"
                          checked={templateForm.groups.includes(option)}
                          onChange={() => toggleTemplateGroupOption(option)}
                        />
                        {formatGroupLabel(option)}
                      </label>
                    ))}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    value={ntpGroupInput}
                    onChange={e => setNtpGroupInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddGroupInput()
                      }
                    }}
                    placeholder="Add or type a group name"
                  />
                  <button type="button" className="btn secondary" onClick={handleAddGroupInput}>Add Group</button>
                </div>
              </label>
            ) : (
              <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)' }}>
                Templates you create are automatically shared with the <strong>{formatGroupLabel(userGroup) || 'your'}</strong> group.
              </div>
            )}
              <div style={{ gridColumn: '1 / -1', whiteSpace: 'normal' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span>Body</span>
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={(e) => {
                      e.preventDefault()
                      captureTemplateSelection()
                      setShowVarModal(true)
                    }}
                  >
                    Insert variable
                  </button>
                </div>
                <RichTextEditor
                  value={templateForm.body}
                  onChange={html => setTemplateForm(prev => ({ ...prev, body: html }))}
                  placeholder="Dear {{custodian_name}}, ..."
                  editorRef={templateBodyRef}
                  onSelectionChange={(range) => { templateSelectionRef.current = range }}
                />
              </div>
            </div>
          {templateStatus && <p style={{ color: '#b91c1c' }}>{templateStatus}</p>}
        </Modal>
  )
}
