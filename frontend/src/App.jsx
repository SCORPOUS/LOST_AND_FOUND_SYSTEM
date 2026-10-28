import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import confetti from "canvas-confetti";
import Joyride, { STATUS } from "react-joyride";
import { Activity, ArrowLeft, ArrowRight, Bell, BookOpen, Check, ChevronDown, CircleHelp, Compass, Filter, Image as ImageIcon, LayoutDashboard, MapPin, Moon, Plus, Search, ShieldCheck, Sparkles, Sun, Trophy, Trash2, Upload, Users } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const API = "";
const categories = ["Electronics", "ID card", "ID cards", "Keys", "Bags", "Books", "Clothing", "Water bottle", "Other"];
const initialForm = { type: "lost", title: "", description: "", category: "Electronics", color: "", brand: "", location: "", date_event: new Date().toISOString().slice(0, 10), contact_email: "" };
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const TOUR_STEPS = [
  { target: "#tour-report", content: "Start here to report something you have lost or found.", disableBeacon: true },
  { target: "#tour-search", content: "Search the campus reports by item, color, or location." },
  { target: "#tour-matches", content: "Smart matching compares reports and suggests likely matches." },
  { target: "#tour-profile", content: "Your account, activity, and sign-in options are here." },
];

function relativeTime(value) {
  const timestamp = Date.parse(value || "");
  if (!Number.isFinite(timestamp)) return "recently";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} day(s) ago`;
}

function anonymousReportText(item) {
  const title = (item.title || "an item").trim().toLowerCase();
  const article = /^(a|an|the)\s/.test(title)
    ? ""
    : /\b(keys|earbuds|glasses|pants)\b/.test(title)
      ? ""
      : /^[aeiou]/.test(title) ? "an " : "a ";
  const verb = item.type === "found" ? "found" : "lost";
  return `A student ${verb} ${article}${title} near ${item.location || "campus"}`;
}

async function compressImage(file, blurred = false) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(800 / bitmap.width, 1200 / bitmap.height, 1);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Your browser could not process this image.");
  context.filter = blurred ? `blur(${Math.max(16, canvas.width * 0.025)}px)` : "none";
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/webp", 0.82));
  if (!blob) throw new Error("Your browser could not compress this image.");
  return new File([blob], file.name.replace(/\.[^.]+$/, ".webp"), { type: "image/webp" });
}

export default function App() {
  const prefersReducedMotion = useReducedMotion();
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("campusloop_token"));
  const [page, setPage] = useState("browse");
  const [items, setItems] = useState([]);
  const [recentReports, setRecentReports] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [claims, setClaims] = useState([]);
  const [myItems, setMyItems] = useState([]);
  const [account, setAccount] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminActivity, setAdminActivity] = useState([]);
  const [adminStats, setAdminStats] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detailReturnPage, setDetailReturnPage] = useState("browse");
  const [matches, setMatches] = useState([]);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [matchPopup, setMatchPopup] = useState(null);
  const [matchPopupQueue, setMatchPopupQueue] = useState([]);
  const [tourRun, setTourRun] = useState(false);
  const [filters, setFilters] = useState({ q: "", type: "", category: "", location: "", status: "open", date_from: "", date_to: "" });
  const [form, setForm] = useState(initialForm);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [safetyContact, setSafetyContact] = useState("");
  const [modal, setModal] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [events, setEvents] = useState([]);
  const [loginDestination, setLoginDestination] = useState("browse");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("campfindr_theme") === "dark");
  const shownMatchPopups = useRef(new Set());

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    localStorage.setItem("campfindr_theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    document.querySelectorAll(".content > *, .item-card, .activity-panel, .chart-card").forEach((element) => {
      element.classList.add("reveal");
      observer.observe(element);
    });
    return () => observer.disconnect();
  }, [page, items.length, selected]);

  async function request(path, options = {}) {
    const requestHeaders = { "Content-Type": "application/json", ...options.headers };
    if (token) requestHeaders.Authorization = `Bearer ${token}`;
    const response = await fetch(`${API}${path}`, { ...options, headers: requestHeaders });
    const body = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith("/auth/")) {
      localStorage.removeItem("campusloop_token");
      setToken(null);
      setUser(null);
      setSelected(null);
      setPage("browse");
    }
    if (!response.ok) throw new Error(body?.detail || "Request failed");
    return body;
  }

  async function exportReports() {
    try {
      const response = await fetch("/admin/export.csv", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "CSV export failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "campfindr-reports.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) { setNotice(error.message); }
  }

  useEffect(() => {
    request("/config").then((config) => {
      setReadOnly(config.read_only);
      setSafetyContact(config.campus_safety_contact);
    }).catch((error) => setNotice(error.message));
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }
    request("/auth/me").then(setUser).catch((error) => {
      setNotice(error.message);
      localStorage.removeItem("campusloop_token");
      setToken(null);
    });
  }, [token]);

  async function authenticate(path, payload) {
    const result = await request(path, { method: "POST", body: JSON.stringify(payload) });
    localStorage.setItem("campusloop_token", result.token);
    setToken(result.token);
    setUser(result.user);
    setPage(loginDestination);
    if (loginDestination === "report") {
      setForm({ ...initialForm, contact_email: result.user.email });
    }
    setModal("");
    setNotice("");
  }

  function openLogin(destination = "browse") {
    setLoginDestination(destination);
    setModal("login");
  }

  function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function goHome() {
    setPage("browse");
    setSelected(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function searchReports(query) {
    setFilters((state) => ({ ...state, q: query }));
    setPage("browse");
    setSelected(null);
    window.setTimeout(() => scrollToSection("report-list"), 30);
  }

  function startReport() {
    setSelected(null);
    if (readOnly) {
      setNotice("Reporting is disabled in this read-only public demo.");
      return;
    }
    if (!user && !readOnly) {
      openLogin("report");
      return;
    }
    setPage("report");
    if (user) setForm({ ...initialForm, contact_email: user.email });
    scrollToSection("browse-home");
  }

  async function logout() {
    try { await request("/auth/logout", { method: "POST" }); }
    catch (error) { setNotice(error.message); }
    localStorage.removeItem("campusloop_token");
    setToken(null);
    setUser(null);
    setSelected(null);
    setPage("browse");
  }

  async function loadItems() {
    setItemsLoading(true);
    try {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      setItems(await request(`/items?${params}`));
    } catch (error) { setNotice(error.message); }
    finally { setItemsLoading(false); }
  }
  async function loadClaims() {
    try { setClaims(await request("/claims")); } catch (error) { setNotice(error.message); }
  }
  async function loadMyItems() {
    try { setMyItems(await request("/my/items")); } catch (error) { setNotice(error.message); }
  }
  async function loadAccount() {
    try { setAccount(await request("/account")); } catch (error) { setNotice(error.message); }
  }
  async function loadAnalytics() {
    try { setAnalytics(await request("/dashboard/analytics")); } catch (error) { setNotice(error.message); }
  }
  async function loadAdminData() {
    try {
      const [students, activity, stats] = await Promise.all([
        request("/admin/users"),
        request("/admin/activity"),
        request("/admin/stats"),
      ]);
      setAdminUsers(students);
      setAdminActivity(activity);
      setAdminStats(stats);
    } catch (error) { setNotice(error.message); }
  }
  async function loadLeaderboard() {
    try { setLeaderboard(await request("/leaderboard")); }
    catch (error) { setNotice(error.message); }
  }
  useEffect(() => { loadItems(); }, [filters, user?.email, readOnly]);
  useEffect(() => {
    let active = true;
    const refreshRecentReports = async () => {
      try {
        const reports = await request("/items");
        if (active) setRecentReports(reports.slice(0, 8));
      } catch (error) {
        if (active) setNotice(error.message);
      }
    };
    refreshRecentReports();
    const interval = window.setInterval(refreshRecentReports, 60_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);
  useEffect(() => {
    if (!user || readOnly) return;
    if (page === "admin" || page === "my") loadClaims();
    if (page === "my") loadMyItems();
    if (page === "student") loadAnalytics();
    if (page === "account" || page === "profile") loadAccount();
    if (page === "leaderboard") loadLeaderboard();
    if (page === "admin" && user.role === "admin") loadAdminData();
  }, [page, user?.email, readOnly]);
  useEffect(() => { loadLeaderboard(); }, []);
  useEffect(() => {
    if (itemsLoading || page !== "browse" || selected || tourRun) return;
    if (localStorage.getItem("campfindr_tour_seen")) return;
    localStorage.setItem("campfindr_tour_seen", "true");
    setTourRun(true);
  }, [itemsLoading, page, selected, tourRun]);
  useEffect(() => {
    if (!selected || !matches.length) return;
    try {
      const seen = new Set(JSON.parse(localStorage.getItem("campfindr_seen_matches") || "[]"));
      const freshMatches = matches
        .filter((match) => match.score > 85)
        .filter((match) => {
          const key = [selected.id, match.item.id].sort((a, b) => a - b).join(":");
          return !seen.has(key);
        })
        .map((match) => ({ ...match, sourceId: selected.id }));
      setMatchPopupQueue(freshMatches);
    } catch (error) {
      setNotice(`Could not load match popup history: ${error.message}`);
    }
  }, [selected?.id, matches]);
  useEffect(() => {
    if (matchPopup || !matchPopupQueue.length) return;
    const [nextMatch, ...remaining] = matchPopupQueue;
    const key = [nextMatch.sourceId, nextMatch.item.id].sort((a, b) => a - b).join(":");
    if (shownMatchPopups.current.has(key)) {
      setMatchPopupQueue(remaining);
      return;
    }
    shownMatchPopups.current.add(key);
    try {
      const seen = new Set(JSON.parse(localStorage.getItem("campfindr_seen_matches") || "[]"));
      seen.add(key);
      localStorage.setItem("campfindr_seen_matches", JSON.stringify([...seen]));
    } catch (error) {
      setNotice(`Could not save match popup history: ${error.message}`);
    }
    setMatchPopupQueue(remaining);
    setMatchPopup(nextMatch);
    if (!prefersReducedMotion) {
      confetti({ particleCount: 85, spread: 72, origin: { y: 0.65 }, disableForReducedMotion: true });
    }
  }, [matchPopup, matchPopupQueue, prefersReducedMotion]);
  function handleTourCallback({ status }) {
    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) setTourRun(false);
  }
  function replayTour() {
    setSelected(null);
    setPage("browse");
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
    window.setTimeout(() => setTourRun(true), prefersReducedMotion ? 0 : 150);
  }
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [notice]);

  async function openItem(itemOrId, returnTo = "browse") {
    setMatches([]);
    setMatchesLoading(true);
    try {
      const itemId = typeof itemOrId === "object" ? itemOrId.id : itemOrId;
      const [latest, latestMatches] = await Promise.all([
        request(`/items/${itemId}`),
        request(`/reports/${itemId}/matches`),
      ]);
      setSelected(latest);
      setMatches(latestMatches);
      setDetailReturnPage(returnTo);
      setPage(returnTo);
    } catch (error) { setNotice(error.message); }
    finally { setMatchesLoading(false); }
  }
  async function submitReport(event, image) {
    event.preventDefault();
    setBusy(true);
    try {
      let image_url;
      let image_preview_url;
      if (image) {
        image_url = (await request("/uploads", {
          method: "POST",
          headers: { "Content-Type": image.file.type },
          body: image.file,
        })).image_url;
        if (["id card", "id cards"].includes(form.category.trim().toLowerCase())) {
          image_preview_url = (await request("/uploads?preview=true", {
            method: "POST",
            headers: { "Content-Type": image.blurredFile.type },
            body: image.blurredFile,
          })).image_url;
        }
      }
      const result = await request("/items", { method: "POST", body: JSON.stringify({ ...form, contact_email: user.email, image_url, image_preview_url }) });
      setNotice(`Report submitted. ${result.matches.length} possible match(es) found.`);
      setForm({ ...initialForm, type: form.type, contact_email: user.email });
      await loadItems();
      await openItem(result.item);
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }
  async function submitClaim(event) {
    event.preventDefault();
    const proof = event.currentTarget.elements.proof.value;
    try {
      await request("/claims", { method: "POST", body: JSON.stringify({ item_id: selected.id, proof_description: proof }) });
      setNotice("Claim sent to the campus admin for review.");
      await openItem(selected);
      await loadClaims();
    } catch (error) { setNotice(error.message); }
  }
  async function decide(claimId, status, adminNotes = "") {
    try {
      await request(`/claims/${claimId}`, { method: "PATCH", body: JSON.stringify({ status, admin_notes: adminNotes }) });
      setNotice(`Claim ${status}.`);
      await loadClaims();
      await loadItems();
      if (status === "approved") await loadLeaderboard();
    } catch (error) { setNotice(error.message); }
  }
  async function markCollected(claimId) {
    try {
      await request(`/claims/${claimId}/collect`, { method: "PATCH" });
      setNotice("Collection confirmed. Thank you!");
      await loadClaims();
      await loadItems();
    } catch (error) { setNotice(error.message); }
  }
  async function markReturned(itemId) {
    try {
      await request(`/items/${itemId}/return`, { method: "PATCH" });
      setNotice("Item marked as returned.");
      await loadClaims();
      await loadItems();
      await loadLeaderboard();
      await loadAdminData();
    } catch (error) { setNotice(error.message); }
  }
  async function changeOwnedItem(itemId, action) {
    try {
      await request(`/my/items/${itemId}/recover`, { method: "PATCH" });
      setNotice("Report marked recovered.");
      await loadMyItems();
      await loadItems();
    } catch (error) { setNotice(error.message); }
  }
  async function deleteReport(itemId) {
    if (!window.confirm("Delete this open report? This cannot be undone.")) return;
    try {
      await request(`/items/${itemId}`, { method: "DELETE" });
      setMyItems((current) => current.filter((item) => item.id !== itemId));
      setItems((current) => current.filter((item) => item.id !== itemId));
      if (selected?.id === itemId) {
        setSelected(null);
        setPage(detailReturnPage);
      }
      setNotice("Report deleted.");
    } catch (error) { setNotice(error.message); }
  }

  const role = user?.role || "guest";

  return <>
    <Landing
      recentReports={recentReports}
      prefersReducedMotion={prefersReducedMotion}
      onHome={goHome}
      onContact={() => setModal("contact")}
      onHelp={() => setModal("help")}
      onGuidelines={() => setModal("guidelines")}
      onLogin={() => openLogin("browse")}
      onReport={startReport}
      onBrowse={() => { setFilters((state) => ({ ...state, type: "lost" })); goHome(); }}
      onSearch={searchReports}
    />
    <HowItWorks prefersReducedMotion={prefersReducedMotion} />
    <div className="app-shell" id="browse-home">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setPage("browse"); setSelected(null); }}>
        <img className="workspace-logo" src="/campfindr-logo.png" alt="CampFindr" />
      </a>
      <div className="nav-label">WORKSPACE</div>
      <button className={`nav-item ${page === "browse" ? "active" : ""}`} onClick={() => { setPage("browse"); setSelected(null); }}><LayoutDashboard size={18} /> Browse items</button>
      <button className={`nav-item ${page === "leaderboard" ? "active" : ""}`} onClick={() => { setPage("leaderboard"); setSelected(null); }}><Trophy size={18} /> Leaderboard</button>
      {!readOnly && <>
        {role === "student" && <button className={`nav-item ${page === "student" ? "active" : ""}`} onClick={() => { setPage("student"); setSelected(null); }}><Activity size={18} /> Student dashboard</button>}
        <button className={`nav-item ${page === "report" ? "active" : ""}`} onClick={startReport}><Plus size={18} /> Report an item</button>
        <button className={`nav-item ${page === "my" ? "active" : ""}`} onClick={() => { setPage("my"); setSelected(null); }}><BookOpen size={18} /> My activity</button>
        {role === "admin" && <button className={`nav-item ${page === "admin" ? "active" : ""}`} onClick={() => { setPage("admin"); setSelected(null); }}><ShieldCheck size={18} /> Admin dashboard</button>}
      </>}
      <button className={`nav-item ${page === "about" ? "active" : ""}`} onClick={() => { setPage("about"); setSelected(null); }}><CircleHelp size={18} /> About</button>
      <div className="sidebar-bottom">
        <button className="help-card" onClick={() => setModal("safety")}><CircleHelp size={17} /><div><b>Need a hand?</b><span>Ask Campus Safety</span></div><ArrowRight size={15} /></button>
        {user ? <div className="profile-wrap">
          <button className="profile" onClick={() => setProfileOpen(!profileOpen)} aria-expanded={profileOpen}>
            <div className="avatar">{user.name.trim().charAt(0).toUpperCase()}</div>
            <div className="profile-info"><b>{user.name}</b><span>{user.email}</span></div>
            <ChevronDown size={16} />
          </button>
          {profileOpen && <div className="menu profile-menu">
            <button onClick={() => { setPage("account"); setSelected(null); setProfileOpen(false); }}>Account</button>
            <button onClick={() => { setPage("profile"); setSelected(null); setProfileOpen(false); }}>Profile</button>
            <button onClick={() => { setPage("my"); setSelected(null); setProfileOpen(false); }}>My activity</button>
            <button onClick={logout}>Log out</button>
          </div>}
        </div> : <button className="profile visitor-profile" onClick={() => openLogin("browse")}><div className="avatar">G</div><div className="profile-info"><b>Guest visitor</b><span>Sign in to report or claim</span></div></button>}
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="crumb">Campus services <span>/</span> <b>{selected ? "Item details" : pageLabel(page)}</b></div>
        <div className="top-actions">
          <button className="icon-btn theme-toggle" aria-label={`Switch to ${darkMode ? "light" : "dark"} mode`} title={`Switch to ${darkMode ? "light" : "dark"} mode`} onClick={() => setDarkMode((mode) => !mode)}>{darkMode ? <Sun size={18} /> : <Moon size={18} />}</button>
          <div className="dropdown-wrap">
            <button className="icon-btn" title="Notifications" aria-label="Recent events" onClick={async () => {
              const next = !eventsOpen;
              setEventsOpen(next);
              if (next && !readOnly) {
                try { setEvents(await request("/my/events")); } catch (error) { setNotice(error.message); }
              }
            }}><Bell size={18} /><i /></button>
            {eventsOpen && <div className="menu events-menu"><b>Recent events</b>
              {readOnly ? <p>Events are unavailable in read-only mode.</p> : events.length ? events.map((event, index) => <p key={`${event.type}-${index}`}>{event.message}{event.admin_notes && <small>{event.admin_notes}</small>}</p>) : <p>No recent events.</p>}
            </div>}
          </div>
          {user ? <button id="tour-profile" className="avatar top-avatar account-button" aria-label="Account" title="Account" onClick={() => { setPage("account"); setSelected(null); }}>{user.name.trim().charAt(0).toUpperCase()}</button> : <button id="tour-profile" className="avatar top-avatar account-button" aria-label="Sign in" title="Sign in" onClick={() => openLogin("browse")}>G</button>}
        </div>
      </header>
      <div className="content">
        {readOnly && <div className="readonly-banner" role="status">Read-only public demo — reports, claims, and admin actions are disabled.</div>}
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")}>×</button></div>}
        {selected && <Detail item={selected} matches={matches} matchesLoading={matchesLoading} role={role} readOnly={readOnly} token={token} prefersReducedMotion={prefersReducedMotion} backLabel={detailReturnPage === "my" ? "Back to My activity" : "Back to reports"} onBack={() => setSelected(null)} onClaim={submitClaim} onOpen={(item) => openItem(item, detailReturnPage)} onDelete={deleteReport} />}
        {!selected && page === "browse" && <Browse items={items} filters={filters} setFilters={setFilters} onOpen={openItem} onReport={startReport} readOnly={readOnly} loading={itemsLoading} />}
        {!selected && !readOnly && user && page === "report" && <Report form={form} setForm={setForm} submit={submitReport} busy={busy} onError={setNotice} />}
        {!selected && !readOnly && !user && page === "report" && <div className="activity-page"><h1>Sign in to report an item</h1><p className="page-intro">Sign in or create a student account to submit a report.</p><button className="primary-btn" onClick={() => openLogin("report")}>Login to continue</button></div>}
        {!selected && readOnly && page === "my" && <div className="activity-page"><h1>My activity</h1><p className="page-intro">My activity isn’t available in the read-only public demo.</p></div>}
        {!selected && !readOnly && user && page === "my" && <MyActivity email={user.email} items={myItems} claims={claims} onCollect={markCollected} onItemAction={changeOwnedItem} onOpen={(id) => openItem(id, "my")} onDelete={deleteReport} />}
        {!selected && !readOnly && user && page === "student" && role === "student" && <StudentDashboard data={analytics} />}
        {!selected && !readOnly && user && (page === "account" || page === "profile") && <AccountPage data={account} title={page === "profile" ? "Profile" : "Account"} />}
        {!selected && page === "leaderboard" && <Leaderboard data={leaderboard} />}
        {!selected && page === "about" && <About />}
        {!selected && !readOnly && page === "admin" && role === "admin" && <Admin claims={claims} decide={decide} onReturn={markReturned} onExport={exportReports} students={adminUsers} activity={adminActivity} stats={adminStats} />}
      </div>
    </main>
    </div>
    <nav className="mobile-nav" aria-label="Mobile navigation">
      <button className={page === "browse" && !selected ? "active" : ""} onClick={() => { setPage("browse"); setSelected(null); }}><LayoutDashboard size={19} /><span>Browse</span></button>
      <button className={page === "leaderboard" ? "active" : ""} onClick={() => { setPage("leaderboard"); setSelected(null); }}><Trophy size={19} /><span>Leaderboard</span></button>
      {!readOnly && <button className="mobile-report-nav" onClick={startReport}><Plus size={19} /><span>Report</span></button>}
      {!readOnly && user && <button className={page === (role === "admin" ? "admin" : "student") ? "active" : ""} onClick={() => { setPage(role === "admin" ? "admin" : "student"); setSelected(null); }}><Activity size={19} /><span>{role === "admin" ? "Admin" : "Insights"}</span></button>}
      {!readOnly && user && <button className={page === "my" ? "active" : ""} onClick={() => { setPage("my"); setSelected(null); }}><BookOpen size={19} /><span>Activity</span></button>}
      <button className={page === "account" || page === "profile" ? "active" : ""} onClick={() => { if (!user) openLogin("browse"); else setProfileOpen((open) => !open); }}><Users size={19} /><span>Account</span></button>
      {profileOpen && user && <div className="mobile-profile-menu">
        <button onClick={() => { setPage("account"); setSelected(null); setProfileOpen(false); }}>Account</button>
        <button onClick={() => { setPage("profile"); setSelected(null); setProfileOpen(false); }}>Profile</button>
        <button onClick={() => { setPage("my"); setSelected(null); setProfileOpen(false); }}>My activity</button>
        <button onClick={() => { setPage("about"); setSelected(null); setProfileOpen(false); }}>About</button>
        <button onClick={logout}>Log out</button>
      </div>}
    </nav>
    {!readOnly && <button className="floating-report" onClick={startReport} aria-label="Report an item"><Plus size={19} /><span>Report item</span></button>}
    {modal === "safety" && <Modal title="Ask Campus Safety" onClose={() => setModal("")}><p>For help with an item or a safety concern, contact Campus Safety:</p><a href={`mailto:${safetyContact}`}>{safetyContact}</a></Modal>}
    {modal === "contact" && <Modal title="Contact" onClose={() => setModal("")}><ContactCard title="Contact" /></Modal>}
    {modal === "help" && <Modal title="Help Centre" onClose={() => setModal("")}><ContactCard title="Help Centre" help /></Modal>}
    {modal === "guidelines" && <Modal title="Pickup Guidelines" onClose={() => setModal("")}><PickupGuidelines /></Modal>}
    {modal === "login" && <Login onAuthenticate={authenticate} notice={notice} onClose={() => setModal("")} />}
    <footer className="site-footer"><a href="#top" onClick={(event) => { event.preventDefault(); goHome(); }}><img src="/campfindr-logo.png" alt="CampFindr" /></a><span>Campus Lost &amp; Found</span><button className="replay-tour" onClick={replayTour}>Replay tour</button></footer>
    <Joyride
      steps={TOUR_STEPS}
      run={tourRun}
      continuous
      showProgress
      showSkipButton
      disableAnimation={Boolean(prefersReducedMotion)}
      callback={handleTourCallback}
      styles={{ options: { primaryColor: "#168778", zIndex: 1600 } }}
    />
    <MatchPopup
      match={matchPopup}
      prefersReducedMotion={prefersReducedMotion}
      onClose={() => setMatchPopup(null)}
      onOpen={() => {
        const item = matchPopup?.item;
        setMatchPopup(null);
        setMatchPopupQueue([]);
        if (item) openItem(item, detailReturnPage);
      }}
    />
  </>;
}

function Landing({ recentReports, prefersReducedMotion, onHome, onContact, onHelp, onGuidelines, onLogin, onReport, onBrowse, onSearch }) {
  const [query, setQuery] = useState("");
  const [playLogoIntro, setPlayLogoIntro] = useState(false);
  useEffect(() => {
    if (sessionStorage.getItem("campfindr_logo_intro_seen")) return;
    sessionStorage.setItem("campfindr_logo_intro_seen", "true");
    setPlayLogoIntro(true);
  }, []);
  return <section className="landing-hero" id="top">
    <nav className="landing-nav" aria-label="Main navigation">
      <a className="findr-brand" href="#top" onClick={(event) => { event.preventDefault(); onHome(); }}><img src="/campfindr-logo.png" alt="CampFindr" />
        {playLogoIntro && !prefersReducedMotion && <>
          <motion.span className="brand-intro-pin" initial={{ y: -26, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ type: "spring", stiffness: 430, damping: 17 }} aria-hidden="true"><MapPin size={16} fill="currentColor" /></motion.span>
          <motion.span className="brand-intro-lens" initial={{ scale: 0.8 }} animate={{ scale: [1, 1.38, 1] }} transition={{ delay: 0.55, duration: 0.65, ease: "easeInOut" }} aria-hidden="true"><Search size={16} /></motion.span>
        </>}
      </a>
      <div className="landing-links">
        <button onClick={onHome}>Home</button>
        <button onClick={onContact}>Contact</button>
        <button onClick={onHelp}>Help Centre</button>
        <button onClick={onGuidelines}>Pickup Guidelines</button>
      </div>
      <label className="landing-search" id="tour-search"><Search size={15} /><input type="search" placeholder="Search lost items" aria-label="Search lost and found reports" value={query} onChange={(event) => { setQuery(event.target.value); onSearch(event.target.value); }} /><button type="button" aria-label="Search reports" onClick={() => onSearch(query)}><ArrowRight size={14} /></button></label>
      <button className="landing-login" onClick={onLogin}>Login</button>
    </nav>
    <ReportTicker reports={recentReports} prefersReducedMotion={prefersReducedMotion} />
    <div className="landing-content">
      <div className="landing-copy"><div className="landing-kicker">CAMPUS LOST &amp; FOUND</div><h1>Lost Something On Campus? Let&apos;s Help You Find It</h1><p>Search your campus reports, post what you lost or found, and let smart matching help reconnect you with what matters.</p>
        <div className="landing-actions"><button id="tour-report" className="landing-primary" onClick={onReport}>Report an Item <ArrowRight size={15} /></button><button className="landing-secondary" onClick={onBrowse}>Browse Lost Items</button></div>
      </div>
      <div className="landing-art" aria-label="Illustration of students finding lost belongings" role="img">
        <svg viewBox="0 0 460 330" aria-hidden="true">
          <path d="M56 77C76 32 148 45 191 52c49 8 89-24 143-4 54 20 85 61 74 119-8 43-31 81-75 105-44 24-105 9-151 14-50 6-110 8-137-33C17 210 31 130 56 77Z" fill="#F7DFAE"/>
          <path d="M71 91c62-27 111 19 169 4 52-13 104-31 143 1" fill="none" stroke="#E8C984" strokeWidth="3" strokeDasharray="7 9"/>
          <g fill="#fff" stroke="#173D37" strokeWidth="3"><rect x="68" y="106" width="36" height="44" rx="4"/><rect x="353" y="89" width="35" height="44" rx="4"/><rect x="345" y="210" width="39" height="47" rx="4"/><rect x="79" y="222" width="34" height="43" rx="4"/></g>
          <g fill="#F2A62B" stroke="#173D37" strokeWidth="3"><path d="M123 203h31v37h-31z"/><path d="M298 89h24v30h-24z"/><path d="M171 260h30v21h-30z"/></g>
          <g stroke="#173D37" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" fill="none"><path d="m181 115 30 25-16 42-31 28"/><path d="m211 140 36-22 26 15"/><path d="m195 181-28 3-17 33"/><path d="m238 128 23-26"/><path d="m266 159 32 23-6 39"/><path d="m266 159-30 32-29 1"/><path d="m286 219-18 25"/><path d="m236 191-18 39"/></g>
          <g fill="#F5A527" stroke="#173D37" strokeWidth="3"><circle cx="185" cy="106" r="13"/><circle cx="270" cy="151" r="13"/></g>
          <path d="M164 131 194 147 181 174l-31-12z" fill="#fff" stroke="#173D37" strokeWidth="3"/><path d="M245 175 269 164l22 17-11 24-32-3z" fill="#fff" stroke="#173D37" strokeWidth="3"/>
          <g transform="translate(304 222)"><circle cx="0" cy="0" r="22" fill="#fff" stroke="#173D37" strokeWidth="5"/><path d="m16 17 20 20" stroke="#173D37" strokeWidth="8" strokeLinecap="round"/><path d="M-9 2h18M0-7v18" stroke="#F2A62B" strokeWidth="4" strokeLinecap="round"/></g>
          <path d="M111 73h18m-9-9v18M320 65h15m-7-8v16" stroke="#fff" strokeWidth="4" strokeLinecap="round"/>
        </svg>
      </div>
    </div>
  </section>;
}

function ReportTicker({ reports, prefersReducedMotion }) {
  const entries = reports.map((item) => ({
    id: item.id,
    text: anonymousReportText(item),
    time: relativeTime(item.created_at),
  }));
  const items = entries.length ? [...entries, ...entries] : [{ id: "empty", text: "Loading recent campus reports", time: "" }];
  return <div className="report-ticker" aria-label="Recent anonymous campus reports">
    <span className="ticker-label"><i /> LIVE REPORTS</span>
    <div className="ticker-window">
      <motion.div
        className="ticker-track"
        animate={prefersReducedMotion || !entries.length ? undefined : { x: ["0%", "-50%"] }}
        transition={{ duration: 36, ease: "linear", repeat: Infinity }}
      >
        {items.map((entry, index) => <span className="ticker-entry" key={`${entry.id}-${index}`} aria-hidden={index >= entries.length}>
          <span>{entry.text}</span>{entry.time && <small>{entry.time}</small>}<i>✦</i>
        </span>)}
      </motion.div>
    </div>
  </div>;
}

function HowItWorks({ prefersReducedMotion }) {
  const steps = [
    { icon: Plus, title: "Report", description: "Share what you lost or found." },
    { icon: Search, title: "Match", description: "Smart suggestions compare report details." },
    { icon: Check, title: "Reunite", description: "Verify your item and get it back." },
  ];
  return <section className="how-it-works" aria-labelledby="how-it-works-title">
    <motion.div
      className="how-inner"
      initial={prefersReducedMotion ? false : "hidden"}
      whileInView="visible"
      viewport={{ once: true, amount: 0.25 }}
      variants={{ hidden: {}, visible: { transition: { staggerChildren: prefersReducedMotion ? 0 : 0.14 } } }}
    >
      <div className="how-heading"><span>THREE SIMPLE STEPS</span><h2 id="how-it-works-title">A little closer to found.</h2></div>
      <div className="how-steps">{steps.map(({ icon: Icon, title, description }, index) =>
        <motion.article
          className="how-step"
          key={title}
          variants={{
            hidden: { opacity: 0, y: prefersReducedMotion ? 0 : 18 },
            visible: { opacity: 1, y: 0, transition: { duration: prefersReducedMotion ? 0 : 0.45 } },
          }}
        >
          <span className="how-step-number">0{index + 1}</span><span className="how-step-icon"><Icon size={19} /></span>
          <div><h3>{title}</h3><p>{description}</p></div>
        </motion.article>
      )}</div>
    </motion.div>
  </section>;
}

function ContactCard({ title, help = false }) {
  return <section className="info-card">
    <div className="info-eyebrow">{help ? "WE'RE HERE TO HELP" : "GET IN TOUCH"}</div><h2>{title}</h2>
    {help && <p className="help-note">Help Centre and AI chatbot services are ongoing. We will fix them after updating and maintenance.</p>}
    <div className="contact-details"><b>R Kasinadh</b><span>B.Tech CSE student</span><span>SRM Institute of Science and Technology, Tiruchirappalli</span>
      <a href="mailto:rkkasinadh33@gmail.com">rkkasinadh33@gmail.com</a><a href="tel:+919846376243">9846376243</a>
    </div>
  </section>;
}

function PickupGuidelines() {
  return <section className="info-card">
    <div className="info-eyebrow">PICKUP GUIDELINES</div>
    <h2>Collect safely and securely</h2>
    <p>Submit a claim with a private identifying detail and wait for campus admin approval. Once approved, follow the collection location shown in My activity and bring your student ID.</p>
  </section>;
}

function Login({ onAuthenticate, notice, onClose }) {
  const [tab, setTab] = useState("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await onAuthenticate(tab === "signin" ? "/auth/login" : "/auth/register",
        tab === "signin" ? { email, password } : { name, email, password });
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <Modal title="Sign in to CampFindr" onClose={onClose} className="login-modal"><form className="auth-card" onSubmit={submit}>
    <img className="auth-logo" src="/campfindr-logo.png" alt="CampFindr" /><div className="eyebrow">CAMPUS LOST & FOUND</div><h1>Welcome to CampFindr</h1><p>Sign in to find what’s missing and help items get home.</p>
    <div className="auth-tabs"><button type="button" className={tab === "signin" ? "selected" : ""} onClick={() => { setTab("signin"); setError(""); }}>Sign in</button><button type="button" className={tab === "register" ? "selected" : ""} onClick={() => { setTab("register"); setError(""); }}>Create account</button></div>
    {tab === "register" && <label className="auth-field">Name<input required autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} /></label>}
    <label className="auth-field">Email<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
    <label className="auth-field">Password<input required type="password" minLength={tab === "register" ? 8 : undefined} autoComplete={tab === "register" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    {(error || notice) && <div className="auth-error" role="alert">{error || notice}</div>}
    <button className="primary-btn auth-submit" disabled={busy}>{busy ? "Please wait..." : tab === "signin" ? "Sign in" : "Create account"} <ArrowRight size={16} /></button>
    <small>Demo accounts: maya@campus.edu, sam@campus.edu, alex@campus.edu</small>
  </form></Modal>;
}

function Modal({ title, children, onClose, className = "" }) {
  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return <div className="modal-backdrop" onClick={onClose}><section className={`modal-card ${className}`} role="dialog" aria-modal="true" aria-label={title} onClick={(event) => event.stopPropagation()}><button className="modal-close" onClick={onClose} aria-label="Close">×</button><h2>{title}</h2>{children}</section></div>;
}

function pageLabel(page) { return ({ browse: "Browse items", report: "Report an item", my: "My activity", student: "Student dashboard", leaderboard: "Leaderboard", account: "Account", profile: "Profile", about: "About", admin: "Admin dashboard" })[page]; }

function Browse({ items, filters, setFilters, onOpen, onReport, readOnly, loading }) {
  const update = (key, value) => setFilters((state) => ({ ...state, [key]: value }));
  return <>
    <div className="welcome-row"><div><div className="eyebrow">{readOnly ? "PUBLIC CAMPUS DEMO" : "YOUR CAMPUS, CONNECTED"}</div><h1>Find what’s <span>missing.</span></h1><p>{readOnly ? "Browse sample reports and possible matches. This shared demo is read-only." : "Lost something? Found something? Let’s get it back where it belongs."}</p></div>
      {!readOnly && <button className="primary-btn" onClick={onReport}><Plus size={17} /> Report an item</button>}</div>
    <div className="hero-strip" id="tour-matches"><div className="hero-mark"><Sparkles size={20} /></div><div><b>Good things find their way back.</b><span>Browse reports and let smart matching help reunite you with your item.</span></div><div className="hero-count"><strong>{items.length}</strong><span>OPEN REPORTS</span></div></div>
    <div className="section-head" id="report-list"><div><h2>Recent reports</h2><p>Browse items reported around campus</p></div><div className="view-tabs"><span className="selected">All reports</span></div></div>
    <div className="filters">
      <label className="searchbox"><Search size={17} /><input placeholder="Search reports..." value={filters.q} onChange={(e) => update("q", e.target.value)} /></label>
      <label><Filter size={15} /><select value={filters.type} onChange={(e) => update("type", e.target.value)}><option value="">All types</option><option value="lost">Lost</option><option value="found">Found</option></select></label>
      <label><select value={filters.category} onChange={(e) => update("category", e.target.value)}><option value="">All categories</option>{categories.map((x) => <option key={x}>{x}</option>)}</select></label>
      <label className="location-filter"><input placeholder="Location" value={filters.location} onChange={(e) => update("location", e.target.value)} /></label>
      <label><select aria-label="Status" value={filters.status} onChange={(e) => update("status", e.target.value)}><option value="">All statuses</option><option value="open">Open</option><option value="matched">Matched</option><option value="claimed">Claimed</option><option value="returned">Returned</option><option value="recovered">Recovered</option></select></label>
      <label className="date-filter"><span>From</span><input aria-label="Date from" type="date" value={filters.date_from} onChange={(e) => update("date_from", e.target.value)} /></label>
      <label className="date-filter"><span>To</span><input aria-label="Date to" type="date" value={filters.date_to} onChange={(e) => update("date_to", e.target.value)} /></label>
      <button className="clear-btn" onClick={() => setFilters({ q: "", type: "", category: "", location: "", status: "open", date_from: "", date_to: "" })}>Clear filters</button>
    </div>
    <div className="item-grid">{loading ? Array.from({ length: 3 }, (_, index) => <div className="item-skeleton" key={index} aria-label="Loading report"><div /><span /><span /></div>) : items.map((item) => <ItemCard key={item.id} item={item} onClick={() => onOpen(item)} />)}
      {!loading && !items.length && <div className="empty-state"><Search size={26} /><b>No reports found</b><span>Try adjusting your filters, or be the first to report an item.</span></div>}
    </div>
  </>;
}

function isIdCard(item) {
  return ["id card", "id cards"].includes((item.category || "").trim().toLowerCase());
}

function ItemImage({ item, className = "", token = "" }) {
  const [securedUrl, setSecuredUrl] = useState("");
  const sensitive = isIdCard(item);
  const imageUrl = item.image_url;

  useEffect(() => {
    if (!imageUrl || !sensitive || !item.can_view_sensitive_image || !token) {
      setSecuredUrl("");
      return undefined;
    }
    let active = true;
    let objectUrl;
    fetch(imageUrl, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error("Image could not be loaded.");
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setSecuredUrl(objectUrl);
      })
      .catch(() => setSecuredUrl(""));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageUrl, sensitive, item.can_view_sensitive_image, token]);

  const src = sensitive && item.can_view_sensitive_image ? securedUrl : imageUrl;
  return <div className={`report-image ${className} ${sensitive && !item.can_view_sensitive_image ? "sensitive-photo" : ""}`}>
    {src ? <img src={src} alt="" loading="lazy" /> : <div className="image-placeholder"><ImageIcon size={34} /><span>{categoryIcon(item.category)}</span></div>}
  </div>;
}

function ItemCard({ item, onClick }) {
  const colors = { Electronics: "lavender", "ID cards": "mint", Keys: "yellow", Bags: "peach", Books: "blue", Clothing: "rose", "Water bottle": "mint" };
  return <button className="item-card" onClick={onClick} aria-label={`View details and matching items for ${item.title}`}>
    <div className={`card-art ${colors[item.category] || "blue"}`}><ItemImage item={item} /><span className={`type-pill ${item.type}`}>{item.type === "lost" ? "LOST" : "FOUND"}</span><span className="category-chip">{item.category}</span></div>
    <div className="card-body"><div className="card-title-row"><h3>{item.title}</h3><span className="arrow-circle"><ArrowRight size={15} /></span></div><p>{item.description}</p><div className="card-meta"><span><Compass size={14} />{item.location}</span><span>{item.date_event}</span></div><div className="card-footer"><span className="posted"><span className="tiny-avatar">C</span> Campus report</span><span className="match-hint"><Sparkles size={13} /> View details &amp; matches</span></div></div>
  </button>;
}

function Detail({ item, matches, matchesLoading, role, readOnly, token, prefersReducedMotion, backLabel, onBack, onClaim, onOpen, onDelete }) {
  return <div className="detail-page"><button className="back-btn" onClick={onBack}><ArrowLeft size={16} /> {backLabel}</button>
    <div className="detail-layout"><section className="detail-main">
      <div className={`detail-art ${item.type}`}><ItemImage item={item} className="detail-report-image" token={token} /><span className={`type-pill ${item.type}`}>{item.type.toUpperCase()}</span></div>
      <div className="detail-summary"><span className="category-chip">{item.category}</span><h1>{item.title}</h1><p>{item.description}</p><div className="detail-facts"><span><Compass size={16} /> {item.location}</span><span>Reported {item.date_event}</span><span className="status-text">{item.status}</span></div><ItemTimeline item={item} matches={matches} prefersReducedMotion={prefersReducedMotion} /></div>
      {!readOnly && item.is_owner && item.status === "open" && <button className="reject-btn detail-delete" onClick={() => onDelete(item.id)}>Delete report</button>}
      {!readOnly && role === "student" && !item.is_owner && item.type === "found" && item.status === "open" && <form className="claim-panel" onSubmit={onClaim}><h3>Is this yours?</h3><p>Share a detail only the owner would know. Your proof is visible only to campus administrators.</p><textarea name="proof" required minLength="8" placeholder="Describe an identifying mark, contents, or other proof of ownership..." /><button className="primary-btn" type="submit">Submit claim <ArrowRight size={16} /></button></form>}
    </section><aside className="match-sidebar"><div className="match-heading"><span className="match-icon"><Sparkles size={17} /></span><div><h2>Possible matches</h2><p>Smart suggestions for this report</p></div></div>
      {matchesLoading ? <div className="match-empty">Loading item details and match suggestions...</div> : matches.length ? matches.map((match) => <button className="match-card" key={match.item.id} onClick={() => onOpen(match.item)} aria-label={`Open possible match: ${match.item.title}, ${match.score}% match`}><div className="match-thumbnail"><ItemImage item={match.item} token={token} /></div><div className="match-content"><b>{match.item.title}</b><span>{match.item.location} · {match.item.date_event}</span><p>{match.explanation}</p></div><MatchScore score={match.score} /></button>) : <div className="match-empty">No likely matches yet. We’ll keep looking as new reports come in.</div>}
      <div className="privacy-note"><ShieldCheck size={16} /><span>Contact details are private and never shown on public reports.</span></div>
    </aside></div>
  </div>;
}

function MatchScore({ score }) {
  return <span className={`match-score ${score >= 70 ? "high" : "medium"}`} style={{ "--match-progress": `${score}%` }} role="img" aria-label={`${score}% match`}><span className="match-score-inner">{score}<small>%</small></span></span>;
}

function ItemTimeline({ item, matches, prefersReducedMotion }) {
  const returned = ["returned", "recovered"].includes(item.status) || Boolean(item.returned_at);
  const claimed = returned || item.status === "claimed";
  const matched = claimed || item.status === "matched" || matches.length > 0;
  const currentStep = returned ? 3 : claimed ? 2 : matched ? 1 : 0;
  const steps = ["Reported", "Matched", "Claimed", "Returned"];
  return <section className="item-timeline" aria-label="Item status timeline">
    <h2>Item timeline</h2>
    <div className="timeline-steps">
      <motion.span
        className="timeline-progress"
        initial={prefersReducedMotion ? false : { width: 0 }}
        whileInView={{ width: `${(currentStep / (steps.length - 1)) * 100}%` }}
        viewport={{ once: true }}
        transition={{ duration: prefersReducedMotion ? 0 : 0.65, ease: "easeOut" }}
      />
      {steps.map((step, index) => {
        const complete = index <= currentStep;
        return <div className={`timeline-step ${complete ? "complete" : ""} ${index === currentStep ? "current" : ""}`} key={step}>
          <motion.span
            className="timeline-dot"
            initial={prefersReducedMotion ? false : { scale: 0.5, opacity: 0.5 }}
            whileInView={{ scale: 1, opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: prefersReducedMotion ? 0 : 0.28, delay: prefersReducedMotion ? 0 : index * 0.12 }}
          />
          <span className="timeline-label">{step}</span>
        </div>;
      })}
    </div>
  </section>;
}

function MatchPopup({ match, prefersReducedMotion, onClose, onOpen }) {
  return <AnimatePresence>
    {match && <motion.div
      className="match-popup-backdrop"
      initial={prefersReducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.section
        className="match-popup"
        role="dialog"
        aria-modal="true"
        aria-labelledby="match-popup-title"
        initial={prefersReducedMotion ? false : { opacity: 0, y: 18, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.98 }}
        transition={{ duration: prefersReducedMotion ? 0 : 0.24 }}
        onClick={(event) => event.stopPropagation()}
      >
        <button className="match-popup-close" onClick={onClose} aria-label="Close match suggestion">×</button>
        <span className="match-popup-sparkle"><Sparkles size={20} /></span>
        <h2 id="match-popup-title">We think we found it!</h2>
        <p>This report looks like a strong match for <b>{match.item.title}</b>.</p>
        <MatchScore score={match.score} />
        <button className="primary-btn" onClick={onOpen}>View possible match <ArrowRight size={16} /></button>
      </motion.section>
    </motion.div>}
  </AnimatePresence>;
}

function Report({ form, setForm, submit, busy, onError }) {
  const [image, setImage] = useState(null);
  const update = (key, value) => setForm((state) => ({ ...state, [key]: value }));
  useEffect(() => () => {
    if (image?.previewUrl) URL.revokeObjectURL(image.previewUrl);
  }, [image]);
  async function selectImage(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = "";
    const acceptedType = ["image/jpeg", "image/png", "image/webp"].includes(file.type);
    const acceptedName = /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!acceptedType && !acceptedName) {
      onError("Choose a JPG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      onError("Images must be 5 MB or smaller.");
      return;
    }
    try {
      const compressed = await compressImage(file);
      const blurredFile = await compressImage(compressed, true);
      setImage({
        file: compressed,
        blurredFile,
        previewUrl: URL.createObjectURL(compressed),
      });
      onError("");
    } catch (error) {
      onError(error.message || "This image could not be processed.");
    }
  }
  function removeImage() {
    if (image?.previewUrl) URL.revokeObjectURL(image.previewUrl);
    setImage(null);
  }
  return <div className="report-page"><div className="eyebrow">HELP YOUR ITEM FIND ITS WAY HOME</div><h1>Make a report</h1><p className="page-intro">The more detail you share, the better chance we have of finding a match.</p>
    <div className="form-type"><button className={form.type === "lost" ? "chosen" : ""} onClick={() => update("type", "lost")} type="button">I lost something</button><button className={form.type === "found" ? "chosen" : ""} onClick={() => update("type", "found")} type="button">I found something</button></div>
    <form className="report-form" onSubmit={(event) => submit(event, image)}>
      <div className="form-section-title"><span>01</span><div><b>Tell us about the item</b><small>Describe it so we can identify it.</small></div></div>
      <div className="form-grid"><Field label="Item name" required><input required minLength="2" maxLength="120" placeholder="e.g. Blue water bottle" value={form.title} onChange={(e) => update("title", e.target.value)} /></Field>
        <Field label="Category" required><select value={form.category} onChange={(e) => update("category", e.target.value)}>{categories.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Color" required><input required placeholder="e.g. Navy blue" value={form.color} onChange={(e) => update("color", e.target.value)} /></Field>
        <Field label="Brand (optional)"><input placeholder="e.g. Hydro Flask" value={form.brand} onChange={(e) => update("brand", e.target.value)} /></Field>
        <Field label="Description" required wide><textarea required minLength="4" placeholder="Add identifying details, stickers, marks, or contents..." value={form.description} onChange={(e) => update("description", e.target.value)} /></Field>
      </div>
      <div className="image-upload-section">
        <div><b>Item photo <span>Optional</span></b><small>JPG, PNG, or WebP · up to 5 MB. Images are resized before upload.</small></div>
        {image ? <div className="image-preview-card"><img src={image.previewUrl} alt="Selected item preview" /><div><b>Image ready</b><small>{(image.file.size / 1024).toFixed(0)} KB · resized for faster loading</small>{isIdCard(form) && <small>An anonymized blurred preview will be shown in reports.</small>}</div><button type="button" className="remove-image-btn" onClick={removeImage} aria-label="Remove selected image"><Trash2 size={17} /> Remove</button></div> :
          <label className="image-upload-control"><input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={selectImage} /><span className="upload-icon"><Upload size={19} /></span><span><b>Add a photo</b><small>Choose a JPG, PNG, or WebP image</small></span></label>}
      </div>
      <div className="form-section-title second"><span>02</span><div><b>Where and when?</b><small>{form.type === "lost" ? "Where you last remember having it." : "Where the item is currently being kept."}</small></div></div>
      <div className="form-grid"><Field label={form.type === "lost" ? "Last seen location" : "Current location"} required><input required placeholder="e.g. North Library, second floor" value={form.location} onChange={(e) => update("location", e.target.value)} /></Field>
        <Field label={form.type === "lost" ? "Date lost" : "Date found"} required><input required type="date" value={form.date_event} onChange={(e) => update("date_event", e.target.value)} /></Field>
        <Field label="Your contact email" required wide><input required type="email" readOnly value={form.contact_email || ""} /><small className="field-note">Account email; private and visible only to campus admins.</small></Field>
      </div>
      <button className="primary-btn submit-report" disabled={busy}>{busy ? "Uploading image and submitting..." : "Submit report"} <ArrowRight size={17} /></button>
    </form>
  </div>;
}

function Field({ label, required, wide, children }) {
  return <label className={`field ${wide ? "wide" : ""}`}><span>{label}{required && <i> *</i>}</span>{children}</label>;
}

function MyActivity({ email, items, claims, onCollect, onItemAction, onOpen, onDelete }) {
  const activateRow = (event, open) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  };
  return <div className="activity-page"><div className="eyebrow">CAMPFINDR COMMUNITY</div><h1>My activity</h1><p className="page-intro">Reports and claim decisions for {email}.</p>
    <div className="activity-panel"><h2><Compass size={18} /> Your reports</h2>
      {!items.length ? <div className="empty-state">You haven’t submitted any reports yet.</div> : items.map((item) => <div className="reviewed-row clickable-row" key={item.id} role="button" tabIndex={0} onClick={() => onOpen(item.id)} onKeyDown={(event) => activateRow(event, () => onOpen(item.id))}><div><b>{item.title}</b><span>{item.type} · {item.location} · {item.date_event}</span></div><Status value={item.status} />{item.type === "lost" && item.status === "open" && <button className="text-btn" onClick={(event) => { event.stopPropagation(); onItemAction(item.id, "recover"); }}>Recovered</button>}{item.status === "open" && <button className="text-btn danger-text" onClick={(event) => { event.stopPropagation(); onDelete(item.id); }}>Delete</button>}</div>)}
    </div>
    <div className="activity-panel"><h2><BookOpen size={18} /> Your claims</h2>
      {!claims.length ? <div className="empty-state">You haven’t submitted any claims yet.</div> : claims.map((claim) => <div className="claim-row clickable-row" key={claim.id} role="button" tabIndex={0} onClick={() => onOpen(claim.item_id)} onKeyDown={(event) => activateRow(event, () => onOpen(claim.item_id))}><div><b>{claim.item_title}</b><span>Submitted {new Date(claim.created_at).toLocaleDateString()}</span></div><Status value={claim.status} />
        {claim.status === "approved" ? <p className="approved-message">Approved: collect from {claim.collect_location}. Bring your student ID.{claim.admin_notes && <span className="admin-note-display">Admin note: {claim.admin_notes}</span>}</p> : <p>{claim.admin_notes || (claim.status === "pending" ? "Awaiting admin review" : "")}</p>}
        {claim.status === "approved" && <button className="approve-btn collect-btn" onClick={(event) => { event.stopPropagation(); onCollect(claim.id); }}><Check size={15} /> Confirm collected</button>}
      </div>)}
    </div>
    <div className="privacy-note"><ShieldCheck size={16} /> Your proof details are private and visible only to admins.</div>
  </div>;
}

function StudentDashboard({ data }) {
  const reportTypes = [
    { name: "Lost", value: data?.lost || 0 },
    { name: "Found", value: data?.found || 0 },
  ];
  const locations = data?.locations || [];
  return <div className="dashboard-page">
    <div className="eyebrow">CAMPFINDR COMMUNITY</div><h1>Student dashboard</h1>
    <p className="page-intro">A campus-wide snapshot of lost and found reports, activity over time, and the most active locations.</p>
    {!data ? <div className="activity-panel">Loading your report analytics...</div> : <>
      <div className="dashboard-metrics">
        <div><span>Total reports</span><b>{data.lost + data.found}</b></div>
        <div><span>Lost reports</span><b>{data.lost}</b></div>
        <div><span>Found reports</span><b>{data.found}</b></div>
      </div>
      <div className="charts-grid">
        <section className="chart-card"><h2><Activity size={17} /> Lost vs. found</h2>
          {(data.lost + data.found) === 0 ? <p className="chart-empty">Post a report to see this breakdown.</p> : <div className="chart-frame">
            <ResponsiveContainer width="100%" height={230}><PieChart><Pie data={reportTypes} dataKey="value" nameKey="name" innerRadius={55} outerRadius={82} paddingAngle={4}>{reportTypes.map((entry, index) => <Cell key={entry.name} fill={index === 0 ? "#e9a181" : "#32977e"} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer>
            <div className="chart-legend"><span><i className="legend-lost" />Lost {data.lost}</span><span><i className="legend-found" />Found {data.found}</span></div>
          </div>}
        </section>
        <section className="chart-card"><h2><Activity size={17} /> Reports over time</h2>
          {!data.timeline.length ? <p className="chart-empty">Reports will appear here as you post them.</p> : <ResponsiveContainer width="100%" height={250}><LineChart data={data.timeline} margin={{ top: 8, right: 12, left: -18, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#edf0f3" /><XAxis dataKey="date" tick={{ fontSize: 9 }} /><YAxis allowDecimals={false} tick={{ fontSize: 9 }} /><Tooltip /><Line type="monotone" dataKey="count" name="Reports" stroke="#32977e" strokeWidth={2.5} dot={{ r: 4 }} /></LineChart></ResponsiveContainer>}
        </section>
        <section className="chart-card chart-wide"><h2><MapPin size={17} /> Reports by campus area</h2>
          {!locations.length ? <p className="chart-empty">Locations will appear here as you post reports.</p> : <ResponsiveContainer width="100%" height={Math.max(220, locations.length * 38)}><BarChart data={locations} layout="vertical" margin={{ top: 2, right: 18, left: 8, bottom: 2 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#edf0f3" /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 9 }} /><YAxis type="category" dataKey="location" width={115} tick={{ fontSize: 9 }} /><Tooltip /><Bar dataKey="count" name="Reports" radius={[0, 5, 5, 0]}>{locations.map((location, index) => <Cell key={location.location} fill={["#25856b", "#39977e", "#57a990", "#7bbda8", "#a4d0c0"][Math.min(index, 4)]} />)}</Bar></BarChart></ResponsiveContainer>}
        </section>
      </div>
    </>}
  </div>;
}

function AccountPage({ data, title }) {
  return <div className="account-page"><div className="eyebrow">CAMPFINDR ACCOUNT</div><h1>{title}</h1><p className="page-intro">Your account details and sign-in activity.</p>
    {!data ? <div className="activity-panel">Loading your account...</div> : <section className="account-card">
      <div className="account-identity"><div className="account-avatar">{data.name.trim().charAt(0).toUpperCase()}</div><div><h2>{data.name}</h2><p>{data.email}</p></div></div>
      <div className="account-details">
        <div><span>Account type</span><b>{data.role}</b></div>
        <div><span>Member since</span><b>{new Date(data.created_at).toLocaleDateString()}</b></div>
        <div><span>Last login</span><b>{data.last_login_at ? new Date(data.last_login_at).toLocaleString() : "No login recorded"}</b></div>
        <div><span>Total logins</span><b>{data.total_logins}</b></div>
      </div>
      <div className="account-badge"><div><span>Good Samaritan returns</span><b>{data.returns}</b></div><div><span>Your badge</span><b>{data.badge || "No badge yet"}</b></div></div>
    </section>}
  </div>;
}

function Leaderboard({ data }) {
  return <div className="activity-page leaderboard-page">
    <div className="eyebrow">CAMPUS KINDNESS</div><h1>Good Samaritan leaderboard</h1>
    <p className="page-intro">Celebrating students who help found items make it back to their owners.</p>
    <section className="activity-panel"><h2><Trophy size={18} /> Top helpers</h2>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Rank</th><th>Student</th><th>Items returned</th><th>Badge</th></tr></thead><tbody>
        {data.map((student, index) => <tr key={`${student.name}-${index}`}><td>#{index + 1}</td><td>{student.name}</td><td>{student.returns}</td><td><span className="badge-pill">{student.badge}</span></td></tr>)}
        {!data.length && <tr><td colSpan="4">No returns have been recorded yet.</td></tr>}
      </tbody></table></div>
      <p className="badge-explainer">1 return: Helper · 5 returns: Good Samaritan · 10 returns: Campus Hero</p>
    </section>
  </div>;
}

function About() {
  return <div className="about-page"><div className="eyebrow">ABOUT CAMPFINDR</div><h1>Helping campus items find their way home.</h1>
    <section className="about-card"><h2>What this portal does</h2><p>CampFindr is a campus lost-and-found portal where students can report belongings they have lost or found, browse reports from around campus, and privately claim found items.</p><h3>How reporting and matching works</h3><p>When you submit a report, include the item’s category, color, identifying description, location, and the date it was lost or found. The portal compares lost and found reports using item details, location, and date to surface likely matches. Open a report to review its details and matching suggestions. If you recognize a found item, submit a private identifying detail for an administrator to verify.</p></section>
    <section className="author-card"><div className="author-avatar" aria-label="Avatar placeholder">RK</div><div><div className="eyebrow">AUTHOR</div><h2>R Kasinadh</h2><p>B.Tech CSE student</p><span>SRM Institute of Science and Technology, Tiruchirappalli</span></div></section>
  </div>;
}

function Admin({ claims, decide, onReturn, onExport, students, activity, stats }) {
  const [notes, setNotes] = useState({});
  const [activityQuery, setActivityQuery] = useState("");
  const [activityType, setActivityType] = useState("");
  const pending = claims.filter((claim) => claim.status === "pending");
  const reviewed = claims.filter((claim) => claim.status !== "pending");
  const filteredActivity = activity.filter((event) => {
    const matchesType = !activityType || event.event_type === activityType;
    const text = `${event.actor_name} ${event.actor_email} ${event.item_title} ${event.related_title} ${event.summary}`.toLowerCase();
    return matchesType && text.includes(activityQuery.toLowerCase());
  });
  const recoveryData = stats ? [{ name: "Returned", value: stats.returned_count }, { name: "Unclaimed", value: stats.unclaimed_count }] : [];
  return <div className="activity-page"><div className="admin-heading"><div><div className="eyebrow">CAMPUS OPERATIONS</div><h1>Admin dashboard</h1><p className="page-intro">Review student sign-ins and activity, then keep item statuses up to date.</p></div><button className="primary-btn" onClick={onExport}>Export CSV</button></div>
    {stats && <section className="admin-recovery">
      <div className="admin-recovery-cards">
        <div><span>Total reports</span><b>{stats.total_reports}</b></div>
        <div><span>Returned</span><b>{stats.returned_rate}%</b><small>{stats.returned_count} reports</small></div>
        <div><span>Unclaimed / not returned</span><b>{stats.unclaimed_rate}%</b><small>{stats.unclaimed_count} reports</small></div>
        <div><span>Average recovery time</span><b>{stats.average_recovery_hours < 24 ? `${stats.average_recovery_hours} hrs` : `${stats.average_recovery_days} days`}</b><small>Based on {stats.recovered_count} returned reports</small></div>
      </div>
      <div className="activity-panel admin-recovery-chart"><h2>Returned vs not returned</h2><div className="admin-pie"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={recoveryData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={72} paddingAngle={3}><Cell fill="#31977e" /><Cell fill="#f3a347" /></Pie><Tooltip /></PieChart></ResponsiveContainer></div><div className="chart-legend"><span><i className="returned-legend" />Returned</span><span><i className="unclaimed-legend" />Not returned</span></div></div>
    </section>}
    <div className="admin-stats"><div><span>Needs review</span><b>{pending.length}</b></div><div><span>Reviewed claims</span><b>{reviewed.length}</b></div></div>
    <section className="activity-panel"><h2><Users size={18} /> Student logins</h2>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Name</th><th>Email</th><th>Last login</th><th>Total logins</th></tr></thead><tbody>
        {students.map((student) => <tr key={student.email}><td>{student.name}</td><td>{student.email}</td><td>{student.last_login_at ? new Date(student.last_login_at).toLocaleString() : "Never"}</td><td>{student.total_logins}</td></tr>)}
        {!students.length && <tr><td colSpan="4">No student accounts found.</td></tr>}
      </tbody></table></div>
    </section>
    <section className="activity-panel"><h2><Activity size={18} /> Activity log</h2>
      <div className="activity-filters"><label><Search size={15} /><input placeholder="Search name, email, item..." value={activityQuery} onChange={(event) => setActivityQuery(event.target.value)} /></label><select aria-label="Filter activity type" value={activityType} onChange={(event) => setActivityType(event.target.value)}><option value="">All activity</option><option value="report">Reports</option><option value="claim">Claims</option><option value="match">Matches</option></select></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Activity</th><th>Student</th><th>Item</th><th>Timestamp</th></tr></thead><tbody>
        {filteredActivity.map((event, index) => <tr key={`${event.event_type}-${event.created_at}-${index}`}><td><span className={`event-tag ${event.event_type}`}>{event.event_type}</span><small>{event.summary}</small></td><td>{event.actor_name}<small>{event.actor_email}</small></td><td>{event.item_title}{event.related_title && <small>Match: {event.related_title}</small>}</td><td>{new Date(event.created_at).toLocaleString()}</td></tr>)}
        {!filteredActivity.length && <tr><td colSpan="4">No activity matches those filters.</td></tr>}
      </tbody></table></div>
    </section>
    <div className="activity-panel"><h2><ShieldCheck size={18} /> Pending claims</h2>
      {!pending.length ? <div className="empty-state">All caught up. New claims will appear here.</div> : pending.map((claim) => <div className="admin-claim" key={claim.id}><div className="claim-top"><div><span className="claim-id">CLAIM #{claim.id}</span><h3>{claim.item_title}</h3></div><Status value={claim.status} /></div><div className="proof-box"><small>CLAIMANT · {claim.claimant_email} · REPORT CONTACT · {claim.reporter_contact_email}</small><p>{claim.proof_description}</p></div><label className="admin-note-label">Admin note (optional)<textarea className="admin-note-input" value={notes[claim.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [claim.id]: event.target.value }))} maxLength={1000} placeholder="Add a note for the claimant..." /></label><div className="review-actions"><button className="reject-btn" onClick={() => decide(claim.id, "rejected", notes[claim.id])}>Reject</button><button className="approve-btn" onClick={() => decide(claim.id, "approved", notes[claim.id])}><Check size={15} /> Approve claim</button></div></div>)}
    </div>
    {reviewed.length > 0 && <div className="activity-panel reviewed"><h2>Reviewed</h2>{reviewed.map((claim) => <div className="reviewed-row" key={claim.id}><div><b>{claim.item_title}</b><span>{claim.claimant_email} · Report contact: {claim.reporter_contact_email}</span></div><Status value={claim.status} />{claim.status === "approved" && <button className="text-btn" onClick={() => onReturn(claim.item_id)}>Mark returned</button>}</div>)}</div>}
  </div>;
}

function Status({ value }) { return <span className={`status-pill ${value}`}>{value}</span>; }
function categoryIcon(category) {
  return ({ Electronics: "⌁", "ID card": "▤", "ID cards": "▤", Keys: "⚿", Bags: "▣", Books: "▤", Clothing: "◈", "Water bottle": "♧", Other: "✦" })[category] || "✦";
}
