export const REQUESTOR_HELP_SECTIONS = [
  {
    id: 'help-overview',
    title: 'Requestor Guide: Start Here',
    paragraphs: [
      'This guide is written for requestor workflows. It is intentionally detailed so you can execute each workflow without guessing what each screen is for.',
      'Use the question-mark button from any page to jump directly to the section that explains that page. If a modal is open (for example a new request wizard), the same page section still applies.',
      'This guide is for requestor accounts that submit and track work. Analyst and sys admin workflows are intentionally excluded.',
    ],
    steps: [
      'Use the table of contents first, then keep this page open in a second tab while you work through an unfamiliar flow.',
      'If you are completely new, read sections in this order: Access and login, Cases page, Requests page, New case request, and Case detail.',
      'If you already submitted a request, jump straight to Requests page and the request-type section that matches your task.',
      'If you are working inside a case, read Case detail before making assumptions based on status chips.',
      'Treat Pending status values as in-progress snapshots. Some external hold/search/ticket systems update asynchronously.',
    ],
    tips: [
      'Most requestor mistakes come from incomplete custodian data (missing email, wrong person, or unclear hold scope).',
      'Use explicit text in notes: who, what, where, and why. Short vague notes usually cause decline-and-resubmit cycles.',
    ],
  },
  {
    id: 'access',
    title: 'Access, Login, and Password Recovery',
    paragraphs: [
      'Use registration only once. Existing users should use password reset instead of creating duplicate requests.',
      'Authentication and password management are handled through the Login and System pages.',
    ],
    steps: [
      'Open Login and verify the email address exactly matches your approved account.',
      'If you do not have an account, use the registration link and submit your full name and work email.',
      'Wait for approval and invitation email, then set your password from that link.',
      'If login fails and you already have an account, use Forgot Password on Login.',
      'Complete reset flow and return to Login.',
      'After successful login, open System to review your profile and preferences.',
      'If you changed password and still cannot log in, clear stale browser session cookies and retry once.',
      'If access is still blocked, provide admin support with exact error text and timestamp so logs can be correlated.',
    ],
    tips: [
      'Do not share activation or reset links. They are account-scoped.',
      'For support escalation, include the email you used and the approximate login attempt time.',
    ],
  },
  {
    id: 'cases',
    title: 'Cases Page (Requestor Navigation)',
    paragraphs: [
      'Cases is your index of matters you can see. It contains Active Cases and Inactive Cases in separate tables.',
      'Requestor accounts are read-only here for case records. Use this page to locate and open cases, not to edit case metadata.',
    ],
    steps: [
      'Select Cases from the left sidebar.',
      'Use Show Filters to reveal filter inputs at the top of each table.',
      'Filter by Name for broad lookup across both internal and legal naming patterns.',
      'Use Filter Legal Name for legal naming only when legal naming is consistently maintained.',
      'Use Filter Analyst to narrow to a specific analyst owner when you are coordinating on a handoff.',
      'Use Filter Requestor to find cases assigned to your requestor identity or related requestor set.',
      'Use year and letter expand/collapse controls to reduce visual noise before drilling into a case.',
      'Click a case row action to open Case Detail.',
      'For new work, use the yellow requestor helper card button Open Case Intake to jump to Requests.',
      'Use Reset to clear all filters quickly when results look unexpectedly empty.',
    ],
    tips: [
      'If expected cases are missing, verify role visibility and requestor assignment before assuming data loss.',
      'Legal column behavior depends on case data completeness and role-specific table layout.',
    ],
  },
  {
    id: 'case-detail',
    title: 'Case Detail (Requestor Deep Walkthrough)',
    paragraphs: [
      'Case Detail is the most important requestor screen. You validate scope, monitor status, and initiate requestor-allowed workflows from here.',
      'Requestor mode is mostly read-only for direct case edits, but requestor-specific actions are available, including NTP send flow and closure requests.',
    ],
    steps: [
      'Open a case from Cases.',
      'Read the case header first: case name, legal case, claimant, analyst, requestor list, and created date.',
      'Use Back to Cases to preserve your filter context while navigating.',
      'Requestor action buttons at top: NTPs opens notice send workflow, Case Summary opens summary view, Request Case Closure opens closure request modal.',
      'Use Custodians tab to review per-custodian preservation, NTP status, consent status, and search-derived progress badges.',
      'If custodians are missing, use Request to add custodians button from Custodians tab to open the correct request modal.',
      'Use Searches tab to review search names, assigned custodians, and Search/Export/Delivery states. Requestor sees read-only search controls.',
      'Use Tickets tab to review ticket mapping. Requestor view hides sensitive ticket identifiers and blocks direct ticket edits.',
      'Use Consent tab to review consent artifacts and proof status; requestor does not directly manage analyst-only consent operations.',
      'Use SLA tab to quickly see overdue acknowledgement or consent timelines.',
      'Use Notes tab for requestor-visible notes history and communication trail.',
      'When statuses look stale, refresh once and wait briefly for asynchronous upstream updates before escalating.',
    ],
    tips: [
      'Read-only does not mean blocked from action: requestors still trigger changes through structured request flows.',
      'If the same issue appears across multiple custodians, submit one clear request with explicit bulk instructions.',
    ],
  },
  {
    id: 'requests',
    title: 'Requests Page (Intake and Tracking)',
    paragraphs: [
      'Requests is your submission and tracking center. Requestor view groups cards into Pending, Declined (recent), and Approved (recent).',
      'Every request card is a historical record. Declined requests are not edited in place; submit a corrected replacement.',
    ],
    steps: [
      'Open Requests.',
      'Use New Case Request to start a net-new intake.',
      'Review Pending first to monitor work still awaiting analyst review.',
      'Open each card and read every section: case context, custodians, preservation, searches, attachments, and decline reason if present.',
      'For Declined cards, copy valid data into a new request and correct only the rejected components.',
      'Use Approved cards for verification of what was accepted and executed.',
      'Download any attached custodian list or consent file from the card when auditing submitted inputs.',
      'If you opened Requests from a deep link query like type=new_case, confirm modal mode before submitting.',
    ],
    tips: [
      'Include structured details up front to avoid multi-cycle back-and-forth on clarification.',
      'When multiple independent searches are needed, include separate search entries for cleaner tracking and review.',
    ],
  },
  {
    id: 'new-case-request',
    title: 'New Case Request (Step-by-Step, Extremely Detailed)',
    paragraphs: [
      'This workflow creates intake for a new matter. Accuracy here drives downstream preservation quality and approval speed.',
      'The wizard collects case details, custodian identity and preservation intent, plus any NTP/consent indicators and search requests.',
    ],
    steps: [
      'Open Requests and click New Case Request.',
      'Step 1 Case details: verify suggested case name, then set legal case name and claimant if applicable.',
      'Enter Description/Notes with concrete scope language: systems, timeframe, urgency, and legal context.',
      'Choose custodian input mode: manual entry, paste list, upload file, or none yet.',
      'If using manual mode, enter full name and email per custodian and add/remove rows as needed.',
      'If using paste mode, use one custodian per line and include email where possible.',
      'If using upload mode, provide CSV/TSV/TXT/XLSX within file size limits and wait for parsing completion.',
      'Move to Step 2 and review lookup results carefully. Resolve multiple matches by selecting the correct person record.',
      'If lookup is incorrect or unavailable, use Override lookup and manually lock final name/email plus rationale.',
      'For each custodian, open preservation options and explicitly select only required sources (Email, OneDrive, Box, Slack as available).',
      'Mark NTP already sent only when notice has already gone out and status is known.',
      'Mark Consent already received only when valid proof exists; attach proof file per custodian when required.',
      'Use Apply to all controls only when custodians share identical scope. Recheck edge cases afterward.',
      'Step 3 search details: include keywords, senders, recipients, date range, and additional instructions when needed.',
      'If multiple searches are needed, save one, add next, and keep each search focused on a single goal.',
      'Submit and wait for success confirmation before closing modal.',
    ],
    tips: [
      'Use explicit email addresses whenever possible. Unmatched identities create the largest approval delays.',
      'Attach supporting files only when they improve requestor clarity. Avoid noisy attachments with no execution value.',
    ],
  },
  {
    id: 'custodian-update-request',
    title: 'Custodian Update Request',
    paragraphs: [
      'Use this when an existing case needs person-level scope changes (additions, removals, or preservation updates).',
      'Write the request as delta instructions: what changes, what stays unchanged, and why.',
    ],
    steps: [
      'From Case Detail Custodians tab, click Request to add custodians, or open Requests and choose custodian update context.',
      'Confirm target case before entering custodian rows.',
      'Add new custodians with complete name and email data.',
      'For removals, identify custodians precisely and include reason/context in notes.',
      'Select preservation changes per custodian. Do not assume prior preservation state without checking current status.',
      'If NTP/consent indicators are part of update context, set them deliberately and include proof artifacts when relevant.',
      'Validate final roster and submit.',
      'Track the new card under Pending, then verify actual case changes after approval.',
    ],
    tips: [
      'Avoid ambiguous notes like add this person. Name exact hold actions requested.',
      'When urgency exists, include deadline and business impact in the description.',
    ],
  },
  {
    id: 'search-request',
    title: 'Search Request',
    paragraphs: [
      'Search requests should describe an executable search plan, not only high-level goals.',
      'Well-scoped searches reduce turnaround time and reduce rework due to interpretation errors.',
    ],
    steps: [
      'Open Requests and start Search Request for the correct case.',
      'Enter keywords using clear grouping, phrase logic, and exclusions when needed.',
      'Populate senders and recipients when correspondence direction matters.',
      'Set date range to bound data volume and improve relevance.',
      'Add additional instructions describing expected result shape and review intent.',
      'If multiple unrelated questions exist, create separate search entries instead of a single overloaded search.',
      'Submit and monitor status on request cards and in case search tracking.',
    ],
    tips: [
      'Phrase-match requirements should be called out explicitly in notes.',
      'Avoid broad, unbounded searches unless legally required.',
    ],
  },
  {
    id: 'close-case-request',
    title: 'Case Closure Request',
    paragraphs: [
      'Closure requests formally ask to close a case and begin hold release workflow according to policy.',
      'Use this only when the matter is actually ready for closure or when legal has approved release timing.',
    ],
    steps: [
      'From Case Detail header, click Request Case Closure, or open close-case request flow from Requests.',
      'Confirm target case and review whether case is already marked closed.',
      'Provide explicit closure notes including dependencies, approvals, and restrictions.',
      'If holds must remain temporarily, state that clearly in notes instead of assuming default behavior.',
      'Submit request and monitor Pending/Approved states in Requests.',
      'After approval, re-open Case Detail and validate closure state and hold release outcomes.',
    ],
    tips: [
      'If closure timing is contested, add stakeholders and decision date in notes for audit clarity.',
    ],
  },
  {
    id: 'dashboards',
    title: 'Dashboards Page (Requestor Use)',
    paragraphs: [
      'Dashboards provides visual widgets and drilldowns for operational status across cases and workflows.',
      'Requestor accounts can use saved dashboard layouts to monitor high-level trend and workload patterns.',
    ],
    steps: [
      'Open Dashboards.',
      'Use Refresh before interpreting metrics during active operations.',
      'Use New dashboard to create a focused workspace by team or workflow type.',
      'Use Add widget to insert metric cards relevant to your current operational question.',
      'Use Rename and Delete to keep dashboard list clean and purpose-driven.',
      'Click metric values or widgets to open drilldown tables when available.',
      'Use drilldown filter input to narrow result rows quickly.',
      'Use Open case actions from drilldowns to jump directly into Case Detail.',
      'Save dashboard layout changes after adding/removing/reordering widgets.',
    ],
    tips: [
      'Keep one dashboard for daily triage and one for weekly trend review to avoid noisy layouts.',
    ],
  },
  {
    id: 'reports',
    title: 'Reports Page (Requestor Use)',
    paragraphs: [
      'Reports provides structured exports and on-page report runners for quantitative review and audit support.',
      'Most report sections include direct CSV export links for offline analysis.',
    ],
    steps: [
      'Open Reports.',
      'Review static report sections first and use Export CSV links as needed.',
      'Use Custodian Report runner to search by custodian name/email or run across all custodians.',
      'Use Clear to reset custodian query state between unrelated analyses.',
      'Use Case Timeline section to load case-specific event timelines.',
      'Select or type case name/legal name, then load timeline.',
      'Export timeline CSV when preserving a point-in-time snapshot for external review.',
      'Open linked cases from report tables to verify context before escalating findings.',
    ],
    tips: [
      'Capture the filter/query you used in your own notes so exported data remains reproducible.',
    ],
  },
  {
    id: 'logs',
    title: 'Logs Page (Requestor Visibility)',
    paragraphs: [
      'Requestor accounts can access logs to troubleshoot account/workflow behavior and confirm audit events.',
      'Logs supports server-side filtering and paging; start broad, then narrow.',
    ],
    steps: [
      'Open Logs.',
      'Use Action contains to target event families (for example login, request, update).',
      'Use Actor ID when correlating activity to a specific user record.',
      'Use IP contains and Details/username contains to isolate narrow incidents.',
      'Click Apply filters to run a filtered query.',
      'Use Prev/Next for pagination and Refresh for same-page reload.',
      'Use Clear to reset all filters and return to page 1.',
      'Read action pills for quick severity context, then inspect Details payload for exact field changes.',
      'When escalating, capture timestamp, username, action, and key detail values from the same row.',
    ],
    tips: [
      'Logs are best-effort operational evidence. Pair with case/request screens for full context.',
    ],
  },
  {
    id: 'system',
    title: 'System Page (Requestor Scope)',
    paragraphs: [
      'System includes account-level tools available to all authenticated users plus several admin-only tabs that appear but may be restricted.',
      'As a requestor, focus on preferences and requestor-permitted template tools when configured.',
    ],
    steps: [
      'Open System.',
      'Set User Preferences theme and case sort mode to match your workflow.',
      'Contact a DiscoveryOne administrator if your account details need correction.',
      'Use tab buttons to navigate sections; expect admin-only notice cards for restricted areas.',
      'Use User Management tab for self-level visibility if your role cannot manage users globally.',
      'If NTP Templates are enabled for your requestor group, create/edit only approved language and assigned groups.',
      'Save changes and verify status messages before leaving the page.',
    ],
    tips: [
      'If a required capability is blocked by role, do not workaround with alternate accounts; request correct role/group assignment.',
    ],
  },
  {
    id: 'requestor-troubleshooting',
    title: 'Requestor Troubleshooting Checklist',
    paragraphs: [
      'Use this checklist before escalating support tickets so the team gets a reproducible issue report.',
    ],
    steps: [
      'Reproduce once and note exact page, button, and visible error text.',
      'Capture case name, request ID, and custodian email(s) involved.',
      'Refresh the page and retry once to rule out transient state.',
      'Check Requests and Case Detail together to distinguish submission failure vs delayed backend processing.',
      'For visibility issues, confirm role and assigned case/requestor context.',
      'For login issues, include approximate timestamp and whether you used single sign-on or local account sign-in.',
      'Escalate with a concise timeline of what you clicked and what the system returned.',
    ],
  },
  {
    id: 'requestor-global-nav',
    title: 'Requestor Navigation: What Each Page Is For',
    paragraphs: [
      'Requestor accounts should primarily work in Requests and Cases. Other pages are for monitoring, reporting, and account security.',
    ],
    controls: [
      'Cases: find and open case records you can view.',
      'Requests: submit all intake/update/search/closure actions and track status.',
      'Dashboards: monitor operational metrics and drilldown to cases.',
      'Reports: run/export CSV reports for audits and status checks.',
      'Logs: filter and inspect activity records available to requestor role.',
      'System: account preferences and limited role-specific tools.',
      'Help Videos: open short walkthroughs in a new tab.',
    ],
    steps: [
      'Use Requests when you need action.',
      'Use Cases when you need verification.',
      'Use Dashboards/Reports for trend or portfolio visibility.',
      'Use System for security and account maintenance.',
    ],
  },
  {
    id: 'case-detail-tab-details',
    title: 'Case Detail Tabs: Exact Requestor Behavior by Tab',
    paragraphs: [
      'Requestor role can open all case detail tabs, but editing capability differs by tab.',
    ],
    controls: [
      'Custodians tab: review holds, NTP, consent, and status chips; use Request to add custodians to trigger change workflow.',
      'Searches tab: review search status and criteria; requestor cannot create/edit searches directly here.',
      'Tickets tab: review ticket mapping/status; requestor view is read-only for ticket entry editing.',
      'Consent tab: review consent artifacts/status; requestor cannot run analyst-only consent operations.',
      'SLA tab: view overdue/on-track indicators for NTP acknowledgement and consent completion.',
      'Notes tab: add and read requestor notes; internal analyst notes remain restricted.',
    ],
    steps: [
      'Open the tab matching your immediate question.',
      'If a direct control is disabled/read-only, submit the change through Requests.',
      'After requests are approved, return to the same tab to verify final state.',
    ],
    checks: [
      'Always confirm you are in the correct case before acting from header buttons.',
      'Refresh once before escalating stale status concerns to account for async backend updates.',
    ],
  },
  {
    id: 'ntp-send',
    title: 'NTP Send Modal: Every Field and Action',
    paragraphs: [
      'NTP sending is launched from Case Detail via the NTPs button. This flow controls template selection, reminder scheduling, variables, and recipient selection.',
    ],
    controls: [
      'Template: required selector for the outbound notice format.',
      'Reminder Template: enables reminder interval/duration fields when selected.',
      'Reminder every (days): cadence for reminders.',
      'Reminders for (days): duration window before reminders stop.',
      'See previous NTPs: opens historical send/reminder timeline modal.',
      'Copy previous NTP data: preloads latest prior NTP setup for this case.',
      'Variable fields: legal case name, claimant, reason, outside counsel values, firm, and CC list.',
      'Custodian search box: narrows recipients list by name/email.',
      'Custodian checkboxes: chooses recipients for current send.',
      'Send Notices: executes send for selected custodians.',
    ],
    steps: [
      'Select template first.',
      'Configure reminder settings only if reminders are required.',
      'Populate variables and CC values carefully.',
      'Select correct custodians, then click Send Notices.',
      'Verify send results in custodian status views after completion.',
    ],
    checks: [
      'Do not send until template and recipient set are verified.',
      'Some custodians may be blocked from NTP selection (for example separated or marked Silent).',
    ],
  },
  {
    id: 'request-card-anatomy',
    title: 'Requests Cards: What To Review on Every Card',
    paragraphs: [
      'Each request card is a permanent record of what you asked for and how it was handled.',
    ],
    controls: [
      'Type and case header: confirms request category and target case.',
      'Status badge: pending, approved, or declined.',
      'Submitted metadata: timestamp and requestor identity.',
      'Payload sections: custodians, holds, search definitions, and attachments.',
      'Decline reason line: appears on declined cards and drives resubmission corrections.',
      'Download links: uploaded lists and consent proof files where attached.',
    ],
    steps: [
      'Open the card and confirm request type and case.',
      'Read status and details completely before acting.',
      'If declined, copy valid info and resubmit corrected request.',
      'If approved, verify resulting case state in Case Detail.',
    ],
  },
  {
    id: 'system-account-security',
    title: 'System Security: Account Review (Requestor)',
    paragraphs: [
      'System includes account details you should review routinely.',
    ],
    controls: [
      'User profile summary: shows your account details and assigned access.',
    ],
    steps: [
      'Open System.',
      'Review your account details and assigned access.',
      'Contact a DiscoveryOne administrator if your account details need correction.',
    ],
  },
  {
    id: 'declined-requests',
    title: 'Declined Requests: Recovery Procedure',
    paragraphs: [
      'Declined requests are not edited in place. Recovery is always a corrected resubmission.',
    ],
    steps: [
      'Open Declined Requests section.',
      'Read decline reason fully.',
      'Create a new request of the same type.',
      'Reuse valid data, correct only rejected fields, then resubmit.',
      'Track the new card under Pending until reviewed.',
    ],
  },]

export const TECH_HELP_SECTIONS = [
  {
    id: 'tech-overview',
    title: 'Tech Guide: Start Here',
    paragraphs: [
      'This guide is for tech accounts. Tech role is ticket-focused and scope-limited by group assignment (Box and/or Email).',
      'Tech navigation is intentionally narrower than requestor workflows: Cases, System, and Help Videos.',
    ],
    steps: [
      'Use Cases to find eligible matters and open case details.',
      'Use Case Detail primarily for Custodians and Tickets tabs, depending on group permissions.',
      'Use System for your own account security settings and limited role-visible tabs.',
      'Use the help button on any page to jump to matching tech instructions.',
    ],
    tips: [
      'If a case or category is missing, first confirm your tech group assignment before escalating.',
    ],
  },
  {
    id: 'access',
    title: 'Access, Login, and Group Validation',
    paragraphs: [
      'Tech account behavior depends on both role and assigned group (a configured ticket workflow group).',
      'Without a valid group, ticket categories can appear empty.',
    ],
    steps: [
      'Log in normally with approved tech account credentials.',
      'Open System and confirm your account profile includes expected group assignment.',
      'If ticket categories are missing in case detail, verify group is exactly Box and/or Email.',
      'Set a password on first login or after reset.',
      'Escalate group mismatches through admin channel instead of using another user account.',
    ],
  },
  {
    id: 'tech-cases',
    title: 'Cases Page (Tech Workflow)',
    paragraphs: [
      'Tech cases list only shows matters that are visible to your ticket category permissions.',
      'Tech page includes a ticket-only access notice and read-only case table controls.',
    ],
    steps: [
      'Select Cases.',
      'Use Show Filters and narrow by case name, analyst, or requestor context as needed.',
      'Expand year and letter groups to locate the case faster.',
      'Open case detail for ticket and hold work.',
      'Remember: tech cannot create/edit/delete case records from this page.',
      'If no cases appear, verify your assigned group and whether matching ticket categories exist on cases.',
    ],
    tips: [
      'Use Reset whenever multiple filters were applied across different tasks.',
    ],
  },
  {
    id: 'tech-case-detail',
    title: 'Case Detail (Tech Deep Walkthrough)',
    paragraphs: [
      'Tech opens directly into ticket-focused context and can manage only allowed hold/ticket categories by group.',
      'Tech view intentionally hides non-tech tabs like Searches, Consent, SLA, and Notes.',
    ],
    steps: [
      'Open a case from Cases.',
      'Read top info and confirm you are in ticket-only view notice context.',
      'Use tab buttons: Custodians and Tickets are the primary tech surfaces.',
      'In Custodians tab, review only hold fields relevant to your allowed categories.',
      'Use Set all to completed for bulk completion when operationally appropriate.',
      'Use Apply to persist tech hold changes after review.',
      'Switch to Tickets tab to manage category-specific ticket entries.',
      'If you see warning that no categories are available, your group mapping is missing or invalid.',
      'Add ticket entries using + Add inside allowed category cards.',
      'Map custodians accurately, maintain ticket identifiers, and use copy helpers when coordinating execution.',
      'Track status badges (opened, assigned, closed) and assignee handoff indicators where visible.',
      'Use Ticket Notes section for operational context and handoff traceability.',
      'Save/verify state before leaving the page.',
    ],
    tips: [
      'Tech group access comes from System > Ticket Workflows. Each workflow defines which tech group can see and work that category.',
      'Do not assume access to every case ticket type. Visibility is category-scoped.',
    ],
  },
  {
    id: 'tech-system',
    title: 'System Page (Tech Scope)',
    paragraphs: [
      'Tech uses System primarily for personal account settings and password management.',
      'Admin-only tabs are visible in tab bar but show access-limited cards when not permitted.',
    ],
    steps: [
      'Open System.',
      'Set User Preferences theme and case sort mode.',
      'Change password and verify confirmation matches.',
      'Review your account details and change your password when needed.',
      'Use User Management view for self visibility where allowed; global user management remains restricted.',
      'Ignore admin-only operational tabs unless you are explicitly granted elevated access.',
    ],
    tips: [
      'If you need tab-level access for an operational task, request role change formally instead of bypassing policy.',
    ],
  },
  {
    id: 'tech-unavailable-pages',
    title: 'Pages Not Available to Tech Accounts',
    paragraphs: [
      'Tech accounts do not have operational access to several requestor/analyst pages. Opening these routes directly shows not-available messages.',
    ],
    steps: [
      'Requests page is not available for tech accounts.',
      'Dashboards page is not available for tech accounts.',
      'Reports page is not available for tech accounts.',
      'Custodian admin views are not available for tech accounts.',
      'Logs page is not available for tech accounts.',
      'When a task requires these pages, escalate to requestor/analyst/sys admin based on workflow ownership.',
    ],
  },
  {
    id: 'tech-troubleshooting',
    title: 'Tech Troubleshooting Checklist',
    paragraphs: [
      'Use this checklist before escalating so support can resolve quickly.',
    ],
    steps: [
      'Confirm role is tech and group is set to Box and/or Email.',
      'Confirm case actually contains tickets in your allowed categories.',
      'Refresh case detail and re-open the same tab before concluding data is missing.',
      'Capture case name, category, ticket entry context, and visible error text.',
      'If categories are empty across all cases, escalate as group assignment issue.',
      'If one case is affected, include case ID and category in escalation details.',
    ],
  },
  {
    id: 'tech-nav',
    title: 'Tech Navigation: Working Surfaces',
    paragraphs: [
      'Tech accounts are intentionally constrained to ticket-focused work. Primary navigation is Cases and System.',
    ],
    controls: [
      'Cases: locate visible cases with allowed ticket categories.',
      'System: manage your own account security and preferences.',
      'Help Videos: short reference walkthroughs.',
    ],
  },
  {
    id: 'tech-custodians',
    title: 'Tech Custodians Tab: Preservation Update Controls',
    paragraphs: [
      'In tech mode, custodians tab supports preservation updates tied to your allowed category mapping.',
    ],
    controls: [
      'Set all to completed: bulk update for the visible preservation set.',
      'Apply: save pending preservation changes.',
      'Sort/filter controls: isolate target custodians quickly.',
    ],
    steps: [
      'Open Custodians tab.',
      'Apply needed status changes.',
      'Click Apply and confirm results before leaving.',
    ],
  },
  {
    id: 'tech-tickets',
    title: 'Tech Tickets Tab: Category Cards and Entries',
    paragraphs: [
      'Tickets tab is the main tech workspace. Cards shown are filtered by your allowed categories.',
    ],
    controls: [
      '+ Add in category card: create ticket entry for that category.',
      'Custodian mapping controls: attach ticket work to correct people.',
      'Ticket number/status display: track state and assignments.',
      'Copy custodians: copies mapped custodian emails for handoff workflows.',
      'Ticket Notes: operational commentary tied to ticket work.',
    ],
    steps: [
      'Open Tickets tab.',
      'Select category card and add/update entries.',
      'Verify mappings and status badges.',
      'Add concise ticket note for handoff context when needed.',
    ],
  },
  {
    id: 'tech-group-mapping',
    title: 'Tech Group Mapping Reference',
    paragraphs: [
      'Category visibility depends on group mapping. Missing categories are usually a group assignment issue.',
    ],
    controls: [
      'Group box: allows Box Hold and Box Hold Release categories.',
      'Groups are configured in System > Ticket Workflows and determine which ticket categories a tech user can access.',
      'Combined group values: union of both category sets.',
    ],
    checks: [
      'No valid group means no tech categories visible.',
      'Case still must contain matching category data to appear in tech scope.',
    ],
  },
  {
    id: 'tech-account-security',
    title: 'Tech Security: Password and Account Care',
    paragraphs: [
      'Use System to continuously manage account security posture.',
    ],
    steps: [
      'Review your assigned account details in System.',
      'Change your password when required.',
      'Use admin support channels if your account access needs to change.',
    ],
  },]

export const OTHER_ROLE_SECTIONS = [
  {
    id: 'help-overview',
    title: 'Help Scope',
    paragraphs: [
      'This help documentation is intentionally focused on requestor and tech workflows.',
      'For analyst or sys admin workflows, follow your internal operating procedures.',
    ],
  },
]
