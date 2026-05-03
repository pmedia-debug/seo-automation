#!/usr/bin/env python3
"""
app.py - SEO Schema Generator (Google Docs + OAuth2)
Deploy-ready for Render.com

Env vars (set in Render dashboard):
  SESSION_SECRET     - any long random string
  OAUTH_REDIRECT_URI - https://your-app.onrender.com/auth/callback
  OAUTHLIB_INSECURE_TRANSPORT=1 (local dev only, HTTP)

CHANGES:
  - Breadcrumb + FAQ schemas are ALWAYS generated for every doc URL.
  - Product / Blog schema is OPTIONAL — the user picks which one (or neither)
    via a toggle, then clicks Generate.  The toggle defaults to "none" so the
    first run always gives breadcrumb + FAQ only.
  - Added a "schema_type=none" path so the API can skip product/blog entirely.
"""

import os
import json
from flask import (Flask, request, jsonify, session,
                   redirect, url_for, render_template_string)
from google_docs_fetcher import (
    fetch_doc_data, credentials_to_dict,
    credentials_from_dict, CLIENT_SECRET_FILE, SCOPES,
)
from site_fetcher import fetch_site_assets
from seo_automation import build_all_schemas

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-change-in-prod")

# Allow HTTP in local dev
if os.environ.get("OAUTHLIB_INSECURE_TRANSPORT", "1") == "1":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _redirect_uri():
    return os.environ.get(
        "OAUTH_REDIRECT_URI",
        url_for("auth_callback", _external=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# OAuth2 routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/auth/login")
def auth_login():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    from google_auth_oauthlib.flow import Flow
    state = session.get("oauth_state", "")
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=_redirect_uri(),
    )
    auth_resp = request.url
    flow.fetch_token(authorization_response=auth_resp)
    creds = flow.credentials
    session["token"] = credentials_to_dict(creds)
    return redirect(url_for("home"))


@app.route("/auth/logout")
def auth_logout():
    session.pop("token", None)
    return redirect(url_for("home"))


# ─────────────────────────────────────────────────────────────────────────────
# Auth status helper
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/auth-status")
def api_auth_status():
    connected = "token" in session
    return jsonify({
        "connected": connected,
        "label": "Connected via Google OAuth2" if connected else "Not connected",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Generate API
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
def api_generate():
    body        = request.get_json(force=True, silent=True) or {}
    docs_urls   = body.get("docs_urls", [])
    # schema_type: "none" | "product" | "blog"
    # "none"    → breadcrumb + FAQ only
    # "product" → breadcrumb + FAQ + product schema
    # "blog"    → breadcrumb + FAQ + blog schema
    schema_type = body.get("schema_type", "none")

    if not docs_urls:
        return jsonify({"error": "No docs_urls provided."}), 400

    if schema_type not in ("none", "product", "blog"):
        return jsonify({"error": "schema_type must be 'none', 'product', or 'blog'."}), 400

    token_dict = session.get("token")   # None if not logged in

    results = []
    for url in docs_urls:
        try:
            doc_data = fetch_doc_data(url, token_dict=token_dict)
            page_url = doc_data.get("page_url") or ""

            logo_url = banner_url = None
            if page_url:
                try:
                    logo_url, banner_url = fetch_site_assets(page_url)
                except Exception:
                    pass

            outputs = build_all_schemas(
                doc_data    = doc_data,
                schema_type = schema_type,
                logo_url    = logo_url,
                banner_url  = banner_url,
            )

            results.append({
                "page_url":   page_url,
                "logo_url":   logo_url,
                "banner_url": banner_url,
                "faq_count":  len(doc_data.get("faqs") or []),
                "h1":         doc_data.get("h1") or "",
                "auth_mode":  doc_data.get("_auth_mode", "unknown"),
                **outputs,
            })

        except Exception as exc:
            results.append({"page_url": url, "error": str(exc)})

    return jsonify({"results": results})


# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>SchemaForge - SEO Schema Generator</title>
<meta name="description" content="Generate Product, Blog, Breadcrumb and FAQ schemas from your Google Docs in seconds."/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#070711;--surface:#0f0f1e;--card:#15152a;--border:#252540;
  --accent:#7c5cfc;--accent2:#b06afc;--text:#eeeef8;--muted:#8888aa;
  --success:#22d3a0;--error:#f87171;--warn:#fbbf24;--r:14px;
}
html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
/* ── Header ── */
header{
  background:linear-gradient(135deg,#0e0b2e 0%,#0a0a1f 60%,#160b30 100%);
  border-bottom:1px solid var(--border);
  padding:0 40px;height:64px;
  display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100;
}
.logo{display:flex;align-items:center;gap:12px;text-decoration:none}
.logo-icon{
  width:38px;height:38px;border-radius:9px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;font-size:18px;
}
.logo-text{font-size:1.1rem;font-weight:800;
  background:linear-gradient(90deg,#c4b5fd,#e9d5ff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
header nav{margin-left:auto;display:flex;align-items:center;gap:12px}
/* ── Auth pill ── */
#auth-pill{
  display:flex;align-items:center;gap:8px;padding:7px 16px;
  border-radius:20px;font-size:0.78rem;font-weight:600;
  border:1px solid var(--border);transition:all .2s;cursor:pointer;
  text-decoration:none;
}
#auth-pill.connected{background:rgba(34,211,160,.1);border-color:rgba(34,211,160,.3);color:var(--success)}
#auth-pill.disconnected{background:rgba(124,92,252,.1);border-color:rgba(124,92,252,.3);color:#c4b5fd}
#auth-pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
/* ── Hero strip ── */
.hero{
  text-align:center;padding:48px 20px 36px;
  background:radial-gradient(ellipse 80% 60% at 50% 0%,rgba(124,92,252,.12) 0%,transparent 70%);
}
.hero h1{font-size:clamp(1.8rem,4vw,2.6rem);font-weight:900;line-height:1.15;margin-bottom:12px;
  background:linear-gradient(135deg,#fff 30%,#c4b5fd);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--muted);font-size:1rem;max-width:520px;margin:0 auto}
/* ── Container ── */
.container{max-width:900px;margin:0 auto;padding:0 20px 60px}
/* ── Card ── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:28px 32px;margin-bottom:20px;
  position:relative;overflow:hidden;
}
.card::before{
  content:'';position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(135deg,rgba(124,92,252,.05) 0%,transparent 55%);
}
.card-title{font-size:.95rem;font-weight:700;margin-bottom:20px;display:flex;align-items:center;gap:10px}
.badge{font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:20px;
  background:rgba(124,92,252,.18);color:#c4b5fd;text-transform:uppercase;letter-spacing:.06em}
.badge-always{font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:20px;
  background:rgba(34,211,160,.15);color:var(--success);text-transform:uppercase;letter-spacing:.06em}
.badge-optional{font-size:.65rem;font-weight:700;padding:3px 8px;border-radius:20px;
  background:rgba(251,191,36,.12);color:var(--warn);text-transform:uppercase;letter-spacing:.06em}
/* ── Toggle ── */
.toggle-group{display:flex;gap:10px;margin-bottom:24px}
.toggle-opt{display:none}
.toggle-opt+.toggle-lbl{
  flex:1;display:flex;flex-direction:column;align-items:center;gap:7px;
  padding:16px 10px;background:var(--surface);border:2px solid var(--border);
  border-radius:11px;cursor:pointer;font-size:.85rem;font-weight:500;color:var(--muted);
  transition:all .2s;
}
.toggle-opt+.toggle-lbl .icon{font-size:1.5rem}
.toggle-opt:checked+.toggle-lbl{border-color:var(--accent);background:rgba(124,92,252,.1);color:var(--text)}
/* ── Form ── */
label.lbl{display:block;font-size:.8rem;font-weight:500;color:var(--muted);margin-bottom:8px;letter-spacing:.03em}
.doc-row{display:grid;grid-template-columns:1fr 34px;gap:8px;margin-bottom:10px;align-items:center}
input[type=url]{
  width:100%;padding:12px 14px;background:var(--surface);border:1px solid var(--border);
  border-radius:9px;color:var(--text);font-family:'Inter',sans-serif;font-size:.9rem;
  outline:none;transition:border-color .2s,box-shadow .2s;
}
input[type=url]:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,92,252,.14)}
input::placeholder{color:#383860}
.btn-rm{
  width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;
  background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.2);
  color:var(--error);font-size:1rem;cursor:pointer;transition:background .2s;
}
.btn-rm:hover{background:rgba(248,113,113,.2)}
.btn-add{
  width:fit-content;margin-top:2px;display:flex;align-items:center;gap:8px;
  padding:8px 16px;background:rgba(124,92,252,.08);border:1px dashed rgba(124,92,252,.35);
  border-radius:8px;color:#a78bfa;font-size:.82rem;font-weight:500;cursor:pointer;transition:background .2s;
}
.btn-add:hover{background:rgba(124,92,252,.16)}
/* ── Generate button ── */
.btn-gen{
  width:100%;padding:14px;margin-top:24px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  border:none;border-radius:11px;color:#fff;font-family:'Inter',sans-serif;
  font-size:.95rem;font-weight:700;cursor:pointer;letter-spacing:.02em;
  transition:opacity .2s,transform .15s;display:flex;align-items:center;justify-content:center;gap:10px;
}
.btn-gen:hover{opacity:.9;transform:translateY(-1px)}
.btn-gen.loading{opacity:.6;pointer-events:none}
.spinner{display:none;width:16px;height:16px;border:2px solid rgba(255,255,255,.3);
  border-top-color:#fff;border-radius:50%;animation:spin .65s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── Schema-type info note ── */
.schema-note{
  font-size:.78rem;color:var(--muted);padding:10px 14px;
  background:rgba(124,92,252,.05);border:1px solid rgba(124,92,252,.15);
  border-radius:9px;margin-bottom:20px;line-height:1.5;
}
.schema-note b{color:#c4b5fd}

/* ── Result blocks ── */
#results{display:none}
.res-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:24px 28px;margin-bottom:20px}
.res-card.err{border-color:rgba(248,113,113,.3)}
.info-strip{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.chip{
  display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;
  background:rgba(124,92,252,.07);border:1px solid var(--border);font-size:.75rem;color:var(--muted);
}
.chip b{color:var(--text)}
.status-ok{background:rgba(34,211,160,.1);border-color:rgba(34,211,160,.25);color:var(--success);padding:5px 12px;border-radius:20px;font-size:.75rem;font-weight:600;display:inline-flex;align-items:center;gap:6px}
.status-err{background:rgba(248,113,113,.1);color:var(--error);padding:5px 12px;border-radius:20px;font-size:.75rem;font-weight:600}
.block-wrap{margin-bottom:16px}
.block-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.block-title{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--accent2);display:flex;align-items:center;gap:7px}
.block-title .dot{width:5px;height:5px;border-radius:50%;background:var(--success);display:inline-block}
.btn-copy{
  padding:4px 12px;border-radius:6px;background:rgba(124,92,252,.1);
  border:1px solid rgba(124,92,252,.25);color:#a78bfa;font-size:.72rem;font-weight:600;cursor:pointer;transition:all .2s;
}
.btn-copy:hover{background:rgba(124,92,252,.2)}
.btn-copy.copied{background:rgba(34,211,160,.1);border-color:rgba(34,211,160,.25);color:var(--success)}
.code-box{
  background:#0a0a17;border:1px solid var(--border);border-radius:9px;
  padding:14px 16px;font-family:'Fira Code','Consolas',monospace;font-size:.76rem;
  line-height:1.65;color:#cccce8;white-space:pre-wrap;word-break:break-word;
  max-height:280px;overflow-y:auto;
}
.code-box::-webkit-scrollbar{width:5px}
.code-box::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.meta-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.page-sep{display:flex;align-items:center;gap:12px;margin:24px 0 16px}
.page-sep span{font-size:.8rem;font-weight:600;color:var(--accent);white-space:nowrap}
.page-sep hr{flex:1;border:none;border-top:1px solid var(--border)}
/* ── Auth notice ── */
#auth-notice{
  display:none;padding:14px 18px;border-radius:10px;margin-bottom:18px;
  background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.25);
  font-size:.85rem;color:var(--warn);
}
#auth-notice a{color:#fbbf24;text-decoration:underline}
@media(max-width:600px){
  header{padding:0 16px}
  .card{padding:20px 16px}
  .meta-pair{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header>
  <a href="/" class="logo">
    <div class="logo-icon">&#128269;</div>
    <span class="logo-text">SchemaForge</span>
  </a>
  <nav>
    <a id="auth-pill" class="disconnected" href="#">&hellip;</a>
  </nav>
</header>

<div class="hero">
  <h1>SEO Schemas from<br/>Google Docs, Instantly</h1>
  <p>Paste your doc links &mdash; Breadcrumb &amp; FAQ schemas are always generated. Add Product or Blog schema optionally.</p>
</div>

<div class="container">

  <div id="auth-notice">
    &#9888;&#65039; You&rsquo;re not connected to Google.
    Private docs will fail. <a href="/auth/login">Connect Google Account &rarr;</a>
    (Public docs still work without login.)
  </div>

  <!-- Input card -->
  <div class="card">
    <div class="card-title">Configure Generation <span class="badge">Step 1</span></div>

    <!-- Always-on note -->
    <div class="schema-note">
      <b>&#10003; Always generated:</b> Breadcrumb Schema &amp; FAQ Schema (auto-extracted from your doc)<br/>
      <b>&#9881; Optional:</b> Select Product or Blog schema below if you need it &mdash; or leave as &ldquo;None&rdquo; to get only Breadcrumb &amp; FAQ.
    </div>

    <label class="lbl">Optional Additional Schema <span class="badge-optional">Optional</span></label>
    <div class="toggle-group">
      <input type="radio" id="t-none"    name="stype" value="none"    class="toggle-opt" checked/>
      <label for="t-none"    class="toggle-lbl"><span class="icon">&#128274;</span>None (Breadcrumb + FAQ only)</label>

      <input type="radio" id="t-product" name="stype" value="product" class="toggle-opt"/>
      <label for="t-product" class="toggle-lbl"><span class="icon">&#128722;</span>+ Product Schema</label>

      <input type="radio" id="t-blog"    name="stype" value="blog"    class="toggle-opt"/>
      <label for="t-blog"    class="toggle-lbl"><span class="icon">&#128221;</span>+ Blog / Article Schema</label>
    </div>

    <label class="lbl" style="margin-bottom:12px">Google Docs Links <span style="font-weight:400">(one per row)</span></label>
    <div id="doc-rows">
      <div class="doc-row">
        <input type="url" class="doc-url" placeholder="https://docs.google.com/document/d/..." />
        <button class="btn-rm" onclick="rmRow(this)" title="Remove">&#215;</button>
      </div>
    </div>
    <button class="btn-add" onclick="addRow()">+ Add another page</button>

    <button class="btn-gen" id="gen-btn" onclick="generate()">
      <span id="btn-txt">&#10024; Generate Schemas</span>
      <span class="spinner" id="btn-spin"></span>
    </button>
  </div>

  <div id="err-box" style="display:none;padding:14px 18px;background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.25);border-radius:10px;color:var(--error);font-size:.87rem;margin-bottom:16px"></div>

  <div id="results"></div>
</div>

<script>
// ── Auth status ────────────────────────────────────────────────────────────
async function loadAuth() {
  try {
    const d = await (await fetch('/api/auth-status')).json();
    const pill   = document.getElementById('auth-pill');
    const notice = document.getElementById('auth-notice');
    if (d.connected) {
      pill.innerHTML  = '<span class="dot"></span> Google Connected';
      pill.className  = 'connected';
      pill.href       = '/auth/logout';
      pill.title      = 'Click to disconnect';
    } else {
      pill.innerHTML  = '&#128279; Connect Google';
      pill.className  = 'disconnected';
      pill.href       = '/auth/login';
      notice.style.display = 'block';
    }
  } catch(_) {}
}
loadAuth();

// ── Row helpers ────────────────────────────────────────────────────────────
function addRow() {
  const c = document.getElementById('doc-rows');
  const d = document.createElement('div');
  d.className = 'doc-row';
  d.innerHTML = '<input type="url" class="doc-url" placeholder="https://docs.google.com/document/d/..."/>'
              + '<button class="btn-rm" onclick="rmRow(this)">&#215;</button>';
  c.appendChild(d);
  d.querySelector('input').focus();
}
function rmRow(btn) {
  const rows = document.querySelectorAll('.doc-row');
  if (rows.length > 1) btn.closest('.doc-row').remove();
}

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function chip(label, val) { return `<div class="chip">${esc(label)}: <b>${esc(String(val))}</b></div>` }

function copyBtn(text) {
  const id = 'cb' + Math.random().toString(36).slice(2);
  setTimeout(() => {
    const btn = document.getElementById(id);
    if (btn) btn.onclick = () => {
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = '✓ Copied!'; btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied') }, 2000);
      });
    };
  }, 50);
  return `<button class="btn-copy" id="${id}">Copy</button>`;
}

function codeBlock(title, content) {
  if (!content || !content.trim()) return '';
  return `<div class="block-wrap">
    <div class="block-hdr">
      <div class="block-title"><span class="dot"></span>${esc(title)}</div>
      ${copyBtn(content)}
    </div>
    <div class="code-box">${esc(content)}</div>
  </div>`;
}

// ── Generate ───────────────────────────────────────────────────────────────
async function generate() {
  const urls = [...document.querySelectorAll('.doc-url')]
    .map(i => i.value.trim()).filter(Boolean);
  if (!urls.length) { alert('Enter at least one Google Docs URL.'); return; }

  const stype  = document.querySelector('input[name="stype"]:checked').value;
  const btn    = document.getElementById('gen-btn');
  const txt    = document.getElementById('btn-txt');
  const spin   = document.getElementById('btn-spin');
  const errBox = document.getElementById('err-box');
  const resDiv = document.getElementById('results');

  btn.classList.add('loading');
  txt.textContent = 'Generating\u2026';
  spin.style.display = 'inline-block';
  errBox.style.display = 'none';
  resDiv.style.display = 'none';
  resDiv.innerHTML = '';

  try {
    const r = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ docs_urls: urls, schema_type: stype }),
    });
    const data = await r.json();
    if (!r.ok) { errBox.textContent = data.error || 'Server error.'; errBox.style.display='block'; return; }

    resDiv.style.display = 'block';
    data.results.forEach((pg, idx) => {
      let html = '';

      if (data.results.length > 1) {
        html += `<div class="page-sep"><hr/><span>Page ${idx+1} &mdash; ${esc(pg.page_url||'Unknown')}</span><hr/></div>`;
      }

      if (pg.error) {
        html += `<div class="res-card err"><span class="status-err">&#10007; ${esc(pg.error)}</span></div>`;
      } else {
        html += '<div class="res-card"><div class="info-strip">';
        if (pg.page_url)  html += chip('&#128279; URL',   pg.page_url);
        if (pg.h1)        html += chip('&#128196; H1',    pg.h1);
        if (pg.faq_count) html += chip('&#10068; FAQs',   pg.faq_count + ' found');
        if (pg.logo_url)  html += chip('&#127959; Logo',  'Auto-detected');
        if (pg.auth_mode) html += chip('&#128274; Auth',  pg.auth_mode === 'oauth2' ? 'OAuth2' : 'Export URL');
        html += `<span class="status-ok" style="margin-left:auto">&#10003; Generated</span>`;
        html += '</div>';

        html += '<div class="meta-pair">';
        html += codeBlock('Meta Title',       pg.meta_title);
        html += codeBlock('Meta Description', pg.meta_description);
        html += '</div>';

        // Always shown
        html += codeBlock('Breadcrumb Schema <span class="badge-always">Always</span>', pg.breadcrumb_schema);
        if (pg.faq_schema)
          html += codeBlock('FAQ Schema <span class="badge-always">Always</span>', pg.faq_schema);
        else
          html += `<div class="block-wrap" style="padding:12px 14px;background:rgba(251,191,36,.05);border:1px dashed rgba(251,191,36,.2);border-radius:9px;font-size:.78rem;color:var(--warn)">
            &#9888; No FAQ section detected in this doc. Make sure your doc has a heading containing &ldquo;FAQ&rdquo; or &ldquo;Frequently Asked Questions&rdquo; followed by Q:/A: lines.
          </div>`;

        // Optional schemas
        if (pg.product_schema)
          html += codeBlock('Product Schema <span class="badge-optional">Optional</span>', pg.product_schema);
        if (pg.blog_schema)
          html += codeBlock('Blog / Article Schema <span class="badge-optional">Optional</span>', pg.blog_schema);

        html += '</div>';
      }
      resDiv.innerHTML += html;
    });

  } catch(err) {
    errBox.textContent = 'Network error: ' + err.message;
    errBox.style.display = 'block';
  } finally {
    btn.classList.remove('loading');
    txt.textContent = '\u2728 Generate Schemas';
    spin.style.display = 'none';
  }
}
</script>
</body>
</html>"""


@app.route("/")
def landing():
    """Marketing / landing page."""
    landing_path = os.path.join(os.path.dirname(__file__), "landing.html")
    with open(landing_path, "r", encoding="utf-8") as f:
        return f.read()


@app.route("/app")
def home():
    """The actual schema generator tool."""
    return render_template_string(HTML)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)