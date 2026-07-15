import SystemAdditionalIntegrationConfigSections from './SystemAdditionalIntegrationConfigSections.jsx'
import SystemCoreIntegrationConfigSections from './SystemCoreIntegrationConfigSections.jsx'

export default function SystemIntegrationConfigSections({ integrationSettings, updateIntegrationConfig }) {
  const props = { integrationSettings, updateIntegrationConfig }

  return (
    <>
      <SystemCoreIntegrationConfigSections {...props} />
      <SystemAdditionalIntegrationConfigSections {...props} />
    </>
  )
}