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
  bindClose,
  ApiError,
  validateSchema,
} from './shared.js';
let boot;
let page = location.pathname.split('/')[2] || 'overview';
const title = (name, description) =>
  `<div class="page-heading"><div><div class="eyebrow">Platform administration</div><h1>${esc(name)}</h1><p class="muted">${esc(description)}</p></div></div>`;
const error = '<div class="error-text" role="alert"></div>';
const field = (label, name, type = 'text', extra = '') =>
  `<div class="field"><label for="${name}">${label}</label><input name="${name}" id="${name}" type="${type}" ${extra}></div>`;
const institutionOptions = () =>
  '<option value="">All institutions</option>' +
  boot.institutions.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join('');
const date = (value) =>
  new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('en-ZA', {
    timeZone: 'Africa/Johannesburg',
  });
function validate(name, data) {
  const key = validateSchema(boot.schemas[name], data);
  if (key) throw new ApiError('Check this field and try again.', 400, key);
}
async function refresh() {
  boot = await api('bootstrap');
  setCsrf(boot.csrf);
  if (!boot.user || boot.user.role !== 'admin') {
    location.replace('/?login=1');
    return;
  }
  await render();
}
async function render() {
  const nav = [
    ['overview', '◫', 'Overview'],
    ['students', '◎', 'Students'],
    ['verifications', '✓', 'Verifications'],
    ['institutions', '⌂', 'Institutions'],
    ['announcements', '♧', 'Announcements'],
    ['audit', '▦', 'Audit log'],
  ];
  if (boot.user?.admin_level === 'super-admin') nav.splice(4, 0, ['admins', '⚙', 'Administrators']);
  el('#app').innerHTML =
    `<aside class="sidebar"><div class="brand"><span class="brand-mark">↗</span>AdaptoLearn</div><small>ADMINISTRATION</small><nav class="nav" aria-label="Administrator navigation">${nav.map(([p, i, n]) => `<button data-admin-nav="${p}" class="${p === page ? 'active' : ''}" ${p === page ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${i}</span>${n}</button>`).join('')}</nav><div class="side-note"><strong>Community operations</strong>Manage access, verification, institutions, and official announcements.</div><div class="side-user"><span><b>${esc(boot.user?.name)}</b>${esc(boot.user?.admin_level)}</span></div></aside><div class="workspace"><header class="topbar"><button class="icon-btn mobile-menu" id="admin-menu" aria-label="Open navigation">☰</button><span class="breadcrumb">Administration / ${esc(page)}</span><button class="text-btn" id="admin-logout">Sign out</button></header><main class="main" id="main"><div id="admin-content"><span class="loader"></span></div></main></div>`;
  try {
    const views = {
      overview,
      students: () => studentPage(false),
      verifications: () => studentPage(true),
      institutions,
      admins,
      announcements,
      audit,
    };
    el('#admin-content').innerHTML = await (views[page] ?? overview)();
    bindForms();
  } catch (e) {
    el('#admin-content').innerHTML = `<div class="empty">${esc(message(e))}</div>`;
  }
}
async function overview() {
  const data = await api('admin/overview');
  return (
    title(
      'Community at a glance',
      'Account activity and registration health across your institutions.',
    ) +
    `<div class="stats">${[
      [data.totalStudents, 'Total students'],
      [data.pendingVerifications, 'Pending verifications'],
      [data.verifiedStudents, 'Verified students'],
      [data.activeInstitutions, 'Active institutions'],
    ]
      .map(([v, n]) => `<div class="stat"><div><b>${v}</b><span>${n}</span></div></div>`)
      .join(
        '',
      )}</div><section class="panel"><h2>Recent sign-ups</h2>${studentTable(data.recentSignups)}</section>`
  );
}
function studentTable(users) {
  return users.length
    ? `<div class="table-wrap"><table><thead><tr><th>Student</th><th>Institution</th><th>Status</th><th>Account controls</th></tr></thead><tbody>${users.map((u) => `<tr><td><b>${esc(u.name)}</b><br>${esc(u.email)}</td><td>${esc(u.institution ?? '')}</td><td><span class="status">${esc(u.status)}</span></td><td><div class="activity-actions"><button class="btn secondary small" data-detail="${u.id}">Detail</button><button class="btn secondary small" data-student="${u.id}" data-action="${u.email_verified ? 'unverify' : 'verify'}">${u.email_verified ? 'Revoke verification' : 'Verify'}</button><button class="btn secondary small" data-student="${u.id}" data-action="${u.active ? 'suspend' : 'reactivate'}">${u.active ? 'Suspend' : 'Reactivate'}</button>${u.status === 'PENDING_VERIFICATION' ? `<button class="btn secondary small" data-student="${u.id}" data-action="resend">Resend code</button>` : ''}<button class="btn danger small" data-student="${u.id}" data-action="delete">Delete</button></div></td></tr>`).join('')}</tbody></table></div>`
    : '<div class="empty">No students match this view.</div>';
}
async function studentPage(pending) {
  const result = await api('admin/students' + (pending ? '?status=PENDING_VERIFICATION' : ''));
  return (
    title(
      pending ? 'Verification queue' : 'Student management',
      pending
        ? 'Review pending accounts, resend codes, and control verification.'
        : 'Search accounts and manage access. Academic content is read-only.',
    ) +
    `<form id="student-filter" class="filterbar"><input name="q" aria-label="Search students" placeholder="Name or email…"><select name="institution" aria-label="Filter institution">${institutionOptions()}</select><select name="status" aria-label="Filter status">${pending ? '<option value="PENDING_VERIFICATION">Pending verification</option>' : '<option value="">All statuses</option><option value="ACTIVE">Active</option><option value="PENDING_VERIFICATION">Pending verification</option><option value="SUSPENDED">Suspended</option>'}</select><button class="btn" type="submit">Search</button></form><div class="panel" id="student-results">${studentTable(result.users)}</div>`
  );
}
async function institutions() {
  const result = await api('admin/institutions');
  return (
    title('Institution registry', 'Control registration availability and student email domains.') +
    result.institutions
      .map(
        (i) =>
          `<form class="panel institution-form" data-id="${i.id}"><h3>${esc(i.name)} · ${esc(i.shortName)}</h3><div class="form-grid"><div class="field"><label for="domain-${i.id}">Student email domain</label><input id="domain-${i.id}" name="studentEmailDomain" value="${esc(i.studentEmailDomain)}" required maxlength="150"></div><div class="field"><label for="active-${i.id}">Registration availability</label><select id="active-${i.id}" name="isActive"><option value="true" ${i.isActive ? 'selected' : ''}>Enabled</option><option value="false" ${!i.isActive ? 'selected' : ''}>Disabled</option></select></div></div>${error}<button class="btn small" type="submit">Save institution</button></form>`,
      )
      .join('')
  );
}
async function admins() {
  const result = await api('admin/admins');
  return (
    title(
      'Administrator access',
      'Manage privileges for administrators provisioned through setup.',
    ) +
    `${result.users.map((u) => `<form class="panel admin-user-form" data-id="${u.id}"><h3>${esc(u.name)} · ${esc(u.email)}</h3><div class="dynamic-row"><select name="adminLevel" aria-label="Privilege for ${esc(u.name)}"><option value="admin" ${u.admin_level === 'admin' ? 'selected' : ''}>Admin</option><option value="super-admin" ${u.admin_level === 'super-admin' ? 'selected' : ''}>Super-admin</option></select><select name="active" aria-label="Account status for ${esc(u.name)}"><option value="true" ${u.active ? 'selected' : ''}>Active</option><option value="false" ${!u.active ? 'selected' : ''}>Inactive</option></select><button class="btn small" type="submit">Save access</button></div>${error}</form>`).join('')}`
  );
}
async function announcements() {
  const result = await api('admin/announcements');
  return (
    title('Official announcements', 'Send an in-app notice now or schedule it for later.') +
    `<form class="panel" id="announcement-form">${field('Title', 'title', 'text', 'required maxlength="150"')}<div class="field"><label for="body">Notice</label><textarea name="body" id="body" required maxlength="2000"></textarea></div><div class="form-grid"><div class="field"><label for="institution">Audience</label><select name="institution_id" id="institution">${institutionOptions()}</select></div>${field('Schedule (SAST, optional)', 'send_at', 'datetime-local')}</div><p class="muted">Only active, verified students receive announcements. Leave the date empty to send now.</p>${error}<button class="btn" type="submit">Create notice</button></form><section class="panel"><h2>Announcement history</h2>${result.announcements.map((a) => `<article class="activity-card"><div><h3>${esc(a.title)}</h3><p>${esc(a.body)}</p><p>${a.institution_id ? esc(boot.institutions.find((i) => i.id === a.institution_id)?.name) : 'All institutions'} · ${a.sent_at ? 'Sent ' + date(a.sent_at) : 'Scheduled ' + date(a.send_at)} SAST</p></div></article>`).join('') || '<p class="muted">No announcements yet.</p>'}</section>`
  );
}
async function audit() {
  const result = await api('admin/audit');
  return (
    title('Audit log', 'Recorded verification, access, deletion, institution, and role changes.') +
    `<div class="panel table-wrap"><table><thead><tr><th>When (SAST)</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>${result.entries.map((a) => `<tr><td>${esc(date(a.created))}</td><td>${esc(a.actor_name)}</td><td>${esc(a.action)}</td><td>${esc(a.target)}</td><td>${esc(a.details)}</td></tr>`).join('')}</tbody></table></div>`
  );
}
function bindForms() {
  const filter = document.querySelector('#student-filter');
  if (filter)
    filter.onsubmit = (e) => {
      e.preventDefault();
      const data = formData(filter);
      void api('admin/students?' + new URLSearchParams(data).toString())
        .then((r) => (el('#student-results').innerHTML = studentTable(r.users)))
        .catch((e) => toast(message(e), true));
    };
  document.querySelectorAll('.institution-form').forEach(
    (form) =>
      (form.onsubmit = (e) => {
        e.preventDefault();
        void submit(form, async () => {
          const d = formData(form);
          const data = {
            studentEmailDomain: d.studentEmailDomain.trim().toLowerCase(),
            isActive: d.isActive === 'true',
          };
          validate('institution', data);
          await api('admin/institutions/' + form.dataset.id, 'PUT', data);
          await refresh();
          toast('Institution saved.');
        });
      }),
  );
  document.querySelectorAll('.admin-user-form').forEach(
    (form) =>
      (form.onsubmit = (e) => {
        e.preventDefault();
        void submit(form, async () => {
          const d = formData(form);
          const data = { active: d.active === 'true', adminLevel: d.adminLevel };
          validate('adminAction', data);
          await api('admin/admins/' + form.dataset.id, 'PUT', data);
          await refresh();
          toast('Administrative access saved.');
        });
      }),
  );
  const announcement = document.querySelector('#announcement-form');
  if (announcement)
    announcement.onsubmit = (e) => {
      e.preventDefault();
      void submit(announcement, async () => {
        const d = formData(announcement);
        const data = {
          title: d.title,
          body: d.body,
          institution_id: d.institution_id ? Number(d.institution_id) : null,
          send_at: d.send_at ? d.send_at + ':00+02:00' : null,
        };
        validate('announcement', data);
        await api('admin/announcements', 'POST', data);
        await render();
        toast('Announcement created.');
      });
    };
}
bindClose();
document.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  void (async () => {
    try {
      if (button.dataset.adminNav) {
        page = button.dataset.adminNav;
        history.pushState({}, '', '/admin/' + page);
        await render();
      } else if (button.id === 'admin-menu') el('.sidebar').classList.toggle('open');
      else if (button.id === 'admin-logout') {
        await api('logout', 'POST', {});
        location.assign('/?login=1');
      } else if (button.dataset.detail) {
        const result = await api('admin/students/' + button.dataset.detail);
        const u = result.user;
        openModal(
          `<h2>${esc(u.name)}</h2><p>${esc(u.email)}</p><p>${esc(u.institution)}</p><p>Status: ${esc(u.status)} · ${u.email_verified ? 'Verified' : 'Unverified'}</p><p class="muted">${esc(u.programme)} · Year ${u.year}<br>Academic information is read-only.</p>`,
        );
      } else if (button.dataset.student) {
        const id = button.dataset.student;
        const action = button.dataset.action;
        if (action === 'delete') {
          openModal(
            `<h2>Delete this student account?</h2><p>This permanently removes the account and its related study records.</p><button class="btn danger" id="confirm-delete" data-id="${id}">Delete account</button>`,
          );
          return;
        }
        button.disabled = true;
        await api('admin/students/' + id, 'POST', { action });
        await render();
        toast('Student account updated.');
      } else if (button.id === 'confirm-delete') {
        await api('admin/students/' + button.dataset.id, 'POST', { action: 'delete' });
        el('#modal').close();
        await render();
        toast('Student account deleted.');
      }
    } catch (e) {
      button.disabled = false;
      toast(message(e), true);
    }
  })();
});
window.addEventListener('popstate', () => {
  page = location.pathname.split('/')[2] || 'overview';
  void render();
});
void refresh().catch((e) => (el('#app').innerHTML = `<div class="empty">${esc(message(e))}</div>`));
