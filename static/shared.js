export const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c,
  );
export function el(selector) {
  const node = document.querySelector(selector);
  if (!node) throw new Error('Missing page element');
  return node;
}
export class ApiError extends Error {
  status;
  field;
  constructor(message, status, field = null) {
    super(message);
    this.status = status;
    this.field = field;
  }
}
let csrf = '';
export function setCsrf(value) {
  csrf = value;
}
export async function api(path, method = 'GET', data) {
  const response = await fetch('/api/' + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = result;
    throw new ApiError(
      error.error ?? 'Unable to complete this action.',
      response.status,
      error.field ?? null,
    );
  }
  return result;
}
let timer;
export function toast(message, error = false) {
  el('#toast').textContent = message;
  el('#toast').className = 'visible' + (error ? ' error' : '');
  clearTimeout(timer);
  timer = setTimeout(() => (el('#toast').className = ''), 4500);
}
export function message(error) {
  return error instanceof Error ? error.message : 'Unable to complete this action.';
}
export function formData(form) {
  return Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, String(value)]));
}
export function validateSchema(schema, data) {
  for (const key of schema.required ?? []) if (!(key in data)) return key;
  for (const [key, rule] of Object.entries(schema.properties ?? {})) {
    const value = data[key];
    if (value === undefined) continue;
    const types = Array.isArray(rule.type) ? rule.type : [rule.type];
    const actual =
      value === null
        ? 'null'
        : typeof value === 'number' && Number.isInteger(value)
          ? 'integer'
          : typeof value;
    if (rule.type && !types.includes(actual) && !(actual === 'integer' && types.includes('number')))
      return key;
    if (
      typeof value === 'string' &&
      ((rule.minLength !== undefined && value.length < rule.minLength) ||
        (rule.maxLength !== undefined && value.length > rule.maxLength) ||
        (rule.pattern && !new RegExp(rule.pattern).test(value)))
    )
      return key;
    if (
      typeof value === 'number' &&
      ((rule.minimum !== undefined && value < rule.minimum) ||
        (rule.maximum !== undefined && value > rule.maximum))
    )
      return key;
    if (rule.enum && !rule.enum.includes(value)) return key;
  }
  return null;
}
export function showFormError(form, error) {
  const target = form.querySelector('.error-text');
  if (target) target.textContent = message(error);
  if (error instanceof ApiError && error.field) {
    const input = form.elements.namedItem(error.field);
    if (input instanceof HTMLElement) {
      input.setAttribute('aria-invalid', 'true');
      input.focus();
    }
  }
}
export async function submit(form, work) {
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  form.querySelectorAll('[aria-invalid]').forEach((e) => e.removeAttribute('aria-invalid'));
  const error = form.querySelector('.error-text');
  if (error) error.textContent = '';
  try {
    await work();
  } catch (e) {
    showFormError(form, e);
  } finally {
    if (button) button.disabled = false;
  }
}
export function openModal(content) {
  el('#modal-content').innerHTML = content;
  el('#modal').showModal();
}
export function closeModal() {
  el('#modal').close();
}
export function bindClose() {
  document.addEventListener('click', (event) => {
    if (event.target.closest('.close')) closeModal();
  });
}
