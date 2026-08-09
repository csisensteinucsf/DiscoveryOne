import { useEffect, useRef, useState } from "react";
import { Paperclip, X } from 'lucide-react';
import FileDropZone from './FileDropZone.jsx';
import { DeleteIconButton, EditIconButton } from './RowActionIconButton.jsx';
import {
  ATTACH_ACCEPT,
  CURRENT_USERNAME,
  NOTE_ATTACHMENT_HELP_TEXT,
  absoluteUrl,
  appendStatusDetail,
  attachmentKind,
  canPreviewAttachment,
  fileLabelForAttachment,
  fileToneForAttachment,
  formatAttachmentSize,
  isImageAttachment,
  mapNote,
  pacificStamp,
  serverCreateNote,
  serverDeleteAttachment,
  serverDeleteNote,
  serverLoadNotes,
  serverUpdateNote,
  serverUploadAttachment,
} from './notesPanelData.js';
export default function NotesPanel({ caseId, apiSuffix = "notes", notify, readOnly = false, allowCreate = !readOnly, onCountChange, draftControlsBeforeAttach = null }) {
  const [notes, setNotes] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draftFiles, setDraftFiles] = useState([]);
  const draftFileInputRef = useRef(null);
  const [preview, setPreview] = useState(null);

  // load server copy of the notes list
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      const data = await serverLoadNotes(caseId, apiSuffix);
      if (cancelled) return;
      if (!data) {
        setNotes([]);
        notify && notify("Unable to load notes from server.");
      } else {
        setNotes(data.map(n => mapNote(n, caseId)).sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || "")));
      }
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [caseId, apiSuffix, notify]);

  useEffect(() => {
    onCountChange?.(notes.length);
  }, [notes.length, onCountChange]);

  const resetDraftAttachments = () => {
    setDraftFiles([]);
    if (draftFileInputRef.current) {
      draftFileInputRef.current.value = '';
    }
  };

  const openPreview = (attachment) => {
    if (!attachment) return;
    setPreview({
      src: absoluteUrl(attachment.url),
      name: attachment.filename || "Attachment",
      kind: attachmentKind(attachment),
      label: fileLabelForAttachment(attachment),
      size: formatAttachmentSize(attachment.size),
    });
  };

  const closePreview = () => setPreview(null);

  const handleDraftAttachmentChange = (event) => {
    const files = Array.from(event.target.files || []);
    if (files.length) {
      setDraftFiles(prev => [...prev, ...files]);
    }
    if (event.target) event.target.value = '';
  };

  const removeDraftAttachment = (index) => {
    setDraftFiles(prev => prev.filter((_, idx) => idx !== index));
  };

  const uploadAttachments = async (noteId, files, { silent = false } = {}) => {
    const list = Array.from(files || []);
    if (!list.length) return [];
    const uploaded = [];
    for (const file of list) {
      try {
        const attachment = await serverUploadAttachment(caseId, noteId, file);
        if (attachment) uploaded.push(attachment);
      } catch (err) {
        if (!silent && notify) notify(err?.message || "Unable to upload attachment");
        throw err;
      }
    }
    return uploaded;
  };

  const addAttachmentsToNote = async (noteId, files) => {
    try {
      const uploaded = await uploadAttachments(noteId, files);
      if (uploaded.length) {
        setNotes(prev => prev.map(n => n.id === noteId ? { ...n, attachments: [...(n.attachments || []), ...uploaded] } : n));
        notify && notify(uploaded.length > 1 ? "Attachments uploaded" : "Attachment uploaded");
      }
    } catch {
      // uploadAttachments already notified
    }
  };

  const removeAttachmentFromNote = async (noteId, attachmentId) => {
    try {
      await serverDeleteAttachment(caseId, noteId, attachmentId);
      setNotes(prev => prev.map(n => n.id === noteId ? { ...n, attachments: (n.attachments || []).filter(att => att.id !== attachmentId) } : n));
      notify && notify("Attachment removed");
    } catch (err) {
      notify && notify(err?.message || "Unable to delete attachment");
    }
  };

  async function addNote() {
    if (!allowCreate) return
    const text = (draft || "").trim();
    if (!text) return;
    const candidate = mapNote({ body: text, author: CURRENT_USERNAME, attachments: [] }, caseId);
    setSaving(true);
    // optimistic
    setNotes(prev => [candidate, ...prev]);
    setDraft("");
    // server
    const created = await serverCreateNote(caseId, apiSuffix, candidate);
    if (created) {
      let finalNote = created;
      let attachmentUploadMessage = '';
      if (draftFiles.length) {
        try {
          const uploaded = await uploadAttachments(created.id, draftFiles, { silent: true });
          if (uploaded.length) {
            finalNote = { ...created, attachments: [...(created.attachments || []), ...uploaded] };
          }
        } catch (err) {
          attachmentUploadMessage = err?.message || "Unable to upload attachment.";
        }
      }
      setNotes(prev => [finalNote, ...prev.filter(n => n.id !== candidate.id)]);
      if (attachmentUploadMessage) {
        notify && notify(appendStatusDetail(attachmentUploadMessage, "Note was still saved."));
      } else {
        notify && notify("Note added");
      }
    } else {
      setNotes(prev => prev.filter(n => n.id !== candidate.id));
      notify && notify("Unable to save note. Please retry.");
    }
    resetDraftAttachments();
    setSaving(false);
  }

  async function updateNote(id, newBody) {
    if (readOnly) return
    const clean = (newBody || "").trim();
    let previous = null;
    // optimistic
    setNotes(prev => prev.map(n => {
      if (n.id === id) {
        previous = n;
        return { ...n, body: clean, updated_at: new Date().toISOString() };
      }
      return n;
    }));
    const updated = await serverUpdateNote(caseId, apiSuffix, id, { body: clean });
    if (updated) {
      setNotes(prev => prev.map(n => n.id === id ? updated : n));
      notify && notify("Note updated");
    } else {
      if (previous) {
        setNotes(prev => prev.map(n => n.id === id ? previous : n));
      }
      notify && notify("Unable to update note. Please retry.");
    }
  }

  async function deleteNote(id) {
    if (readOnly) return
    // optimistic
    let snapshot;
    setNotes(prev => {
      snapshot = prev.slice();
      return prev.filter(n => n.id !== id);
    });
    const ok = await serverDeleteNote(caseId, apiSuffix, id);
    if (!ok && snapshot) {
      setNotes(snapshot);
      notify && notify("Unable to delete note. Please retry.");
    } else if (ok) {
      notify && notify("Note deleted");
    }
  }

  function NoteItem({ note }) {
    const [editing, setEditing] = useState(false);
    const [text, setText] = useState(note.body || "");
    const [uploadingAttachment, setUploadingAttachment] = useState(false);
    const fileInputRef = useRef(null);

    const ts = pacificStamp(note.created_at ?? note.timestamp, { showTZ: true });
    const attachments = note.attachments || [];

    const renderAttachment = (att, key) => {
      const imageAttachment = isImageAttachment(att);
      const fileTone = fileToneForAttachment(att);
      const attachmentUrl = absoluteUrl(att.url);
      const attachmentLabel = fileLabelForAttachment(att);
      const attachmentSize = formatAttachmentSize(att.size);
      const previewable = canPreviewAttachment(att);
      return (
        <div key={key} style={{ width: 132 }}>
          {imageAttachment ? (
            <button
              type="button"
              onClick={() => openPreview(att)}
              aria-label={`Preview ${att.filename}`}
              style={{ display: "block", padding: 0, border: "none", background: "transparent", width: "100%", cursor: "pointer" }}
            >
              <img
                src={absoluteUrl(att.url)}
                alt={att.filename}
                style={{ width: "100%", height: 88, objectFit: "cover", borderRadius: 6, border: "1px solid #e5e7eb" }}
              />
            </button>
          ) : (
            <a
              href={attachmentUrl}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${att.filename}`}
              style={{
                display: "flex",
                position: "relative",
                width: "100%",
                height: 88,
                borderRadius: 6,
                border: `1px solid ${fileTone.border}`,
                alignItems: "stretch",
                justifyContent: "center",
                background: fileTone.bg,
                color: fileTone.color,
                fontSize: 13,
                fontWeight: 700,
                textDecoration: "none",
                padding: 10,
                overflow: "hidden",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: 5,
                  height: "100%",
                  background: fileTone.accent,
                }}
              />
              <span
                aria-hidden="true"
                style={{
                  display: "grid",
                  gridTemplateRows: "1fr auto",
                  gap: 8,
                  width: "100%",
                  minWidth: 0,
                }}
              >
                <span style={{ display: "grid", gap: 5, alignContent: "center" }}>
                  {[0, 1, 2].map((line) => (
                    <span
                      key={line}
                      style={{
                        display: "block",
                        width: `${82 - line * 14}%`,
                        height: 5,
                        borderRadius: 999,
                        background: line === 0 ? fileTone.accent : fileTone.border,
                        opacity: line === 0 ? 0.85 : 1,
                      }}
                    />
                  ))}
                </span>
                <span style={{ justifySelf: "start", fontSize: 12, letterSpacing: 0 }}>{attachmentLabel}</span>
              </span>
            </a>
          )}
          <div style={{ fontSize: 12, marginTop: 5, wordBreak: "break-word", lineHeight: 1.25 }}>{att.filename}</div>
          {attachmentSize && (
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>{attachmentSize}</div>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 4 }}>
            <a
              href={attachmentUrl}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 11 }}
            >
              Download
            </a>
            {previewable && (
              <button
                type="button"
                onClick={() => openPreview(att)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "#2563eb",
                  padding: 0,
                  fontSize: 11,
                  textDecoration: "underline",
                  cursor: "pointer",
                }}
              >
                Preview
              </button>
            )}
            {!readOnly && (
              <button
                className="btn danger"
                style={{ padding: "2px 6px", fontSize: 11, borderRadius: 8 }}
                onClick={() => removeAttachmentFromNote(note.id, att.id)}
              >
                Remove
              </button>
            )}
          </div>
        </div>
      );
    };

    const handleAttachmentChange = async (event) => {
      const files = Array.from(event.target.files || []);
      if (!files.length) return;
      setUploadingAttachment(true);
      try {
        await addAttachmentsToNote(note.id, files);
      } finally {
        setUploadingAttachment(false);
        if (event.target) event.target.value = '';
      }
    };

    const triggerAttachmentPicker = () => {
      if (fileInputRef.current) {
        fileInputRef.current.click();
      }
    };

    return (
      <div className="card" style={{ padding: 10, marginBottom: 8 }}>
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: "none" }}
          accept={ATTACH_ACCEPT}
          multiple
          onChange={handleAttachmentChange}
          disabled={uploadingAttachment}
        />
        {!editing ? (
          <div>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
              <span title={ts}>{ts} - {note.user_name ?? note.username ?? note.author ?? 'unknown'}</span>
            </div>
            {note.format === "html" ? (
              <div
                style={{ whiteSpace: "normal" }}
                dangerouslySetInnerHTML={{ __html: note.body || "<em>(empty)</em>" }}
              />
            ) : (
              <div style={{ whiteSpace: "pre-wrap" }}>
                {note.body || <em>(empty)</em>}
              </div>
            )}
            {attachments.length > 0 && (
              <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 12 }}>
                {attachments.map(att => renderAttachment(att, `${note.id}-${att.id}`))}
              </div>
            )}
            {!readOnly && (
              <FileDropZone
                multiple
                disabled={uploadingAttachment}
                onFiles={(files) => handleAttachmentChange({ target: { files } })}
                prompt="Drop files to attach to this note"
                className="file-drop-zone--compact"
              >
                <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                  <button
                    className="btn secondary"
                    onClick={triggerAttachmentPicker}
                    style={{ padding: "4px 8px", borderRadius: 10, fontSize: 12 }}
                    disabled={uploadingAttachment}
                  >
                    {uploadingAttachment ? "Uploading..." : <><Paperclip size={14} aria-hidden="true" /> Attach</>}
                  </button>
                  <EditIconButton label="Edit note" onClick={() => setEditing(true)} />
                  <DeleteIconButton label="Delete note" onClick={() => deleteNote(note.id)} />
                </div>
              </FileDropZone>
            )}
          </div>
        ) : (
          <div>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              rows={4}
              style={{ width: "100%", fontFamily: "inherit", fontSize: 14, padding: 8 }}
            />
            {attachments.length > 0 && (
              <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 12 }}>
                {attachments.map(att => renderAttachment(att, `${note.id}-edit-${att.id}`))}
              </div>
            )}
            <FileDropZone
              multiple
              disabled={uploadingAttachment}
              onFiles={(files) => handleAttachmentChange({ target: { files } })}
              prompt="Drop files to attach to this note"
              className="file-drop-zone--compact"
            >
              <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                <button
                  className="btn secondary"
                  onClick={triggerAttachmentPicker}
                  style={{ padding: "4px 8px", borderRadius: 10, fontSize: 12 }}
                  disabled={uploadingAttachment}
                >
                  {uploadingAttachment ? "Uploading..." : <><Paperclip size={14} aria-hidden="true" /> Attach</>}
                </button>
                <button className="btn" onClick={() => { setEditing(false); setText(note.body || ""); }} style={{ padding: "4px 8px", borderRadius: 10, fontSize: 12 }}>Cancel</button>
                <button className="btn secondary" onClick={async () => { await updateNote(note.id, text); setEditing(false); }} style={{ padding: "4px 8px", borderRadius: 10, fontSize: 12 }}>Save</button>
              </div>
            </FileDropZone>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <section className="card" role="tabpanel" aria-labelledby="tab-notes" style={{ padding: 12 }}>
        {allowCreate ? (
          <div>
            <label style={{ display: "block", fontSize: 13, color: "#334155", marginBottom: 6 }}>Add a note</label>
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              rows={4}
              placeholder="Type your note..."
              style={{ width: "100%", fontFamily: "inherit", fontSize: 14, padding: 8, border: "1px solid #e5e7eb", borderRadius: 8 }}
              disabled={saving}
            />
            <p style={{ color: "#6b7280", fontSize: 12, margin: "6px 0 10px" }}>
              {NOTE_ATTACHMENT_HELP_TEXT}
            </p>
            {draftFiles.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                {draftFiles.map((file, idx) => (
                  <span key={`${file.name}-${idx}`} style={{ fontSize: 12, background: "#f3f4f6", borderRadius: 999, padding: "3px 10px", display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span>{file.name}</span>
                    <button
                      type="button"
                      style={{ border: "none", background: "transparent", cursor: "pointer" }}
                      onClick={() => removeDraftAttachment(idx)}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <input
              type="file"
              multiple
              accept={ATTACH_ACCEPT}
              ref={draftFileInputRef}
              style={{ display: "none" }}
              onChange={handleDraftAttachmentChange}
              disabled={saving}
            />
            <FileDropZone
              multiple
              disabled={saving}
              onFiles={(files) => handleDraftAttachmentChange({ target: { files } })}
              prompt="Drop note attachments here"
              className="file-drop-zone--compact"
            >
              <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
                {draftControlsBeforeAttach}
                <button className="btn secondary" type="button" onClick={() => draftFileInputRef.current?.click()} disabled={saving}>
                  <Paperclip size={16} aria-hidden="true" /> Attach
                </button>
                <button className="btn secondary" onClick={addNote} disabled={!draft || saving}>{saving ? "Saving..." : "Add Note"}</button>
              </div>
            </FileDropZone>
          </div>
        ) : (
          <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 0 }}>Notes are read-only for this role.</p>
        )}

        <div style={{ height: 12 }} />
        {loading ? <div>Loading...</div> : (notes.length ? notes.map(n => <NoteItem key={n.id} note={n} />) : <em>No notes yet.</em>)}
      </section>

      {preview && (
        <div
          onClick={closePreview}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            background: "rgba(15,23,42,0.85)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 2000,
            padding: 16,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: preview.kind === "image" || preview.kind === "pdf" ? "#0f172a" : "#ffffff",
              padding: 16,
              borderRadius: 12,
              maxWidth: "90vw",
              maxHeight: "90vh",
              width: preview.kind === "pdf" ? "min(920px, 90vw)" : "auto",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {preview.kind === "image" ? (
              <img
                src={preview.src}
                alt={preview.name}
                style={{ maxWidth: "80vw", maxHeight: "70vh", borderRadius: 8, objectFit: "contain" }}
              />
            ) : preview.kind === "pdf" ? (
              <iframe
                title={preview.name}
                src={preview.src}
                style={{
                  width: "100%",
                  height: "min(70vh, 720px)",
                  border: "1px solid #334155",
                  borderRadius: 8,
                  background: "#ffffff",
                }}
              />
            ) : (
              <div
                style={{
                  width: "min(520px, 82vw)",
                  minHeight: 220,
                  display: "grid",
                  alignContent: "center",
                  justifyItems: "center",
                  gap: 14,
                  color: "#0f172a",
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    width: 128,
                    height: 160,
                    borderRadius: 8,
                    border: `1px solid ${fileToneForAttachment({ filename: preview.name }).border}`,
                    background: fileToneForAttachment({ filename: preview.name }).bg,
                    color: fileToneForAttachment({ filename: preview.name }).color,
                    display: "grid",
                    gridTemplateRows: "1fr auto",
                    padding: 16,
                    fontWeight: 800,
                    boxShadow: "0 18px 45px rgba(15,23,42,0.14)",
                  }}
                >
                  <span style={{ display: "grid", gap: 8, alignContent: "center" }}>
                    {[0, 1, 2, 3].map((line) => (
                      <span
                        key={line}
                        style={{
                          display: "block",
                          width: `${88 - line * 10}%`,
                          height: 7,
                          borderRadius: 999,
                          background: line === 0 ? fileToneForAttachment({ filename: preview.name }).accent : fileToneForAttachment({ filename: preview.name }).border,
                        }}
                      />
                    ))}
                  </span>
                  <span>{preview.label}</span>
                </div>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, wordBreak: "break-word" }}>{preview.name}</div>
                  {preview.size && <div style={{ marginTop: 4, color: "#64748b", fontSize: 13 }}>{preview.size}</div>}
                </div>
              </div>
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                color: preview.kind === "image" || preview.kind === "pdf" ? "#e2e8f0" : "#0f172a",
              }}
            >
              <span style={{ fontSize: 14, wordBreak: "break-word" }}>{preview.name}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <a className="btn secondary" href={preview.src} target="_blank" rel="noreferrer">
                  Download
                </a>
                <button className="btn" type="button" onClick={closePreview}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
