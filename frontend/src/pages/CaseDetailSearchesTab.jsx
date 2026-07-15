import { Badge, Select } from './caseDetailControls.jsx'
import { isSearchPushedToProvider } from './caseDetailPersistence.js'
import { searchExportIsAutomated } from './searchExportProviderCatalog.js'

export default function CaseDetailSearchesTab({
  isRequestor,
  openCreateSearch,
  canUseSearchAi,
  openSearchAiBuilder,
  navigate,
  caseId,
  searches,
  custodians,
  updateSearchStatus,
  openEditSearch,
  copySearch,
  searchExportProvider,
  searchExportProviderName,
  pushSearchToProvider,
  searchExportModal,
  removeSearch,
}) {
  const automatedSearchExport = searchExportIsAutomated(searchExportProvider)
  return (
<section className="card" style={{ padding: 12 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <h3 style={{ margin: 0 }}>Searches</h3>
                {!isRequestor && (
                  <div className="row" style={{ gap: 8 }}>
                    <button className="btn secondary" type="button" onClick={openCreateSearch}>
                      New Search
                    </button>
                    {canUseSearchAi && (
                      <button className="btn secondary" type="button" onClick={openSearchAiBuilder}>
                        Versa Powered Search Builder
                      </button>
                    )}
                  </div>
                )}
                {isRequestor && (
                  <button
                    className="btn secondary"
                    type="button"
                    onClick={() => navigate(`/requests?type=search&caseId=${caseId}`)}
                  >
                    Request New Search
                  </button>
                )}
              </div>
              <table
                style={{
                  width:'100%',
                  borderCollapse:'collapse',
                  marginTop: 8,
                  tableLayout:'fixed'
                }}
              >
                <colgroup>
                  <col style={{ width:'18%' }} />
                  <col style={{ width:'18%' }} />
                  <col style={{ width:'12%' }} />
                  <col style={{ width:'12%' }} />
                  <col style={{ width:'12%' }} />
                  <col style={{ width:'10%' }} />
                  <col style={{ width:'10%' }} />
                </colgroup>
                <thead style={{ background: 'rgba(0,0,0,.04)' }}>
                  <tr>
                    <th style={{ textAlign:'left', padding:8 }}>Name</th>
                    <th style={{ textAlign:'left', padding:8 }}>Custodians</th>
                    <th style={{ textAlign:'center', padding:8 }}>Search</th>
                    <th style={{ textAlign:'center', padding:8 }}>Export</th>
                    <th style={{ textAlign:'center', padding:8 }}>Delivery</th>
                    <th style={{ textAlign:'center', padding:8 }}>Criteria</th>
                    <th style={{ textAlign:'center', padding:8 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {searches.length ? searches.map(s => (
                    <tr key={s.id}>
                      <td style={{ padding:8, verticalAlign:'top' }}>
                        <div style={{whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis'}}><span style={{whiteSpace:'nowrap'}}>{s.name}</span></div>
                      </td>
                      <td style={{ padding:8, verticalAlign:'top' }}>
                        <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
                          {custodians
                            .filter(c => s.custodianIds.includes(c.id))
                            .map(c => <Badge key={c.id} variant="orange" compact>{c.email || '-'}</Badge>)}
                        </div>
                      </td>
                      {/* Status dropdowns */}
                      <td style={{ padding:8, verticalAlign:'top' }}>
                        <Select
                          value={s.status_search ?? s.status?.search ?? 'not performed'}
                          onChange={(e) => updateSearchStatus(s, 'search', e.target.value)}
                          disabled={isRequestor}
                        >
                          <option value="not performed">Not performed</option>
                          <option value="performed">Performed</option>
                        </Select>
                        </td>
                        <td style={{ padding:8, verticalAlign:'top' }}>
                        <div style={{ display:'grid', gap:6 }}>
                          <Select
                            value={s.status_export ?? s.status?.export ?? 'not performed'}
                            onChange={(e) => updateSearchStatus(s, 'export', e.target.value)}
                            disabled={isRequestor}
                          >
                            <option value="not performed">Not performed</option>
                            <option value="performed">Performed</option>
                          </Select>
                          {(s.status_export ?? s.status?.export ?? 'not performed') === 'performed' && s.export_without_consent ? (
                            <Badge variant="danger" compact>Exported without consent</Badge>
                          ) : null}
                        </div>
                        </td>
                        <td style={{ padding:8, verticalAlign:'top' }}>
                        <Select
                          value={s.status_delivery ?? s.status?.delivery ?? 'not performed'}
                          onChange={(e) => updateSearchStatus(s, 'delivery', e.target.value)}
                          disabled={isRequestor}
                        >
                          <option value="not performed">Not performed</option>
                          <option value="performed">Performed</option>
                          <option value="not required">Not required</option>
                        </Select>
                      </td>
                      {/* criteria link */}
                      <td style={{ padding:8, verticalAlign:'top' }}>
                        <button
                          className="btn secondary"
                          onClick={() => openEditSearch(s)}
                          style={{ padding:'4px 8px', borderRadius:10, fontSize:12, lineHeight:'16px' }}
                        >
                          Click here for <br/>search details
                        </button>
                      </td>
                      <td style={{ padding:8, textAlign:'right', verticalAlign:'top' }}>
                        {isRequestor ? (
                          <span style={{ color:'#6b7280' }}>Read only</span>
                        ) : (
                          <div style={{ display:'flex', flexDirection:'column', gap:6, alignItems:'flex-end' }}>
                            <div className="row" style={{ gap:6, justifyContent:'flex-end', flexWrap:'wrap' }}>
                              <button className="btn secondary" onClick={() => openEditSearch(s)} style={{padding:'4px 8px',borderRadius:10,fontSize:12}}>Edit</button>
                              <button className="btn secondary" onClick={() => copySearch(s)} style={{padding:'4px 8px',borderRadius:10,fontSize:12}}>Copy</button>
                              {automatedSearchExport && (
                                <button
                                  className="btn secondary"
                                  onClick={() => pushSearchToProvider(s)}
                                  disabled={searchExportModal.busy || isSearchPushedToProvider(s)}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: 10,
                                    fontSize: 12,
                                    opacity: isSearchPushedToProvider(s) ? 0.65 : 1,
                                    cursor: isSearchPushedToProvider(s) ? 'default' : 'pointer',
                                  }}
                                >
                                  {isSearchPushedToProvider(s)
                                    ? 'Search Pushed'
                                    : (searchExportModal.busy ? 'Pushing...' : `Push to ${searchExportProviderName}`)}
                                </button>
                              )}
                            </div>
                            <button className="btn danger" onClick={() => removeSearch(s.id)} style={{padding:'4px 8px',borderRadius:10,fontSize:12,width:'fit-content'}}>Remove</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )) : (
                    <tr><td style={{ padding:8 }} colSpan={7}><em>No searches yet.</em></td></tr>
                  )}
                </tbody>
              </table>
            </section>
  )
}
