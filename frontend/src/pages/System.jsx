// frontend/src/pages/System.jsx
import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import Modal from '../components/Modal.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import SystemUserModal from './SystemUserModal.jsx'
import SystemNtpTemplateModal from './SystemNtpTemplateModal.jsx'
import { SystemActiveUsersModal, SystemGroupModal, SystemRegistrationApprovalModal } from './SystemAccountModals.jsx'
import SystemIntegrationsPanel from './SystemIntegrationsPanel.jsx'
import SystemInstitutionPanel from './SystemInstitutionPanel.jsx'
import SystemTicketWorkflowsPanel from './SystemTicketWorkflowsPanel.jsx'
import SystemUsersPanel from './SystemUsersPanel.jsx'
import { SystemBackupsPanel, SystemBrandingPanel } from './SystemBackupBrandingPanels.jsx'
import SystemImportsPanel from './SystemImportsPanel.jsx'
import { SystemCaseNamingPanel, SystemPreservationPanel } from './SystemPreservationPanel.jsx'
import SystemNtpPanel from './SystemNtpPanel.jsx'
import { SystemNotificationsPanel, SystemSmtpPanel } from './SystemMessagingPanels.jsx'
import SystemClamavPanel from './SystemClamavPanel.jsx'
import SystemPreferencesPanel from './SystemPreferencesPanel.jsx'
import Logs from './Logs.jsx'
import { useSystemNtpTemplates } from './useSystemNtpTemplates.js'
import { useSystemImportsWorkflow } from './useSystemImportsWorkflow.js'
import { useSystemBackupsWorkflow } from './useSystemBackupsWorkflow.js'
import { useSystemCustodianLookupWorkflow } from './useSystemCustodianLookupWorkflow.js'
import { useSystemMessagingWorkflow } from './useSystemMessagingWorkflow.js'
import { useSystemConfigurationWorkflow } from './useSystemConfigurationWorkflow.js'
import { useSystemUsersWorkflow } from './useSystemUsersWorkflow.js'
import { useSystemClamavMonitor } from './useSystemClamavMonitor.js'
import { useSystemPreferences } from './useSystemPreferences.js'
import { useSystemAdministrativeSettings } from './useSystemAdministrativeSettings.js'
import { useSystemInstitutionWorkflow } from './useSystemInstitutionWorkflow.js'
export default function System({ apiBase = '/api' }) {

  const { user, refreshUser, authConfig } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const { showToast } = useToast()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const ssoEnabled = !!authConfig?.sso_enabled
  const ssoDisplayName = authConfig?.sso_display_name || 'Single sign-on'
  const employeeIdLabel = authConfig?.institution?.employee_id_label || 'Employee ID'
  const isSysAdmin = role === 'sys_admin'
  const isRequestor = role === 'requestor'
  const canRequestorManageNtp = isRequestor
  const canManageBranding = isSysAdmin
  const canManageUsers = isSysAdmin
  const canManageNtp = role === 'sys_admin' || role === 'analyst'
  const {
    institutionSettings,
    institutionSaving,
    institutionStatus,
    updateInstitutionSetting,
    saveInstitutionSettings,
  } = useSystemInstitutionWorkflow({
    apiBase,
    isSysAdmin,
  })
  const {
    userTheme,
    themeSaving,
    updateThemePreference,
    caseSortMode,
    caseSortSaving,
    updateCaseSortPreference,
  } = useSystemPreferences({
    apiBase,
    user,
    refreshUser,
    showToast,
  })
  const {
    integrationSettings,
    integrationStatus,
    integrationSaving,
    updateIntegrationEnabled,
    updateIntegrationProvider,
    updateIntegrationConfig,
    saveIntegrationSettings,
    loadIntegrations,
    preservationSourcePayload,
    customPreservationInput,
    setCustomPreservationInput,
    customPreservationSources,
    togglePreservationSource,
    savePreservationSources,
    preservationSaving,
    preservationStatus,
    caseNamingMode,
    setCaseNamingMode,
    saveCaseNaming,
    caseNamingSaving,
    caseNamingStatus,
    caseClosureSettings,
    updateCaseClosureSetting,
    saveCaseClosureSettings,
    caseClosureSaving,
    caseClosureStatus,
    caseStatusSettings,
    updateCaseStatusSetting,
    saveCaseStatusSettings,
    caseStatusSaving,
    caseStatusStatus,
    caseRequestSettings,
    updateCaseRequestSetting,
    saveCaseRequestSettings,
    caseRequestSaving,
    caseRequestStatus,
    ticketWorkflows,
    updateTicketWorkflow,
    addTicketWorkflow,
    removeTicketWorkflow,
    saveTicketWorkflows,
    ticketWorkflowSaving,
    ticketWorkflowStatus,
    applyConfigurationSettings,
    resetConfigurationSettings,
  } = useSystemConfigurationWorkflow({
    apiBase,
    isSysAdmin,
  })
  const normalizeGroupValue = (value) => (value || '').trim().toLowerCase()
  const userGroup = normalizeGroupValue(user?.requestor_group || '')
  const {
    ntpTemplates,
    ntpTemplatesLoading,
    ntpGroupOptions,
    ntpGroupInput,
    setNtpGroupInput,
    templateForm,
    setTemplateForm,
    templateBodyRef,
    templateSelectionRef,
    showVarModal,
    setShowVarModal,
    editingTemplate,
    showTemplateModal,
    templateSaving,
    templateStatus,
    templateVariables,
    captureTemplateSelection,
    insertTemplateVariable,
    removeTemplateGroup,
    toggleTemplateGroupOption,
    handleAddGroupInput,
    templateAccessible,
    templateDeletable,
    loadTemplates,
    loadNtpGroups,
    openTemplateModal,
    copyTemplate,
    closeTemplateModal,
    saveTemplate,
    deleteTemplate,
  } = useSystemNtpTemplates({
    apiBase,
    canManageNtp,
    canRequestorManageNtp,
    isRequestor,
    userGroup,
    normalizeGroupValue,
    showToast,
  })
  const {
    logos,
    activeLogo,
    status,
    selectedFileName,
    brandingText,
    setBrandingText,
    brandingTextSaving,
    deploymentSettings,
    setDeploymentSettings,
    deploymentSaving,
    deploymentStatus,
    accountReviewSettings,
    accountReviewStatus,
    accountReviewSaving,
    ntpSettings,
    setNtpSettings,
    ntpSettingsStatus,
    ntpSettingsSaving,
    flash,
    resetAdministrativeSettings,
    applyAdministrativeSettings,
    updateAccountReviewSetting,
    saveAccountReviewSettings,
    saveNtpSettings,
    saveDeploymentSettings,
    saveBrandingText,
    onUploadLogo,
    onSelectLogo,
    onResetLogo,
    onDeleteLogo,
  } = useSystemAdministrativeSettings({
    apiBase,
    isSysAdmin,
    canManageBranding,
    loadTemplates,
  })

  const {
    users,
    editingId,
    editingSeedAdmin,
    showModal,
    approveRegTarget,
    approveRegRole,
    setApproveRegRole,
    approveRegGroup,
    setApproveRegGroup,
    approveRegNewGroup,
    setApproveRegNewGroup,
    setApproveRegTarget,
    registrationInviteBusyId,
    form,
    setForm,
    userSaveBusy,
    groups,
    groupModal,
    groupForm,
    setGroupForm,
    groupSaving,
    activeUsers,
    activeUsersLoading,
    showActiveUsersModal,
    setShowActiveUsersModal,
    registrationRequests,
    formatGroupLabel,
    allGroupOptions,
    analystOptions,
    closeModal,
    loadUsers,
    loadActiveUsers,
    loadGroups,
    loadRegistrationRequests,
    openCreate,
    openEdit,
    saveUser,
    userModalSaveDisabled,
    deleteUser,
    openGroup,
    openCreateGroup,
    closeGroupModal,
    saveGroup,
    declineRegistration,
    removeRegistrationRequest,
    openApproveRegistration,
    approveRegistration,
    resendRegistrationInvite,
  } = useSystemUsersWorkflow({
    apiBase,
    user,
    refreshUser,
    authConfig,
    showToast,
    canManageUsers,
    isRequestor,
    ssoEnabled,
    employeeIdLabel,
    ntpGroupOptions,
    loadNtpGroups,
    normalizeGroupValue,
    flash,
  })
  const importWorkflow = useSystemImportsWorkflow({
    apiBase,
    isSysAdmin,
    showToast,
  })
  const {
    lastBackup,
    backupHealth,
    backupsLoading,
    backupStatus,
    backupSettings,
    updateBackupSetting,
    saveBackupSettings,
    backupSettingsSaving,
    backupSettingsStatus,
    loadBackups,
    runScheduledBackup,
    describeBackupType,
    restoreInputRef,
    onRestoreFileChange,
    runRestore,
    restoreBusy,
    restoreFile,
    restoreStatus,
    restoreKey,
    setRestoreKey,
  } = useSystemBackupsWorkflow({
    apiBase,
    isSysAdmin,
  })
  const {
    custodianLookupBusy,
    custodianLookupStatus,
    runFullCustodianLookup,
  } = useSystemCustodianLookupWorkflow({
    apiBase,
    isSysAdmin,
  })
  const {
    clamavMonitor,
    clamavLoading,
    clamavStatus,
    loadClamavMonitor,
  } = useSystemClamavMonitor({
    apiBase,
    isSysAdmin,
  })

  const {
    smtpForm,
    updateSmtpField,
    saveSmtpSettings,
    smtpSaving,
    smtpStatus,
    testEmail,
    setTestEmail,
    sendTestEmail,
    testBusy,
    testStatus,
    notifications,
    updateTeamsWebhook,
    clearTeamsWebhook,
    updateEventEnabled,
    updateEventTemplate,
    updateEmailEventEnabled,
    updateEmailEventSubject,
    updateEmailEventBody,
    updateSearchDeliveryReminderSetting,
    updateConsentNotificationSetting,
    saveNotifications,
    notificationsSaving,
    notificationsStatus,
    loadNotifications,
    applySmtpSettings,
  } = useSystemMessagingWorkflow({
    apiBase,
    isSysAdmin,
  })
  const loadSettings = useCallback(async () => {
    if (!isSysAdmin) {
      resetAdministrativeSettings()
      applySmtpSettings(null)
      resetConfigurationSettings()
      return
    }
    const res = await fetch(apiBase + '/system/settings', { credentials: 'include' })
    if (!res.ok) return
    const data = await res.json()
    applyAdministrativeSettings(data)
    applySmtpSettings(data.smtp)
    applyConfigurationSettings(data)
  }, [
    apiBase,
    isSysAdmin,
    resetAdministrativeSettings,
    applyAdministrativeSettings,
    applySmtpSettings,
    applyConfigurationSettings,
    resetConfigurationSettings,
  ])



  useEffect(() => {
    loadSettings()
    loadUsers()
    loadActiveUsers()
    loadGroups()
    loadRegistrationRequests()
    loadNotifications()
    loadIntegrations()
  }, [loadSettings, loadUsers, loadActiveUsers, loadGroups, loadRegistrationRequests, loadNotifications, loadIntegrations])

  useEffect(() => {
    if (!canManageUsers) return undefined
    const timer = window.setInterval(() => {
      loadActiveUsers()
    }, 60000)
    return () => window.clearInterval(timer)
  }, [canManageUsers, loadActiveUsers])


  useEffect(() => {
    if (!isSysAdmin) return
    loadBackups()
    loadClamavMonitor()
    const onKey = (e) => { if (e.key === 'Escape') closeModal() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [loadBackups, loadClamavMonitor, isSysAdmin, closeModal])

  const sections = [
    {
      id: 'access',
      label: 'Access',
      views: [{ id: 'users', label: 'Users & Groups' }],
    },
    {
      id: 'organization',
      label: 'Organization',
      views: [
        { id: 'institution', label: 'Institution' },
        { id: 'branding', label: 'Branding' },
        { id: 'case_naming', label: 'Case Settings' },
        { id: 'preferences', label: 'My Preferences' },
      ],
    },
    {
      id: 'workflows',
      label: 'Workflows',
      views: [
        { id: 'preservation', label: 'Preservation' },
        { id: 'ticket_workflows', label: 'Ticket Workflows' },
        { id: 'ntp', label: 'NTP Templates' },
        { id: 'notifications', label: 'Notifications' },
        { id: 'imports', label: 'Bulk Case Import' },
      ],
    },
    {
      id: 'integrations',
      label: 'Integrations',
      views: [
        { id: 'integrations', label: 'Integration Providers' },
        { id: 'smtp', label: 'SMTP' },
      ],
    },
    {
      id: 'operations',
      label: 'Operations',
      views: [
        { id: 'backups', label: 'Backups & Restore' },
        { id: 'clamav', label: 'ClamAV' },
        { id: 'logs', label: 'Logs' },
      ],
    },
  ]
  const allViews = sections.flatMap(section => section.views)
  const requestedView = searchParams.get('view')
  const initialView = allViews.some(view => view.id === requestedView) ? requestedView : 'users'
  const initialSection = sections.find(section => section.views.some(view => view.id === initialView))?.id || 'access'
  const [activeSection, setActiveSection] = useState(initialSection)
  const [activeTab, setActiveTab] = useState(initialView)

  useEffect(() => {
    const nextView = searchParams.get('view')
    if (!allViews.some(view => view.id === nextView)) return
    const nextSection = sections.find(section => section.views.some(view => view.id === nextView))
    setActiveTab(nextView)
    if (nextSection) setActiveSection(nextSection.id)
  }, [searchParams])

  const selectSystemView = (sectionId, viewId) => {
    setActiveSection(sectionId)
    setActiveTab(viewId)
    setSearchParams({ section: sectionId, view: viewId }, { replace: true })
  }
  useEffect(() => {
    if (!isSysAdmin || activeTab !== 'clamav') return undefined
    loadClamavMonitor()
    const timer = window.setInterval(() => {
      loadClamavMonitor()
    }, 30000)
    return () => window.clearInterval(timer)
  }, [activeTab, isSysAdmin, loadClamavMonitor])

  const adminOnlyCard = (message) => (
    <div className="card" style={{ marginBottom: 16 }}>
      <p style={{ color: 'var(--muted,#6b7280)', margin: 0 }}>{message || 'Only system administrators can access this section.'}</p>
    </div>
  )

  const titleStyle = { fontSize: 20, fontWeight: 700, marginBottom: 12 }
  const labelStyle = { fontSize: 16, fontWeight: 600, marginTop: 4, marginBottom: 8 }
  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 16 }}>System Management</h1>

      <div className="system-section-nav" role="tablist" aria-label="System sections">
        {sections.map(section => (
          <button
            key={section.id}
            type="button"
            role="tab"
            aria-selected={section.id === activeSection}
            className={section.id === activeSection ? 'btn' : 'btn secondary'}
            onClick={() => selectSystemView(section.id, section.views[0].id)}
          >
            {section.label}
          </button>
        ))}
      </div>

      <div className="system-view-nav" role="tablist" aria-label="Section views">
        {sections.find(section => section.id === activeSection)?.views.map(view => (
          <button
            key={view.id}
            type="button"
            role="tab"
            aria-selected={view.id === activeTab}
            className={view.id === activeTab ? 'system-view-nav__button is-active' : 'system-view-nav__button'}
            onClick={() => selectSystemView(activeSection, view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>

      {activeTab === 'preferences' && (
        <SystemPreferencesPanel
          titleStyle={titleStyle}
          userTheme={userTheme}
          themeSaving={themeSaving}
          updateThemePreference={updateThemePreference}
          caseSortMode={caseSortMode}
          caseSortSaving={caseSortSaving}
          updateCaseSortPreference={updateCaseSortPreference}
        />
      )}
      {status && (
        <div className="card" style={{ marginBottom: 16 }}>
          <span style={{ color: 'var(--muted,#6b7280)' }}>{status}</span>
        </div>
      )}

      {activeTab === 'imports' && (
        <SystemImportsPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          analystOptions={analystOptions}
          {...importWorkflow}
        />
      )}
      {activeTab === 'preservation' && (
        <SystemPreservationPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          preservationSourcePayload={preservationSourcePayload}
          customPreservationInput={customPreservationInput}
          setCustomPreservationInput={setCustomPreservationInput}
          customPreservationSources={customPreservationSources}
          togglePreservationSource={togglePreservationSource}
          savePreservationSources={savePreservationSources}
          preservationSaving={preservationSaving}
          preservationStatus={preservationStatus}
        />
      )}

      {activeTab === 'ticket_workflows' && (
        <SystemTicketWorkflowsPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          ticketWorkflows={ticketWorkflows}
          updateTicketWorkflow={updateTicketWorkflow}
          addTicketWorkflow={addTicketWorkflow}
          removeTicketWorkflow={removeTicketWorkflow}
          saveTicketWorkflows={saveTicketWorkflows}
          ticketWorkflowSaving={ticketWorkflowSaving}
          ticketWorkflowStatus={ticketWorkflowStatus}
          preservationSourcePayload={preservationSourcePayload}
        />
      )}
      {activeTab === 'case_naming' && (
        <SystemCaseNamingPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          caseNamingMode={caseNamingMode}
          setCaseNamingMode={setCaseNamingMode}
          saveCaseNaming={saveCaseNaming}
          caseNamingSaving={caseNamingSaving}
          caseNamingStatus={caseNamingStatus}
          caseClosureSettings={caseClosureSettings}
          updateCaseClosureSetting={updateCaseClosureSetting}
          saveCaseClosureSettings={saveCaseClosureSettings}
          caseClosureSaving={caseClosureSaving}
          caseClosureStatus={caseClosureStatus}
          caseStatusSettings={caseStatusSettings}
          updateCaseStatusSetting={updateCaseStatusSetting}
          saveCaseStatusSettings={saveCaseStatusSettings}
          caseStatusSaving={caseStatusSaving}
          caseStatusStatus={caseStatusStatus}
          caseRequestSettings={caseRequestSettings}
          updateCaseRequestSetting={updateCaseRequestSetting}
          saveCaseRequestSettings={saveCaseRequestSettings}
          caseRequestSaving={caseRequestSaving}
          caseRequestStatus={caseRequestStatus}
        />
      )}
      {activeTab === 'institution' && (
        <SystemInstitutionPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          institutionSettings={institutionSettings}
          institutionSaving={institutionSaving}
          institutionStatus={institutionStatus}
          updateInstitutionSetting={updateInstitutionSetting}
          saveInstitutionSettings={saveInstitutionSettings}
        />
      )}
      {activeTab === 'integrations' && (
        <SystemIntegrationsPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          integrationSettings={integrationSettings}
          updateIntegrationEnabled={updateIntegrationEnabled}
          updateIntegrationProvider={updateIntegrationProvider}
          updateIntegrationConfig={updateIntegrationConfig}
          saveIntegrationSettings={saveIntegrationSettings}
          integrationSaving={integrationSaving}
          integrationStatus={integrationStatus}
          apiBase={apiBase}
          showToast={showToast}
        />
      )}

      {activeTab === 'ntp' && (
        <SystemNtpPanel
          titleStyle={titleStyle}
          isSysAdmin={isSysAdmin}
          canManageNtp={canManageNtp}
          ntpSettings={ntpSettings}
          setNtpSettings={setNtpSettings}
          saveNtpSettings={saveNtpSettings}
          ntpSettingsSaving={ntpSettingsSaving}
          ntpSettingsStatus={ntpSettingsStatus}
          ntpTemplates={ntpTemplates}
          ntpTemplatesLoading={ntpTemplatesLoading}
          openTemplateModal={openTemplateModal}
          copyTemplate={copyTemplate}
          deleteTemplate={deleteTemplate}
          templateAccessible={templateAccessible}
          templateDeletable={templateDeletable}
          formatGroupLabel={formatGroupLabel}
        />
      )}
      {activeTab === 'smtp' && (
        <SystemSmtpPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          smtpForm={smtpForm}
          updateSmtpField={updateSmtpField}
          saveSmtpSettings={saveSmtpSettings}
          smtpSaving={smtpSaving}
          smtpStatus={smtpStatus}
          testEmail={testEmail}
          setTestEmail={setTestEmail}
          sendTestEmail={sendTestEmail}
          testBusy={testBusy}
          testStatus={testStatus}
        />
      )}

      {activeTab === 'notifications' && (
        <SystemNotificationsPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          notifications={notifications}
          updateTeamsWebhook={updateTeamsWebhook}
          clearTeamsWebhook={clearTeamsWebhook}
          updateEventEnabled={updateEventEnabled}
          updateEventTemplate={updateEventTemplate}
          updateEmailEventEnabled={updateEmailEventEnabled}
          updateEmailEventSubject={updateEmailEventSubject}
          updateEmailEventBody={updateEmailEventBody}
          updateSearchDeliveryReminderSetting={updateSearchDeliveryReminderSetting}
          updateConsentNotificationSetting={updateConsentNotificationSetting}
          saveNotifications={saveNotifications}
          notificationsSaving={notificationsSaving}
          notificationsStatus={notificationsStatus}
        />
      )}
      {activeTab === 'logs' && <Logs apiBase={apiBase} />}
      {activeTab === 'clamav' && (
        <SystemClamavPanel
          isSysAdmin={isSysAdmin}
          adminOnlyCard={adminOnlyCard}
          titleStyle={titleStyle}
          clamavMonitor={clamavMonitor}
          clamavLoading={clamavLoading}
          clamavStatus={clamavStatus}
          loadClamavMonitor={loadClamavMonitor}
        />
      )}
      <SystemBackupsPanel
        active={activeTab === 'backups'}
        isSysAdmin={isSysAdmin}
        adminOnlyCard={adminOnlyCard}
        titleStyle={titleStyle}
        backupHealth={backupHealth}
        backupsLoading={backupsLoading}
        runScheduledBackup={runScheduledBackup}
        custodianLookupBusy={custodianLookupBusy}
        runFullCustodianLookup={runFullCustodianLookup}
        loadBackups={loadBackups}
        backupStatus={backupStatus}
        backupSettings={backupSettings}
        updateBackupSetting={updateBackupSetting}
        saveBackupSettings={saveBackupSettings}
        backupSettingsSaving={backupSettingsSaving}
        backupSettingsStatus={backupSettingsStatus}
        custodianLookupStatus={custodianLookupStatus}
        lastBackup={lastBackup}
        describeBackupType={describeBackupType}
        restoreInputRef={restoreInputRef}
        onRestoreFileChange={onRestoreFileChange}
        runRestore={runRestore}
        restoreBusy={restoreBusy}
        restoreFile={restoreFile}
        restoreStatus={restoreStatus}
        restoreKey={restoreKey}
        setRestoreKey={setRestoreKey}
      />

      <SystemBrandingPanel
        active={activeTab === 'branding'}
        isSysAdmin={isSysAdmin}
        adminOnlyCard={adminOnlyCard}
        titleStyle={titleStyle}
        labelStyle={labelStyle}
        canManageBranding={canManageBranding}
        onUploadLogo={onUploadLogo}
        selectedFileName={selectedFileName}
        brandingText={brandingText}
        setBrandingText={setBrandingText}
        saveBrandingText={saveBrandingText}
        brandingTextSaving={brandingTextSaving}
        deploymentSettings={deploymentSettings}
        setDeploymentSettings={setDeploymentSettings}
        saveDeploymentSettings={saveDeploymentSettings}
        deploymentSaving={deploymentSaving}
        deploymentStatus={deploymentStatus}
        activeLogo={activeLogo}
        onResetLogo={onResetLogo}
        logos={logos}
        onSelectLogo={onSelectLogo}
        onDeleteLogo={onDeleteLogo}
      />
      <SystemUsersPanel
        active={activeTab === 'users'}
        titleStyle={titleStyle}
        canManageUsers={canManageUsers}
        activeUsers={activeUsers}
        activeUsersLoading={activeUsersLoading}
        setShowActiveUsersModal={setShowActiveUsersModal}
        loadActiveUsers={loadActiveUsers}
        openCreate={openCreate}
        users={users}
        authConfig={authConfig}
        ssoDisplayName={ssoDisplayName}
        formatGroupLabel={formatGroupLabel}
        user={user}
        openEdit={openEdit}
        deleteUser={deleteUser}
        openCreateGroup={openCreateGroup}
        accountReviewSettings={accountReviewSettings}
        updateAccountReviewSetting={updateAccountReviewSetting}
        saveAccountReviewSettings={saveAccountReviewSettings}
        accountReviewSaving={accountReviewSaving}
        accountReviewStatus={accountReviewStatus}
        groups={groups}
        openGroup={openGroup}
        registrationRequests={registrationRequests}
        openApproveRegistration={openApproveRegistration}
        declineRegistration={declineRegistration}
        registrationInviteBusyId={registrationInviteBusyId}
        resendRegistrationInvite={resendRegistrationInvite}
        removeRegistrationRequest={removeRegistrationRequest}
      />

      <SystemActiveUsersModal
        open={showActiveUsersModal}
        activeUsers={activeUsers}
        activeUsersLoading={activeUsersLoading}
        onRefresh={loadActiveUsers}
        onClose={() => setShowActiveUsersModal(false)}
      />

      <SystemGroupModal
        groupModal={groupModal}
        closeGroupModal={closeGroupModal}
        groupSaving={groupSaving}
        saveGroup={saveGroup}
        groupForm={groupForm}
        setGroupForm={setGroupForm}
        groups={groups}
        normalizeGroupValue={normalizeGroupValue}
        formatGroupLabel={formatGroupLabel}
      />

      <SystemRegistrationApprovalModal
        approveRegTarget={approveRegTarget}
        authConfig={authConfig}
        setApproveRegTarget={setApproveRegTarget}
        approveRegRole={approveRegRole}
        setApproveRegRole={setApproveRegRole}
        approveRegGroup={approveRegGroup}
        setApproveRegGroup={setApproveRegGroup}
        approveRegNewGroup={approveRegNewGroup}
        setApproveRegNewGroup={setApproveRegNewGroup}
        approveRegistration={approveRegistration}
        allGroupOptions={allGroupOptions}
        formatGroupLabel={formatGroupLabel}
      />

      <SystemNtpTemplateModal
        open={showTemplateModal}
        editingTemplate={editingTemplate}
        closeTemplateModal={closeTemplateModal}
        saveTemplate={saveTemplate}
        templateSaving={templateSaving}
        templateForm={templateForm}
        setTemplateForm={setTemplateForm}
        canManageNtp={canManageNtp}
        formatGroupLabel={formatGroupLabel}
        removeTemplateGroup={removeTemplateGroup}
        ntpGroupOptions={ntpGroupOptions}
        toggleTemplateGroupOption={toggleTemplateGroupOption}
        ntpGroupInput={ntpGroupInput}
        setNtpGroupInput={setNtpGroupInput}
        handleAddGroupInput={handleAddGroupInput}
        userGroup={userGroup}
        captureTemplateSelection={captureTemplateSelection}
        setShowVarModal={setShowVarModal}
        templateBodyRef={templateBodyRef}
        templateSelectionRef={templateSelectionRef}
        templateStatus={templateStatus}
      />

      {showVarModal && (
        <Modal
          open
          title="Insert variable"
          onClose={() => setShowVarModal(false)}
          width={360}
          footer={null}
        >
          <div style={{ display: 'grid', gap: 8 }}>
            {templateVariables.map(val => (
              <button
                key={val}
                type="button"
                className="btn subtle"
                style={{ justifyContent: 'flex-start' }}
                onClick={() => { insertTemplateVariable(val); setShowVarModal(false) }}
              >
                {val}
              </button>
            ))}
          </div>
        </Modal>
      )}

      <SystemUserModal
        open={showModal}
        editingId={editingId}
        closeModal={closeModal}
        userSaveBusy={userSaveBusy}
        saveUser={saveUser}
        userModalSaveDisabled={userModalSaveDisabled}
        editingSeedAdmin={editingSeedAdmin}
        form={form}
        setForm={setForm}
        ssoEnabled={ssoEnabled}
        ssoDisplayName={ssoDisplayName}
        canManageUsers={canManageUsers}
        isRequestor={isRequestor}
        employeeIdLabel={employeeIdLabel}
        user={user}
      />
    </div>
  )
}
