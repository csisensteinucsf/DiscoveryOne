import { useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { OTHER_ROLE_SECTIONS, REQUESTOR_HELP_SECTIONS, TECH_HELP_SECTIONS } from './HelpContent.js'

const isRequestorRole = (role) => role === 'requestor'
const isTechRole = (role) => role === 'tech'

function resolveProfile(role) {
  if (isTechRole(role)) {
    return {
      title: 'Tech Help Documentation',
      intro: 'Detailed navigation and workflow guidance for tech accounts.',
      sections: TECH_HELP_SECTIONS,
      defaultHash: '#tech-overview',
    }
  }
  if (isRequestorRole(role)) {
    return {
      title: 'Requestor Help Documentation',
      intro: 'Detailed navigation and workflow guidance for requestor accounts.',
      sections: REQUESTOR_HELP_SECTIONS,
      defaultHash: '#help-overview',
    }
  }
  return {
    title: 'Help Documentation',
    intro: 'Role-focused help is currently published for requestor and tech only.',
    sections: OTHER_ROLE_SECTIONS,
    defaultHash: '#help-overview',
  }
}


function SectionList({ title, items, ordered = false }) {
  if (!Array.isArray(items) || items.length === 0) return null
  const Tag = ordered ? 'ol' : 'ul'
  return (
    <>
      <h4 style={{ marginTop: 14, marginBottom: 8 }}>{title}</h4>
      <Tag>
        {items.map((item, idx) => (
          <li key={`${title}-${idx}`}>{item}</li>
        ))}
      </Tag>
    </>
  )
}
export default function Help() {
  const { user } = useAuth()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const location = useLocation()

  const profile = useMemo(() => resolveProfile(role), [role])
  const hash = location.hash || profile.defaultHash
  const visibleSections = profile.sections

  useEffect(() => {
    const targetId = (hash || profile.defaultHash).replace(/^#/, '')
    const targetElement = document.getElementById(targetId)
    if (targetElement) {
      targetElement.scrollIntoView({ behavior: 'smooth' })
    } else {
      window.scrollTo({ top: 0 })
    }
  }, [hash, profile.defaultHash])

  return (
    <div className="wrap help-page" style={{ paddingTop: 12 }}>
      <div className="card" style={{ padding: '24px 32px', maxWidth: 1080, width: '100%', margin: '0 auto' }}>
        <h1 style={{ marginTop: 0 }}>{profile.title}</h1>
        <p style={{ marginBottom: 6, color: '#475569' }}>{profile.intro}</p>
        <p style={{ marginBottom: 18, color: '#475569' }}>
          Role detected: <strong>{role}</strong>
        </p>

        <div className="help-toc">
          <h3>Jump to a section</h3>
          <ul>
            {visibleSections.map((section) => (
              <li key={section.id}>
                <a href={`#${section.id}`}>{section.title}</a>
              </li>
            ))}
          </ul>
        </div>

        {visibleSections.map((section) => (
          <section className="help-section" id={section.id} key={section.id}>
            <h2>{section.title}</h2>
            {section.paragraphs?.map((text, idx) => (
              <p key={`${section.id}-p-${idx}`}>{text}</p>
            ))}
            <SectionList title="Step-by-step" items={section.steps} ordered />
            <SectionList title="Controls in This Screen" items={section.controls} />
            <SectionList title="Checks Before You Continue" items={section.checks} />
            <SectionList title="Role Limits" items={section.limits} />
            <SectionList title="Tips" items={section.tips} />
          </section>
        ))}
      </div>
    </div>
  )
}







