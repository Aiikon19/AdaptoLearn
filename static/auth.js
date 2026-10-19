import { api, el, esc, formData, submit, ApiError, validateSchema, toast } from './shared.js';
import { buildStudentEmail, changeDomain, validLocalPart } from './domain.js';
const field = (label, name, type = 'text', extra = '') =>
  `<div class="field"><label for="${name}">${esc(label)}</label><input id="${name}" name="${name}" type="${type}" ${extra}></div>`;
const error = '<div class="error-text" role="alert"></div>';
let resendTimer;
export function renderAuth(boot, mode, refresh) {
  if (resendTimer) clearInterval(resendTimer);
  const app = el('#app');
  const navigation = `<header class="auth-nav"><a class="brand" href="/" aria-label="AdaptoLearn home"><img class="brand-logo" src="/static/img/logo-mark.png" alt="">AdaptoLearn</a>${mode === 'landing' ? '<nav class="auth-links" aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#benefits">Why AdaptoLearn</a><a href="#faqs">FAQs</a></nav>' : ''}<div class="auth-actions"><button class="text-btn" data-auth="login">Sign in</button><button class="btn" data-auth="register">Get started <span aria-hidden="true">↗</span></button></div></header>`;
  let content;
  if (mode === 'register') {
    content = `<h1>Find your learning people.</h1><p class="muted">Join using your official student email.</p><form id="register-form"><div class="field"><label for="institution_id">University</label><select id="institution_id" name="institution_id">${boot.institutions
      .filter((i) => i.isActive)
      .map(
        (i) =>
          `<option value="${i.id}" ${i.id === boot.defaultInstitutionId ? 'selected' : ''}>${esc(i.name)}</option>`,
      )
      .join(
        '',
      )}</select></div>${field('Full name', 'name', 'text', 'required maxlength="80" autocomplete="name"')}<div class="field"><label for="email">Student email</label><div class="email-composite"><input id="email" name="email" aria-describedby="email-hint email-error" required autocomplete="username" placeholder="221234567" pattern="[a-zA-Z0-9._%+\\-]+"><span id="email-suffix"></span></div><small id="email-hint"></small><span id="email-error" class="error-text" role="alert"></span></div>${field('Programme', 'programme', 'text', 'required maxlength="100"')}<div class="field"><label for="year">Year of study</label><select name="year" id="year">${[1, 2, 3, 4, 5, 6, 7].map((n) => `<option>${n}</option>`).join('')}</select></div>${field('Password', 'password', 'password', 'required minlength="10" maxlength="128" autocomplete="new-password"')}${error}<button class="btn" type="submit">Create account ↗</button></form>`;
  } else if (mode === 'verify') {
    content = `<h1>Check your student inbox.</h1><p class="muted">Enter the six-digit code sent to <strong>${esc(boot.pendingEmail)}</strong>. It expires in 15 minutes.</p><form id="verify-form"><fieldset class="code-fieldset"><legend>Verification code</legend><div class="code-inputs">${Array.from({ length: 6 }, (_, i) => `<input aria-label="Digit ${i + 1}" name="digit${i}" inputmode="numeric" pattern="[0-9]" maxlength="1" ${i === 0 ? 'autocomplete="one-time-code"' : 'autocomplete="off"'} required>`).join('')}</div></fieldset>${error}<button class="btn" type="submit">Verify email</button></form><button class="text-btn" id="resend-code">Resend verification code</button><p class="muted" id="resend-status" aria-live="polite"></p><button class="text-btn" id="cancel-auth">Use another account</button>`;
  } else if (mode === 'reset') {
    content = `<h1>Set your administrator password.</h1><p class="muted">Replace your initial password before opening administration.</p><form id="reset-form">${field('New password', 'password', 'password', 'required minlength="10" maxlength="128" autocomplete="new-password"')}${field('Confirm password', 'confirmation', 'password', 'required minlength="10" maxlength="128" autocomplete="new-password"')}${error}<button class="btn" type="submit">Save password</button></form>`;
  } else if (mode === 'forgot') {
    content = `<h1>Forgot your password?</h1><p class="muted">Enter your account email to request a reset code.</p><form id="forgot-form">${field('Email address', 'email', 'email', 'required autocomplete="email"')}${error}<button class="btn" type="submit">Send reset code</button></form><button class="text-btn" data-auth="recover">I already have a reset code</button><button class="text-btn" data-auth="login">Back to sign in</button>`;
  } else if (mode === 'recover') {
    content = `<h1>Choose a new password.</h1><p class="muted" id="recovery-status" role="status">Use the six-digit code from your email. Codes expire after 10 minutes.</p><form id="recover-form">${field('Email address', 'email', 'email', 'required autocomplete="email"')}${field('Reset code', 'code', 'text', 'required inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"')}${field('New password', 'password', 'password', 'required minlength="10" maxlength="128" autocomplete="new-password"')}${field('Confirm password', 'confirmation', 'password', 'required minlength="10" maxlength="128" autocomplete="new-password"')}${error}<button class="btn" type="submit">Reset password</button></form><button class="text-btn" data-auth="forgot">Request a new code</button><button class="text-btn" data-auth="login">Back to sign in</button>`;
  } else if (mode === 'login') {
    content = `<h1>Welcome to your learning space.</h1><form id="login-form"><div class="field"><label for="role">Sign in as</label><select id="role" name="role" required><option value="student">Student</option><option value="admin">Admin</option></select></div>${field('Email address', 'email', 'email', 'required autocomplete="username"')}${field('Password', 'password', 'password', 'required autocomplete="current-password"')}${error}<div class="login-actions"><button class="btn" type="submit">Sign in</button><button class="text-btn" type="button" data-auth="forgot">Forgot password?</button></div></form><button class="text-btn" data-auth="register">New here? Create an account</button>`;
  } else {
    app.innerHTML =
      navigation +
      `<main id="main" class="landing">
        <section class="landing-hero">
          <div class="landing-intro">
            <div class="eyebrow">South Africa’s peer learning space</div>
            <h1>Great things are<br>learned <em>together.</em></h1>
            <p class="landing-copy">Find a study partner who helps you move forward, and share what you know along the way.</p>
            <div class="landing-cta"><button class="btn" data-auth="register">Find your learning people <span aria-hidden="true">↗</span></button><a class="landing-secondary" href="#how-it-works">See how it works <span aria-hidden="true">↓</span></a></div>
            <div class="landing-proof"><span class="proof-avatars" aria-hidden="true"><i>S</i><i>L</i><i>T</i></span><span><b>A community that learns together</b><small>Verified students · 26 public universities</small></span></div>
          </div>
          <div class="landing-visual" aria-label="A preview of students learning together">
            <div class="scene-window"><div class="scene-top"><span></span><span></span><span></span><b>Study session · Online</b></div><div class="scene-photo-frame"><img class="scene-photo" src="/static/img/landing-study-group.png" alt="University students studying together around a table"></div><div class="scene-caption"><span class="scene-avatar">NM</span><span><b>Making progress, together</b><small>Computer Science · Year 3</small></span><span class="scene-check" aria-label="Verified">✓</span></div></div>
            <div class="scene-float scene-float-match"><span class="scene-icon">✦</span><span><b>Your kind of people</b><small>Shared goals. Better matches.</small></span></div>
            <div class="scene-float scene-float-topic"><span class="scene-icon">✓</span><span><b>Python study group</b><small>3 students · Ready when you are</small></span></div>
          </div>
        </section>
        <div class="landing-trust"><span>MADE FOR STUDENTS, BY THE SPIRIT OF SHARED LEARNING</span><b>26 public universities</b><b>Verified student community</b><b>Better learning, together</b></div>
        <section class="landing-section" id="how-it-works"><div class="section-kicker">A better way to learn</div><div class="landing-section-heading"><h2>From studying alone<br>to figuring it out together.</h2><p>Learning is easier when you have the right people beside you. Find your circle, share your strengths, and make a plan that works.</p></div><div class="landing-features"><article class="landing-feature"><span class="landing-feature-icon">⌕</span><small>01 · FIND YOUR PEOPLE</small><h3>Meet peers who get it.</h3><p>Discover verified students with shared modules, complementary skills, and goals that fit yours.</p></article><article class="landing-feature"><span class="landing-feature-icon">↔</span><small>02 · LEARN BOTH WAYS</small><h3>Give help. Get unstuck.</h3><p>Build confidence by sharing what you know and asking for support where you need it.</p></article><article class="landing-feature"><span class="landing-feature-icon">▦</span><small>03 · MAKE A PLAN</small><h3>Turn good intentions into progress.</h3><p>Arrange study sessions around your availability and keep your next steps in one place.</p></article></div></section>
        <section class="landing-preview"><div class="preview-copy"><div class="section-kicker">A little common ground goes a long way</div><h2>Find your next<br>study partner.</h2><p>Thoughtful matches built around what you’re learning, what you can share, and where you want to grow.</p><ul><li>See why each match makes sense</li><li>Connect with verified students</li><li>Keep your study plans together</li></ul><button class="btn" data-auth="register">Find your learning people <span aria-hidden="true">↗</span></button></div><div class="preview-board" aria-label="Example of a peer matching workspace"><div class="preview-board-bar"><span>AdaptoLearn</span><span>Find peers</span><span class="preview-board-pill">3 good matches</span></div><div class="preview-board-title"><b>People to learn with</b><small>Thoughtful matches, built around you.</small></div><div class="preview-match"><span class="preview-person preview-person-a">NM</span><div><b>Naledi Mokoena</b><small>University of Pretoria · Year 2</small><span class="preview-tags"><i>Python</i><i>Algorithms</i></span></div><strong>92%<small>match</small></strong></div><div class="preview-match"><span class="preview-person preview-person-b">TD</span><div><b>Thabo Dlamini</b><small>University of Johannesburg · Year 3</small><span class="preview-tags"><i>Data structures</i><i>Study group</i></span></div><strong>87%<small>match</small></strong></div><div class="preview-board-footer"><span>✓ Verified students</span><span>↗ View profile</span></div></div></section>
        <section class="landing-session"><div class="session-art" aria-hidden="true"><div class="session-art-card"><span>YOUR STUDY PLAN</span><b>Make time for progress.</b><i>◷ &nbsp; Tomorrow · 15:00</i><i>♧ &nbsp; Study with your circle</i><div class="session-art-avatars"><b>NM</b><b>TD</b><b>+2</b></div></div></div><div><div class="section-kicker">Good things happen when you show up</div><h2>Make “we should study”<br>an actual plan.</h2><p>Choose a study partner, pick a time, and focus on one thing together. Your sessions and invitations stay easy to find.</p><button class="btn" data-auth="register">Plan your first session <span aria-hidden="true">↗</span></button></div></section>
        <section class="landing-benefits" id="benefits"><div><div class="section-kicker">One community, across South Africa</div><h2>Different campuses.<br>The same curiosity.</h2><p>Your next study partner might be closer than you think.</p></div><div class="benefit-list"><div><b>01</b><span><strong>Made for South African students</strong><small>Connect through a network of public universities.</small></span></div><div><b>02</b><span><strong>Built around your learning</strong><small>Find complementary skills, subjects, and study styles.</small></span></div><div><b>03</b><span><strong>Verified, by design</strong><small>A student community grounded in campus email verification.</small></span></div></div></section>
        <section class="landing-last"><div class="landing-last-art" aria-hidden="true"><span>NM</span><span>TD</span><span>LM</span><b>Better, together.</b></div><div><div class="section-kicker">Your next chapter starts with someone</div><h2>You’re someone’s<br>missing piece.</h2><p>Share what you know. Find the support you need. Make studying feel less like doing it all alone.</p><button class="btn" data-auth="register">Join the learning community <span aria-hidden="true">↗</span></button></div></section>
        <section class="landing-faq" id="faqs"><div><div class="section-kicker">A few things you might be wondering</div><h2>Curiosity is<br>a good start.</h2></div><div class="faq-list"><details><summary>Who can join AdaptoLearn?<span>+</span></summary><p>Students at participating South African public universities can join with their official student email address.</p></details><details><summary>How are study partners matched?<span>+</span></summary><p>Matches take your modules, skills, learning needs, availability, and preferences into account.</p></details><details><summary>Do I have to be an expert to help someone?<span>+</span></summary><p>No. Learning is a two-way exchange. Share what you know and be open about what you’re still figuring out.</p></details><details><summary>How do study sessions work?<span>+</span></summary><p>Connect with a peer, agree on a time and place or meeting link, then keep your plans together in your workspace.</p></details></div></section>
        <section class="landing-final-cta"><div class="section-kicker">A good study partner can change the way you learn</div><h2>Your next chapter starts with someone.</h2><p>Find your people and make a little progress together.</p><button class="btn" data-auth="register">Start learning together <span aria-hidden="true">↗</span></button></section>
        <footer class="landing-footer"><a class="brand" href="/" aria-label="AdaptoLearn home"><img class="brand-logo" src="/static/img/logo-mark.png" alt="">AdaptoLearn</a><span>South Africa’s peer learning community.</span><div><button class="text-btn" data-auth="login">Sign in</button><button class="text-btn" data-auth="register">Join the community</button></div></footer>
      </main>`;
    bindNavigation(boot, refresh);
    return;
  }
  app.innerHTML = navigation + `<main id="main"><div class="auth-panel">${content}</div></main>`;
  bindNavigation(boot, refresh);
  if (mode === 'register') {
    const form = el('#register-form');
    const dropdown = el('#institution_id');
    const selected = () => {
      const item = boot.institutions.find((i) => i.id === Number(dropdown.value));
      if (!item) throw new ApiError('Select an active institution.', 400, 'institution_id');
      return item;
    };
    const update = () => {
      const domain = changeDomain(el('#email').value, selected());
      el('#email-suffix').textContent = domain.suffix;
      el('#email-hint').textContent = domain.example;
      el('#email-error').textContent = '';
    };
    if (boot.institutions.some((i) => i.isActive)) update();
    else {
      form.querySelector('button[type="submit"]').disabled = true;
      el('#email-error').textContent = 'Registrations are temporarily closed.';
    }
    dropdown.onchange = update;
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const values = formData(form);
        if (!validLocalPart(values.email)) {
          el('#email-error').textContent = 'Type only the part before @.';
          throw new ApiError('Enter a valid student email username.', 400, 'email');
        }
        const data = {
          ...values,
          institution_id: Number(values.institution_id),
          year: Number(values.year),
          email: buildStudentEmail(values.email, selected()),
        };
        validateBoundary(boot, 'register', data);
        await api('register', 'POST', data);
        await refresh();
        startCooldown();
      });
    };
  } else if (mode === 'forgot') {
    const form = el('#forgot-form');
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const email = formData(form).email.trim().toLowerCase();
        validateBoundary(boot, 'forgotPassword', { email });
        const result = await api('auth/forgot-password', 'POST', { email });
        renderAuth(boot, 'recover', refresh);
        el('#email').value = email;
        el('#recovery-status').textContent = result.message;
      });
    };
  } else if (mode === 'recover') {
    const form = el('#recover-form');
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const values = formData(form);
        if (values.password !== values.confirmation)
          throw new ApiError('Passwords do not match.', 400, 'confirmation');
        const data = {
          email: values.email.trim().toLowerCase(),
          code: values.code.trim(),
          password: values.password,
        };
        validateBoundary(boot, 'recoverPassword', data);
        await api('auth/recover-password', 'POST', data);
        await refresh();
        renderAuth(boot, 'login', refresh);
        toast('Password updated. Sign in with your new password.');
      });
    };
  } else if (mode === 'login') {
    const form = el('#login-form');
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const data = formData(form);
        data.email = data.email.trim().toLowerCase();
        validateBoundary(boot, 'login', data);
        const result = await api('login', 'POST', data);
        if (result.redirect?.startsWith('/admin')) location.assign(result.redirect);
        else await refresh();
      });
    };
  } else if (mode === 'verify') {
    bindDigits();
    const form = el('#verify-form');
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const code = [...form.querySelectorAll('.code-inputs input')].map((i) => i.value).join('');
        validateBoundary(boot, 'verify', { code });
        await api('verify', 'POST', { code });
        await refresh();
        toast('Email verified. Welcome to AdaptoLearn.');
      });
    };
    el('#resend-code').onclick = () => {
      void (async () => {
        try {
          await api('verification/resend', 'POST', {});
          el('#resend-status').textContent = 'A new code has been sent.';
          startCooldown();
        } catch (e) {
          toast(e instanceof Error ? e.message : 'Unable to resend code.', true);
        }
      })();
    };
    el('#cancel-auth').onclick = () => {
      void api('logout', 'POST', {}).then(refresh);
    };
  } else if (mode === 'reset') {
    const form = el('#reset-form');
    form.onsubmit = (event) => {
      event.preventDefault();
      void submit(form, async () => {
        const data = formData(form);
        if (data.password !== data.confirmation)
          throw new ApiError('Passwords do not match.', 400, 'confirmation');
        validateBoundary(boot, 'reset', { password: data.password });
        await api('auth/reset-password', 'POST', { password: data.password });
        location.assign('/admin/overview');
      });
    };
  }
}
function bindNavigation(boot, refresh) {
  document
    .querySelectorAll('[data-auth]')
    .forEach(
      (button) =>
        (button.onclick = () => renderAuth(boot, button.dataset.auth ?? 'login', refresh)),
    );
}
function validateBoundary(boot, name, data) {
  const field = validateSchema(boot.schemas[name], data);
  if (field) throw new ApiError('Check this field and try again.', 400, field);
}
function startCooldown() {
  const button = document.querySelector('#resend-code');
  if (!button) return;
  let seconds = 60;
  button.disabled = true;
  button.textContent = `Resend in ${seconds}s`;
  if (resendTimer) clearInterval(resendTimer);
  resendTimer = setInterval(() => {
    seconds--;
    button.textContent = seconds > 0 ? `Resend in ${seconds}s` : 'Resend verification code';
    if (seconds <= 0) {
      button.disabled = false;
      clearInterval(resendTimer);
    }
  }, 1000);
}
function bindDigits() {
  const inputs = [...document.querySelectorAll('.code-inputs input')];
  inputs.forEach((input, index) => {
    input.oninput = () => {
      input.value = input.value.replace(/\D/g, '').slice(-1);
      if (input.value && index < 5) inputs[index + 1].focus();
    };
    input.onpaste = (event) => {
      event.preventDefault();
      const digits = (event.clipboardData?.getData('text') ?? '').replace(/\D/g, '').slice(0, 6);
      if (digits.length === 6) {
        inputs.forEach((node, i) => (node.value = digits[i]));
        inputs[5].focus();
      } else
        digits.split('').forEach((digit, offset) => {
          if (inputs[index + offset]) inputs[index + offset].value = digit;
        });
    };
    input.onkeydown = (event) => {
      if (event.key === 'Backspace' && !input.value && index > 0) inputs[index - 1].focus();
      if (event.key === 'ArrowLeft' && index > 0) {
        event.preventDefault();
        inputs[index - 1].focus();
      }
      if (event.key === 'ArrowRight' && index < 5) {
        event.preventDefault();
        inputs[index + 1].focus();
      }
    };
  });
  inputs[0].focus();
}
