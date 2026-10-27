import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Bell, BookOpen, Check, ChevronDown, CircleHelp, Compass, Filter, LayoutDashboard, Plus, Search, ShieldCheck, Sparkles } from "lucide-react";

const API = "";
const categories = ["Electronics", "ID cards", "Keys", "Bags", "Books", "Clothing", "Water bottle", "Other"];
const initialForm = { type: "lost", title: "", description: "", category: "Electronics", color: "", brand: "", location: "", date_event: new Date().toISOString().slice(0, 10), contact_email: "" };

export default function App() {
  const [role, setRole] = useState("student");
  const [email, setEmail] = useState("maya@campus.edu");
  const [page, setPage] = useState("browse");
  const [items, setItems] = useState([]);
  const [claims, setClaims] = useState([]);
  const [myItems, setMyItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [matches, setMatches] = useState([]);
  const [filters, setFilters] = useState({ q: "", type: "", category: "", location: "", status: "open", date_from: "", date_to: "" });
  const [form, setForm] = useState(initialForm);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [readOnly, setReadOnly] = useState(false);

  const headers = { "Content-Type": "application/json", "X-User-Email": email, "X-User-Role": role };
  async function request(path, options = {}) {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...options.headers } });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Request failed");
    return body;
  }
  async function loadItems() {
    try {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      setItems(await request(`/items?${params}`));
    } catch (error) { setNotice(error.message); }
  }
  async function loadClaims() {
    try { setClaims(await request("/claims")); } catch (error) { setNotice(error.message); }
  }
  async function loadMyItems() {
    try { setMyItems(await request("/my/items")); } catch (error) { setNotice(error.message); }
  }
  useEffect(() => { loadItems(); }, [filters, email, role]);
  useEffect(() => {
    request("/config").then((config) => setReadOnly(config.read_only)).catch((error) => setNotice(error.message));
  }, []);
  useEffect(() => {
    if (!readOnly && (page === "admin" || page === "my")) loadClaims();
    if (page === "my") loadMyItems();
  }, [page, email, role, readOnly]);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [notice]);

  async function openItem(item) {
    setSelected(item);
    try { setMatches(await request(`/items/${item.id}/matches`)); }
    catch (error) { setNotice(error.message); }
  }
  async function submitReport(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await request("/items", { method: "POST", body: JSON.stringify(form) });
      setNotice(`Report submitted. ${result.matches.length} possible match(es) found.`);
      setForm({ ...initialForm, type: form.type, contact_email: email });
      await loadItems();
      await openItem(result.item);
      setPage("browse");
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }
  async function submitClaim(event) {
    event.preventDefault();
    const proof = event.currentTarget.elements.proof.value;
    try {
      await request("/claims", { method: "POST", body: JSON.stringify({ item_id: selected.id, proof_description: proof }) });
      setNotice("Claim sent to the campus admin for review.");
      setSelected(null);
      loadClaims();
    } catch (error) { setNotice(error.message); }
  }
  async function decide(claimId, status, adminNotes = "") {
    try {
      await request(`/claims/${claimId}`, {
        method: "PATCH",
        body: JSON.stringify({ status, admin_notes: adminNotes }),
      });
      setNotice(`Claim ${status}.`);
      loadClaims();
      loadItems();
    } catch (error) { setNotice(error.message); }
  }
  async function markReturned(itemId) {
    try {
      await request(`/items/${itemId}/return`, { method: "PATCH" });
      setNotice("Item marked as returned.");
      loadClaims();
      loadItems();
    } catch (error) { setNotice(error.message); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={() => { setPage("browse"); setSelected(null); }}>
        <span className="brand-icon"><Compass size={21} /></span><span>Campus<span className="brand-light">Loop</span><small>LOST & FOUND</small></span>
      </a>
      <div className="nav-label">WORKSPACE</div>
      <button className={`nav-item ${page === "browse" ? "active" : ""}`} onClick={() => { setPage("browse"); setSelected(null); }}><LayoutDashboard size={18} /> Browse items</button>
      {!readOnly && <>
        <button className={`nav-item ${page === "report" ? "active" : ""}`} onClick={() => { setPage("report"); setSelected(null); }}><Plus size={18} /> Report an item</button>
        <button className={`nav-item ${page === "my" ? "active" : ""}`} onClick={() => { setPage("my"); setSelected(null); }}><BookOpen size={18} /> My activity</button>
        {role === "admin" && <button className={`nav-item ${page === "admin" ? "active" : ""}`} onClick={() => { setPage("admin"); setSelected(null); }}><ShieldCheck size={18} /> Admin review</button>}
      </>}
      <div className="sidebar-bottom">
        <div className="help-card"><CircleHelp size={17} /><div><b>Need a hand?</b><span>Ask Campus Safety</span></div><ArrowRight size={15} /></div>
        <div className="profile">
          <div className="avatar">{role === "admin" ? "A" : email.slice(0, 1).toUpperCase()}</div>
          <div className="profile-info"><b>{role === "admin" ? "Campus Admin" : "Student"}</b><span>{email}</span></div>
          <ChevronDown size={16} />
        </div>
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="crumb">Campus services <span>/</span> <b>{pageLabel(page)}</b></div>
        <div className="top-actions">
          {!readOnly && <div className="role-switch">
            <label htmlFor="role">Preview as</label>
            <select id="role" value={role} onChange={(e) => {
              const next = e.target.value; setRole(next);
              setEmail(next === "admin" ? "admin@campus.edu" : "maya@campus.edu");
              setPage(next === "admin" ? "admin" : "browse"); setSelected(null);
            }}>
              <option value="student">Student</option><option value="admin">Admin</option>
            </select>
          </div>}
          <button className="icon-btn" title="Notifications"><Bell size={18} /><i /></button>
          <div className="avatar top-avatar">{role === "admin" ? "A" : "M"}</div>
        </div>
      </header>
      <div className="content">
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")}>×</button></div>}
        {page === "browse" && (selected ? <Detail item={selected} matches={matches} role={role} readOnly={readOnly} onBack={() => setSelected(null)} onClaim={submitClaim} /> :
          <Browse items={items} filters={filters} setFilters={setFilters} onOpen={openItem} onReport={() => setPage("report")} readOnly={readOnly} />)}
        {!readOnly && page === "report" && <Report form={form} setForm={setForm} submit={submitReport} busy={busy} />}
        {!readOnly && page === "my" && <MyActivity email={email} items={myItems} claims={claims} />}
        {!readOnly && page === "admin" && role === "admin" && <Admin claims={claims} decide={decide} onReturn={markReturned} />}
      </div>
    </main>
  </div>;
}

function pageLabel(page) { return ({ browse: "Browse items", report: "Report an item", my: "My activity", admin: "Admin review" })[page]; }

function Browse({ items, filters, setFilters, onOpen, onReport, readOnly }) {
  const update = (key, value) => setFilters((state) => ({ ...state, [key]: value }));
  return <>
    <div className="welcome-row"><div><div className="eyebrow">{readOnly ? "PUBLIC CAMPUS DEMO" : "YOUR CAMPUS, CONNECTED"}</div><h1>Find what’s <span>missing.</span></h1><p>{readOnly ? "Browse sample reports and possible matches. This shared demo is read-only." : "Lost something? Found something? Let’s get it back where it belongs."}</p></div>
      {!readOnly && <button className="primary-btn" onClick={onReport}><Plus size={17} /> Report an item</button>}</div>
    <div className="hero-strip"><div className="hero-mark"><Sparkles size={20} /></div><div><b>Good things find their way back.</b><span>Browse reports and let smart matching help reunite you with your item.</span></div><div className="hero-count"><strong>{items.length}</strong><span>OPEN REPORTS</span></div></div>
    <div className="section-head"><div><h2>Recent reports</h2><p>Browse items reported around campus</p></div><div className="view-tabs"><span className="selected">All reports</span><span>Map view <small>SOON</small></span></div></div>
    <div className="filters">
      <label className="searchbox"><Search size={17} /><input placeholder="Search reports..." value={filters.q} onChange={(e) => update("q", e.target.value)} /></label>
      <label><Filter size={15} /><select value={filters.type} onChange={(e) => update("type", e.target.value)}><option value="">All types</option><option value="lost">Lost</option><option value="found">Found</option></select></label>
      <label><select value={filters.category} onChange={(e) => update("category", e.target.value)}><option value="">All categories</option>{categories.map((x) => <option key={x}>{x}</option>)}</select></label>
      <label className="location-filter"><input placeholder="Location" value={filters.location} onChange={(e) => update("location", e.target.value)} /></label>
      <label><select aria-label="Status" value={filters.status} onChange={(e) => update("status", e.target.value)}><option value="">All statuses</option><option value="open">Open</option><option value="matched">Matched</option><option value="claimed">Claimed</option><option value="returned">Returned</option></select></label>
      <label className="date-filter"><span>From</span><input aria-label="Date from" type="date" value={filters.date_from} onChange={(e) => update("date_from", e.target.value)} /></label>
      <label className="date-filter"><span>To</span><input aria-label="Date to" type="date" value={filters.date_to} onChange={(e) => update("date_to", e.target.value)} /></label>
      <button className="clear-btn" onClick={() => setFilters({ q: "", type: "", category: "", location: "", status: "open", date_from: "", date_to: "" })}>Clear filters</button>
    </div>
    <div className="item-grid">{items.map((item) => <ItemCard key={item.id} item={item} onClick={() => onOpen(item)} />)}
      {!items.length && <div className="empty-state">No reports match your search. Try another filter or report an item.</div>}
    </div>
  </>;
}

function ItemCard({ item, onClick }) {
  const colors = { Electronics: "lavender", "ID cards": "mint", Keys: "yellow", Bags: "peach", Books: "blue", Clothing: "rose", "Water bottle": "mint" };
  return <button className="item-card" onClick={onClick}>
    <div className={`card-art ${colors[item.category] || "blue"}`}><span className={`type-pill ${item.type}`}>{item.type === "lost" ? "LOST" : "FOUND"}</span><div className="item-emoji">{categoryIcon(item.category)}</div><span className="category-chip">{item.category}</span></div>
    <div className="card-body"><div className="card-title-row"><h3>{item.title}</h3><span className="arrow-circle"><ArrowRight size={15} /></span></div><p>{item.description}</p><div className="card-meta"><span><Compass size={14} />{item.location}</span><span>{item.date_event}</span></div><div className="card-footer"><span className="posted"><span className="tiny-avatar">{(item.created_by || "s")[0].toUpperCase()}</span> Campus report</span><span className="match-hint"><Sparkles size={13} /> View matches</span></div></div>
  </button>;
}

function Detail({ item, matches, role, readOnly, onBack, onClaim }) {
  return <div className="detail-page"><button className="back-btn" onClick={onBack}><ArrowLeft size={16} /> Back to reports</button>
    <div className="detail-layout"><section className="detail-main">
      <div className={`detail-art ${item.type}`}><span className={`type-pill ${item.type}`}>{item.type.toUpperCase()}</span><div className="big-emoji">{categoryIcon(item.category)}</div></div>
      <div className="detail-summary"><span className="category-chip">{item.category}</span><h1>{item.title}</h1><p>{item.description}</p><div className="detail-facts"><span><Compass size={16} /> {item.location}</span><span>Reported {item.date_event}</span><span className="status-text">{item.status}</span></div></div>
      {!readOnly && item.type === "found" && item.status === "open" && <form className="claim-panel" onSubmit={onClaim}><h3>Is this yours?</h3><p>Share a detail only the owner would know. Your proof is visible only to campus administrators.</p><textarea name="proof" required minLength="8" placeholder="Describe an identifying mark, contents, or other proof of ownership..." /><button className="primary-btn" type="submit">Submit claim <ArrowRight size={16} /></button></form>}
    </section><aside className="match-sidebar"><div className="match-heading"><span className="match-icon"><Sparkles size={17} /></span><div><h2>Possible matches</h2><p>Smart suggestions for this report</p></div></div>
      {matches.length ? matches.map((match) => <div className="match-card" key={match.item.id}><div className="match-score">{match.score}<small>%</small></div><div className="match-content"><b>{match.item.title}</b><span>{match.item.location} · {match.item.date_event}</span><p>{match.explanation}</p></div></div>) : <div className="match-empty">No likely matches yet. We’ll keep looking as new reports come in.</div>}
      <div className="privacy-note"><ShieldCheck size={16} /><span>Contact details are private and never shown on public reports.</span></div>
    </aside></div>
  </div>;
}

function Report({ form, setForm, submit, busy }) {
  const update = (key, value) => setForm((state) => ({ ...state, [key]: value }));
  return <div className="report-page"><div className="eyebrow">HELP YOUR ITEM FIND ITS WAY HOME</div><h1>Make a report</h1><p className="page-intro">The more detail you share, the better chance we have of finding a match.</p>
    <div className="form-type"><button className={form.type === "lost" ? "chosen" : ""} onClick={() => update("type", "lost")} type="button">I lost something</button><button className={form.type === "found" ? "chosen" : ""} onClick={() => update("type", "found")} type="button">I found something</button></div>
    <form className="report-form" onSubmit={submit}>
      <div className="form-section-title"><span>01</span><div><b>Tell us about the item</b><small>Describe it so we can identify it.</small></div></div>
      <div className="form-grid"><Field label="Item name" required><input required minLength="2" maxLength="120" placeholder="e.g. Blue water bottle" value={form.title} onChange={(e) => update("title", e.target.value)} /></Field>
        <Field label="Category" required><select value={form.category} onChange={(e) => update("category", e.target.value)}>{categories.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Color" required><input required placeholder="e.g. Navy blue" value={form.color} onChange={(e) => update("color", e.target.value)} /></Field>
        <Field label="Brand (optional)"><input placeholder="e.g. Hydro Flask" value={form.brand} onChange={(e) => update("brand", e.target.value)} /></Field>
        <Field label="Description" required wide><textarea required minLength="4" placeholder="Add identifying details, stickers, marks, or contents..." value={form.description} onChange={(e) => update("description", e.target.value)} /></Field>
      </div>
      <div className="form-section-title second"><span>02</span><div><b>Where and when?</b><small>{form.type === "lost" ? "Where you last remember having it." : "Where the item is currently being kept."}</small></div></div>
      <div className="form-grid"><Field label={form.type === "lost" ? "Last seen location" : "Current location"} required><input required placeholder="e.g. North Library, second floor" value={form.location} onChange={(e) => update("location", e.target.value)} /></Field>
        <Field label={form.type === "lost" ? "Date lost" : "Date found"} required><input required type="date" value={form.date_event} onChange={(e) => update("date_event", e.target.value)} /></Field>
        <Field label="Your contact email" required wide><input required type="email" placeholder="you@campus.edu" value={form.contact_email || ""} onChange={(e) => update("contact_email", e.target.value)} /><small className="field-note">Kept private. Only campus admins can see your contact details.</small></Field>
      </div>
      <button className="primary-btn submit-report" disabled={busy}>{busy ? "Submitting..." : "Submit report"} <ArrowRight size={17} /></button>
    </form>
  </div>;
}

function Field({ label, required, wide, children }) {
  return <label className={`field ${wide ? "wide" : ""}`}><span>{label}{required && <i> *</i>}</span>{children}</label>;
}

function MyActivity({ email, items, claims }) {
  return <div className="activity-page"><div className="eyebrow">YOUR CAMPUS LOOP</div><h1>My activity</h1><p className="page-intro">Reports and claim decisions for {email}.</p>
    <div className="activity-panel"><h2><Compass size={18} /> Your reports</h2>
      {!items.length ? <div className="empty-state">You haven’t submitted any reports yet.</div> : items.map((item) => <div className="reviewed-row" key={item.id}><div><b>{item.title}</b><span>{item.type} · {item.location} · {item.date_event}</span></div><Status value={item.status} /></div>)}
    </div>
    <div className="activity-panel"><h2><BookOpen size={18} /> Your claims</h2>
      {!claims.length ? <div className="empty-state">You haven’t submitted any claims yet.</div> : claims.map((claim) => <div className="claim-row" key={claim.id}><div><b>{claim.item_title}</b><span>Submitted {new Date(claim.created_at).toLocaleDateString()}</span></div><Status value={claim.status} /><p>{claim.admin_notes || "Awaiting admin review"}</p></div>)}
    </div>
    <div className="privacy-note"><ShieldCheck size={16} /> Your proof details are private and visible only to admins.</div>
  </div>;
}

function Admin({ claims, decide, onReturn }) {
  const [notes, setNotes] = useState({});
  const pending = claims.filter((claim) => claim.status === "pending");
  const reviewed = claims.filter((claim) => claim.status !== "pending");
  return <div className="activity-page"><div className="eyebrow">CAMPUS OPERATIONS</div><h1>Admin review</h1><p className="page-intro">Verify claims and keep item statuses up to date.</p>
    <div className="admin-stats"><div><span>Needs review</span><b>{pending.length}</b></div><div><span>Reviewed claims</span><b>{reviewed.length}</b></div></div>
    <div className="activity-panel"><h2><ShieldCheck size={18} /> Pending claims</h2>
      {!pending.length ? <div className="empty-state">All caught up. New claims will appear here.</div> : pending.map((claim) => <div className="admin-claim" key={claim.id}><div className="claim-top"><div><span className="claim-id">CLAIM #{claim.id}</span><h3>{claim.item_title}</h3></div><Status value={claim.status} /></div><div className="proof-box"><small>CLAIMANT · {claim.claimant_email} · REPORT CONTACT · {claim.reporter_contact_email}</small><p>{claim.proof_description}</p></div><label className="admin-note-label">Admin note (optional)<textarea className="admin-note-input" value={notes[claim.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [claim.id]: event.target.value }))} maxLength={1000} placeholder="Add a note for the claimant..." /></label><div className="review-actions"><button className="reject-btn" onClick={() => decide(claim.id, "rejected", notes[claim.id])}>Reject</button><button className="approve-btn" onClick={() => decide(claim.id, "approved", notes[claim.id])}><Check size={15} /> Approve claim</button></div></div>)}
    </div>
    {reviewed.length > 0 && <div className="activity-panel reviewed"><h2>Reviewed</h2>{reviewed.map((claim) => <div className="reviewed-row" key={claim.id}><div><b>{claim.item_title}</b><span>{claim.claimant_email} · Report contact: {claim.reporter_contact_email}</span></div><Status value={claim.status} />{claim.status === "approved" && <button className="text-btn" onClick={() => onReturn(claim.item_id)}>Mark returned</button>}</div>)}</div>}
  </div>;
}

function Status({ value }) { return <span className={`status-pill ${value}`}>{value}</span>; }
function categoryIcon(category) {
  return ({ Electronics: "⌁", "ID cards": "▤", Keys: "⚿", Bags: "▣", Books: "▤", Clothing: "◈", "Water bottle": "♧", Other: "✦" })[category] || "✦";
}
