import {
  api,
  el,
  esc,
  setCsrf,
  toast,
  message,
  formData,
  submit,
  openModal,
  closeModal,
  bindClose,
} from './shared.js';
import { renderAuth } from './auth.js';
let boot,
  user,
  peers = [],
  activity = { connections: [], sessions: [], notifications: [] },
  page = 'dashboard';
const title = (heading, description) =>
  `<div class="page-heading"><div><div class="eyebrow">Your learning space</div><h1>${esc(heading)}</h1><p class="muted">${esc(description)}</p></div></div>`;
const empty = (text) => `<div class="empty">${esc(text)}</div>`;
const input = (label, name, value = '', type = 'text', extra = '') =>
  `<div class="field"><label for="${name}">${label}</label><input id="${name}" name="${name}" value="${esc(value)}" type="${type}" ${extra}></div>`;
const options = (items, selected) =>
  items
    .map(
      (i) =>
        `<option value="${i.id}" ${i.id === selected ? 'selected' : ''}>${esc(i.name)}</option>`,
    )
    .join('');
const avatar = (u) =>
  `<div class="avatar large v${u.id % 4}">${esc(
    u.name
      .split(' ')
      .map((x) => x[0])
      .slice(0, 2)
      .join(''),
  )}</div>`;
const error = '<div class="error-text" role="alert"></div>';
const completion = () =>
  Math.round(
    (['modules', 'skills', 'needs', 'interests', 'preferences', 'availability'].filter((k) => {
      const v = user.profile[k];
      return Array.isArray(v) && v.length > 0;
    }).length /
      6) *
      100,
  );
const partner = (s) => (s.creator === user.id ? s.peer_name : s.creator_name);
async function refresh() {
  boot = await api('bootstrap');
  setCsrf(boot.csrf);
  if (!boot.user) {
    renderAuth(
      boot,
      boot.resetRequired
        ? 'reset'
        : boot.pendingEmail
          ? 'verify'
          : new URLSearchParams(location.search).has('login')
            ? 'login'
            : 'landing',
      refresh,
    );
    return;
  }
  if (boot.user.role === 'admin') {
    location.replace('/admin/overview');
    return;
  }
  user = boot.user;
  const [p, a] = await Promise.all([api('peers'), api('activity')]);
  peers = p.peers;
  activity = a;
  render();
}
function render() {
  const navigation = [
    ['dashboard', '◫', 'Overview'],
    ['peers', '♧', 'Find peers'],
    ['connections', '⇄', 'Connections'],
    ['sessions', '▦', 'Study sessions'],
    ['profile', '◎', 'My profile'],
    ['notifications', '♧', 'Notifications'],
    ['institutions', '⌂', 'Universities'],
  ];
  el('#app').innerHTML =
    `<aside class="sidebar"><div class="brand"><span class="brand-mark">↗</span>AdaptoLearn</div><small>YOUR WORKSPACE</small><nav class="nav" aria-label="Student navigation">${navigation.map(([p, i, n]) => `<button class="${p === page ? 'active' : ''}" data-nav="${p}" ${p === page ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${i}</span>${n}</button>`).join('')}</nav><div class="side-note"><strong>Better, together.</strong>A verified community to ask questions and share ideas.</div><div class="side-user">${avatar(user)}<span><b>${esc(user.name)}</b><span class="muted">${esc(user.acronym)} · Year ${user.year}</span></span></div></aside><div class="workspace"><header class="topbar"><button class="icon-btn mobile-menu" data-menu="true" aria-label="Open navigation">☰</button><span class="breadcrumb">Workspace / ${esc(navigation.find((x) => x[0] === page)?.[2])}</span><div class="top-actions"><button class="text-btn" data-nav="notifications">Notifications ${activity.notifications.filter((n) => !n.seen).length || ''}</button><button class="text-btn" data-logout="true">Sign out</button></div></header><main class="main" id="main"><div id="page-content"></div><footer class="footer">AdaptoLearn · Built for shared progress.<span>26 universities. Endless possibilities.</span></footer></main></div>`;
  const views = {
    dashboard,
    peers: peerPage,
    connections,
    sessions,
    profile,
    notifications,
    institutions,
  };
  el('#page-content').innerHTML = (views[page] ?? dashboard)();
  bindPage();
  const progress = document.querySelector('#completion-fill');
  if (progress) progress.style.width = completion() + '%';
}
function card(p) {
  const c = activity.connections.find((c) => c.sender === p.id || c.receiver === p.id);
  return `<article class="peer-card"><div class="peer-top">${avatar(p)}<span class="score">${p.score}% match</span></div><h3>${esc(p.name)}</h3><p class="muted">${esc(p.acronym)} · Year ${p.year}<br>${esc(p.programme)}</p><div class="chips">${(
    p.profile.skills ?? []
  )
    .slice(0, 3)
    .map((s) => `<span class="chip">${esc(s)}</span>`)
    .join('')}</div><div class="reasons">${p.reasons
    .slice(0, 2)
    .map((r) => `<div class="reason">${esc(r)}</div>`)
    .join(
      '',
    )}</div><div class="card-actions"><button class="btn secondary" data-peer="${p.id}">View profile</button>${c && c.status !== 'declined' ? `<button class="btn soft" data-nav="connections">${c.status === 'accepted' ? 'Connected ✓' : 'Request pending'}</button>` : `<button class="btn" data-connect="${p.id}">Connect ↗</button>`}</div></article>`;
}
function dashboard() {
  return (
    title(
      'Welcome back, ' + user.name.split(' ')[0],
      'A good study partner can change the way you learn.',
    ) +
    `<section class="hero"><div class="hero-text"><div class="eyebrow">Learn together. Go further.</div><h2>Your next breakthrough<br>starts with a connection.</h2><p>Find peers who get your goals. Share what you know, learn what you need, and grow together.</p><button class="btn" data-nav="peers">Explore your matches ↗</button></div><div class="orbit" aria-hidden="true"><div class="orb one">✎</div><div class="orb two">⌘</div><div class="center">✧</div><div class="orb three">↗</div></div></section><div class="stats">${[
      [peers.length, 'Recommended peers'],
      [activity.connections.filter((c) => c.status === 'accepted').length, 'Your connections'],
      [
        activity.sessions.filter((s) => ['pending', 'accepted'].includes(s.status)).length,
        'Upcoming sessions',
      ],
      [activity.sessions.filter((s) => s.status === 'completed').length, 'Sessions completed'],
    ]
      .map(
        ([n, label]) =>
          `<div class="stat"><div class="stat-icon">↗</div><div><b>${n}</b><span>${label}</span></div></div>`,
      )
      .join(
        '',
      )}</div><div class="dashboard-grid"><section><div class="section-heading"><div><h2>People to learn with</h2><p class="muted">Thoughtful matches, built around you.</p></div><button class="text-btn" data-nav="peers">View all →</button></div><div class="peer-grid">${peers.slice(0, 4).map(card).join('') || empty('Your recommendations will appear as verified students join.')}</div></section><aside><section class="panel"><h3>Upcoming sessions</h3>${
      activity.sessions
        .filter((s) => ['pending', 'accepted'].includes(s.status))
        .slice(0, 3)
        .map(
          (s) =>
            `<div class="session-mini"><div><h4>${esc(s.topic)}</h4><p>with ${esc(partner(s))}</p><p>${esc(s.starts.replace('T', ' '))} SAST</p></div></div>`,
        )
        .join('') || '<p class="muted">Make a connection and plan your first session.</p>'
    }<button class="btn secondary small" data-arrange="true">+ Plan a session</button></section><section class="panel"><h3>Your profile, your possibilities</h3><p class="muted">A little more about you makes a better match.</p><div class="completion-ring"><span id="completion-fill"></span></div><p class="muted">${completion()}% complete</p><button class="text-btn" data-nav="profile">Update your profile →</button></section></aside></div>`
  );
}
function peerPage() {
  return (
    title(
      'Find your learning people',
      'Ranked by learning compatibility, with reasons for every match.',
    ) +
    `<div class="filterbar"><input id="peer-search" aria-label="Search peers" placeholder="Search a name, skill or module…"><select id="peer-institution" aria-label="Filter by university"><option value="">All universities</option>${options(boot.institutions)}</select><select id="peer-score" aria-label="Minimum match score"><option value="0">All scores</option><option value="50">50% and above</option><option value="75">75% and above</option></select></div><div class="peer-grid" id="peer-results">${peers.map(card).join('') || empty('No verified peers are available yet.')}</div><p class="muted">Priority-weighted needs 40%, reciprocal help 10%, modules 20%, availability 15%, preferences 10%, interests 5%. Session feedback adjusts scores by up to 10 points.</p>`
  );
}
function connections() {
  return (
    title('Your learning circle', 'Meet, connect, and make progress together.') +
    activity.connections
      .map(
        (c) =>
          `<article class="activity-card"><div><h3>${esc(c.sender === user.id ? c.receiver_name : c.sender_name)}</h3><span class="status ${c.status}">${c.status}</span></div><div class="activity-actions">${c.status === 'pending' && c.receiver === user.id ? `<button class="btn small" data-connection="${c.id}" data-status="accepted">Accept</button><button class="btn secondary small" data-connection="${c.id}" data-status="declined">Decline</button>` : ''}${c.status === 'accepted' ? `<button class="btn small" data-arrange="${c.sender === user.id ? c.receiver : c.sender}">Plan a session</button>` : ''}</div></article>`,
      )
      .join('') +
    (activity.connections.length
      ? ''
      : empty('Explore your matches and send your first connection request.'))
  );
}
function sessionCard(s) {
  const ended = new Date(s.starts + '+02:00').getTime() + s.duration * 60000 <= Date.now();
  return `<article class="activity-card"><div><h3>${esc(s.topic)} <span class="status ${s.status}">${s.status}</span></h3><p>${esc(s.module)} · with ${esc(partner(s))}</p><p>${esc(s.starts.replace('T', ' '))} SAST · ${s.duration} minutes</p><p>${esc(s.location)}</p></div><div class="activity-actions">${s.status === 'pending' && s.peer === user.id ? `<button class="btn small" data-session="${s.id}" data-status="accepted">Accept invitation</button>` : ''}${s.status === 'accepted' && ended ? `<button class="btn small" data-session="${s.id}" data-status="completed">Mark completed</button>` : ''}${['pending', 'accepted'].includes(s.status) ? `<button class="btn secondary small" data-session="${s.id}" data-status="cancelled">Cancel</button>` : ''}${s.status === 'completed' && !s.feedback_id ? `<button class="btn small" data-feedback="${s.id}">Leave feedback</button>` : s.feedback_id ? '<span class="chip">Feedback submitted ✓</span>' : ''}</div></article>`;
}
function sessions() {
  return (
    title(
      'Make time for progress',
      'Your study plans, invitations, and learning history. All times are SAST (UTC+2).',
    ) +
    `<button class="btn" data-arrange="true">+ Plan a session</button><br><br><h2>Upcoming & invitations</h2>${
      activity.sessions
        .filter((s) => ['pending', 'accepted'].includes(s.status))
        .map(sessionCard)
        .join('') || empty('Plan a session with a connected peer.')
    }<h2>Learning history</h2>${
      activity.sessions
        .filter((s) => ['completed', 'cancelled'].includes(s.status))
        .reverse()
        .map(sessionCard)
        .join('') || empty('Completed and cancelled sessions will appear here.')
    }`
  );
}
function checks(name, values, selected = []) {
  return `<div class="check-group">${values.map((v) => `<label class="check"><input type="checkbox" name="${name}" value="${esc(v)}" ${selected.includes(v) ? 'checked' : ''}>${esc(v)}</label>`).join('')}</div>`;
}
function needRow(n = { topic: '', priority: 3 }) {
  return `<div class="dynamic-row need-row"><input aria-label="Learning need" value="${esc(n.topic)}" maxlength="80" placeholder="e.g. Python"><select aria-label="Learning priority">${[3, 2, 1].map((v) => `<option value="${v}" ${v === n.priority ? 'selected' : ''}>${{ 3: 'High priority', 2: 'Medium priority', 1: 'Low priority' }[v]}</option>`).join('')}</select><button type="button" class="icon-btn" data-remove="true" aria-label="Remove learning need">×</button></div>`;
}
function slotRow(s = { day: 'Monday', start: '16:00', end: '18:00' }) {
  return `<div class="dynamic-row availability-row"><select aria-label="Available day">${boot.days.map((d) => `<option ${d === s.day ? 'selected' : ''}>${d}</option>`).join('')}</select><input type="time" aria-label="Start time" value="${s.start}" required><input type="time" aria-label="End time" value="${s.end}" required><button type="button" class="icon-btn" data-remove="true" aria-label="Remove availability">×</button></div>`;
}
function profile() {
  const p = user.profile;
  return (
    title(
      'A profile that feels like you',
      'Share your strengths. Tell us where you want to grow.',
    ) +
    `<form id="profile-form" class="panel"><div class="form-grid">${input('Full name', 'name', user.name, 'text', 'required maxlength="80"')}<div class="field"><label for="institution_id">University</label><select name="institution_id" id="institution_id">${options(boot.institutions, user.institution_id)}</select></div>${input('Programme', 'programme', user.programme, 'text', 'required maxlength="100"')}<div class="field"><label for="year">Year of study</label><select name="year" id="year">${[1, 2, 3, 4, 5, 6, 7].map((y) => `<option ${user.year === y ? 'selected' : ''}>${y}</option>`).join('')}</select></div><div class="field span-all"><label for="bio">About you</label><textarea id="bio" name="bio" maxlength="500">${esc(p.bio)}</textarea></div></div><section class="form-section"><h3>Your academic world</h3>${checks(
      'modules',
      boot.modules.map((m) => m.name),
      p.modules,
    )}<br>${input('Skills & strengths (comma-separated)', 'skills', (p.skills ?? []).join(', '))}<h3>What would you like help with?</h3><p class="muted">Higher-priority needs carry more weight.</p><div id="needs-list">${(p.needs ?? []).map(needRow).join('')}</div><button class="btn secondary small" type="button" data-add-need="true">+ Add a learning need</button></section><section class="form-section"><h3>How you like to learn</h3>${checks('preferences', boot.methods, p.preferences)}<br>${input('Interests (comma-separated)', 'interests', (p.interests ?? []).join(', '))}</section><section class="form-section"><h3>Your availability · SAST</h3><div id="slots-list">${(p.availability ?? []).map(slotRow).join('')}</div><button class="btn secondary small" type="button" data-add-slot="true">+ Add a time slot</button></section>${error}<button class="btn" type="submit">Save your profile ✓</button></form>`
  );
}
function notifications() {
  return (
    title('Stay in the loop', 'Requests, announcements, sessions, and reminders.') +
    `<button class="btn secondary" data-read="true">Mark all read</button><br><br><section class="panel">${activity.notifications.map((n) => `<div class="notification ${n.seen ? '' : 'unread'}"><div>${esc(n.message)}<small>${esc(new Date(n.created).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg' }))} SAST</small></div></div>`).join('') || empty('All quiet for now.')}</section>`
  );
}
function institutionCards(query = '') {
  return boot.institutions
    .filter((i) => (i.name + ' ' + i.shortName).toLowerCase().includes(query.toLowerCase()))
    .map(
      (i) =>
        `<article class="institution-card"><div class="avatar">${esc(i.shortName)}</div><div><b>${esc(i.name)}</b><p class="muted">${i.isActive ? 'Registrations open' : 'Registrations paused'}</p></div></article>`,
    )
    .join('');
}
function institutions() {
  return (
    title('One community. 26 universities.', 'South Africa’s public university network.') +
    `<div class="filterbar"><input id="institution-search" aria-label="Search universities" placeholder="Search universities…"></div><div class="institution-grid" id="institution-results">${institutionCards()}</div>`
  );
}
function bindPage() {
  for (const id of ['peer-search', 'peer-institution', 'peer-score']) {
    const node = document.querySelector('#' + id);
    if (node)
      node.oninput = () => {
        const q = el('#peer-search').value.toLowerCase(),
          iid = el('#peer-institution').value,
          min = Number(el('#peer-score').value);
        el('#peer-results').innerHTML =
          peers
            .filter(
              (p) =>
                p.score >= min &&
                (!iid || p.institution_id === Number(iid)) &&
                (
                  p.name +
                  ' ' +
                  (p.profile.skills ?? []).join(' ') +
                  ' ' +
                  (p.profile.modules ?? []).join(' ')
                )
                  .toLowerCase()
                  .includes(q),
            )
            .map(card)
            .join('') || empty('No matches for these filters.');
      };
  }
  const search = document.querySelector('#institution-search');
  if (search)
    search.oninput = () => (el('#institution-results').innerHTML = institutionCards(search.value));
  const form = document.querySelector('#profile-form');
  if (form)
    form.onsubmit = (e) => {
      e.preventDefault();
      void submit(form, async () => {
        const d = formData(form);
        const data = {
          ...d,
          institution_id: Number(d.institution_id),
          year: Number(d.year),
          skills: d.skills
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
          interests: d.interests
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
          modules: [...form.querySelectorAll('input[name="modules"]:checked')].map((n) => n.value),
          preferences: [...form.querySelectorAll('input[name="preferences"]:checked')].map(
            (n) => n.value,
          ),
          needs: [...form.querySelectorAll('.need-row')]
            .filter((r) => r.querySelector('input').value.trim())
            .map((r) => ({
              topic: r.querySelector('input').value,
              priority: Number(r.querySelector('select').value),
            })),
          availability: [...form.querySelectorAll('.availability-row')].map((r) => {
            const times = r.querySelectorAll('input');
            return {
              day: r.querySelector('select').value,
              start: times[0].value,
              end: times[1].value,
            };
          }),
        };
        await api('profile', 'PUT', data);
        await refresh();
        toast('Profile saved. Your matches are up to date.');
      });
    };
}
function showPeer(id) {
  const p = peers.find((p) => p.id === id);
  if (!p) throw new Error('This peer is unavailable.');
  openModal(
    `${avatar(p)}<h1>${esc(p.name)}</h1><p class="muted">${esc(p.institution)} · ${esc(p.programme)}</p><p>${esc(p.profile.bio)}</p><h3>Why you match · ${p.score}%</h3>${p.reasons.map((r) => `<p class="reason">${esc(r)}</p>`).join('')}<h3>Can help with</h3><p>${esc((p.profile.skills ?? []).join(', '))}</p><h3>Learning needs</h3><p>${esc((p.profile.needs ?? []).map((n) => n.topic).join(', '))}</p><h3>Availability · SAST</h3>${(p.profile.availability ?? []).map((a) => `<p class="muted">${a.day} ${a.start}–${a.end}</p>`).join('')}`,
  );
}
function arrange(id) {
  const connected = activity.connections
    .filter((c) => c.status === 'accepted')
    .map((c) => ({
      id: c.sender === user.id ? c.receiver : c.sender,
      name: c.sender === user.id ? c.receiver_name : c.sender_name,
    }));
  if (!connected.length) {
    toast('Connect with a peer first to arrange a study session.');
    page = 'connections';
    render();
    return;
  }
  openModal(
    `<h2>Make a little time to learn.</h2><form id="session-form"><div class="field"><label for="peer_id">Study partner</label><select id="peer_id" name="peer_id">${options(connected, id)}</select></div><div class="field"><label for="module">Module</label><select id="module" name="module">${boot.modules.map((m) => `<option>${esc(m.name)}</option>`).join('')}</select></div>${input('Topic', 'topic', '', 'text', 'required maxlength="150"')}${input('Date & time (SAST)', 'starts', '', 'datetime-local', 'required')}${input('Duration (minutes)', 'duration', 60, 'number', 'required min="15" max="240"')}${input('Location or meeting link', 'location', '', 'text', 'required maxlength="200"')}${error}<button class="btn" type="submit">Send study invitation ↗</button></form>`,
  );
  const form = el('#session-form');
  form.onsubmit = (e) => {
    e.preventDefault();
    void submit(form, async () => {
      const d = formData(form);
      await api('sessions', 'POST', {
        ...d,
        peer_id: Number(d.peer_id),
        duration: Number(d.duration),
      });
      closeModal();
      page = 'sessions';
      await refresh();
      toast('Study invitation sent.');
    });
  };
}
function feedback(id) {
  openModal(
    `<h2>How did your session go?</h2><form id="feedback-form"><div class="field"><label for="rating">Rating</label><select id="rating" name="rating">${[5, 4, 3, 2, 1].map((n) => `<option>${n}</option>`).join('')}</select></div>${['useful', 'again'].map((k) => `<div class="field"><label for="${k}">${k === 'useful' ? 'Was it useful?' : 'Would you study together again?'}</label><select id="${k}" name="${k}"><option value="true">Yes</option><option value="false">No</option></select></div>`).join('')}<div class="field"><label for="comments">Comments (optional)</label><textarea id="comments" name="comments" maxlength="1000"></textarea></div>${error}<button class="btn" type="submit">Share feedback</button></form>`,
  );
  const form = el('#feedback-form');
  form.onsubmit = (e) => {
    e.preventDefault();
    void submit(form, async () => {
      const d = formData(form);
      await api(`sessions/${id}/feedback`, 'POST', {
        rating: Number(d.rating),
        useful: d.useful === 'true',
        again: d.again === 'true',
        comments: d.comments,
      });
      closeModal();
      await refresh();
      toast('Feedback saved. Future matches reflect this session.');
    });
  };
}
bindClose();
document.addEventListener('click', (event) => {
  const t = event.target.closest('button');
  if (!t) return;
  void (async () => {
    try {
      if (t.dataset.nav) {
        page = t.dataset.nav;
        render();
        window.scrollTo(0, 0);
      } else if (t.dataset.logout) {
        await api('logout', 'POST', {});
        await refresh();
      } else if (t.dataset.menu) el('.sidebar').classList.toggle('open');
      else if (t.dataset.peer) showPeer(Number(t.dataset.peer));
      else if (t.dataset.connect) {
        t.disabled = true;
        await api('connections', 'POST', { peer_id: Number(t.dataset.connect) });
        await refresh();
        toast('Connection request sent.');
      } else if (t.dataset.connection) {
        await api('connections/' + t.dataset.connection, 'PATCH', { status: t.dataset.status });
        await refresh();
      } else if (t.dataset.arrange)
        arrange(t.dataset.arrange === 'true' ? undefined : Number(t.dataset.arrange));
      else if (t.dataset.session) {
        await api('sessions/' + t.dataset.session, 'PATCH', { status: t.dataset.status });
        await refresh();
      } else if (t.dataset.feedback) feedback(Number(t.dataset.feedback));
      else if (t.dataset.read) {
        await api('notifications/read', 'POST', {});
        await refresh();
      } else if (t.dataset.addNeed) el('#needs-list').insertAdjacentHTML('beforeend', needRow());
      else if (t.dataset.addSlot) el('#slots-list').insertAdjacentHTML('beforeend', slotRow());
      else if (t.dataset.remove) t.closest('.dynamic-row')?.remove();
    } catch (e) {
      t.disabled = false;
      toast(message(e), true);
    }
  })();
});
void refresh().catch((e) => {
  el('#app').innerHTML = empty(message(e));
});
