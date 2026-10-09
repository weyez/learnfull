'use strict';
const $ = id => document.getElementById(id);
let busyTimer;
function unlocked(value) {
  $('login').hidden = value; $('ready').hidden = !value; $('logout').hidden = !value;
  $('url').disabled = !value; $('open').disabled = !value;
  $('status').textContent = value ? 'Сервер подключён' : 'Нужен ключ доступа';
}
fetch('/session').then(r => unlocked(r.ok)).catch(() => { $('login-note').textContent = 'Интерфейс без сервера. Разместите проект по инструкции.'; });
$('login').addEventListener('submit', async e => {
  e.preventDefault(); const button = $('login').querySelector('button'); button.disabled = true;
  try {
    const r = await fetch('/login', {method:'POST', body:new URLSearchParams({key:$('key').value})});
    if (!r.ok) throw new Error(r.status === 429 ? 'Слишком много попыток. Подождите минуту.' : 'Неверный ключ или сервер недоступен.');
    $('key').value = ''; unlocked(true); $('url').focus();
  } catch(err) { $('login-note').textContent = err.message; } finally { button.disabled = false; }
});
function openSite(value) {
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : 'https://' + value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error();
    $('url').value = url.href; $('welcome').hidden = true; $('viewer').hidden = false;
    $('status').textContent = 'Загрузка страницы…';
    clearTimeout(busyTimer);
    busyTimer = setTimeout(() => { $('status').textContent = 'Если страница не открылась, попробуйте другой адрес.'; }, 15000);
    $('frame').src = '/view?url=' + encodeURIComponent(url.href);
  } catch { $('status').textContent = 'Введите корректный адрес HTTP или HTTPS.'; }
}
$('address').addEventListener('submit', e => { e.preventDefault(); openSite($('url').value.trim()); });
$('example').addEventListener('click', () => openSite('https://example.com'));
$('frame').addEventListener('load', () => {
  clearTimeout(busyTimer);
  if ($('viewer').hidden) return;
  try {
    const p = new URL($('frame').contentWindow.location.href);
    const current = p.searchParams.get('url');
    if (current) $('url').value = current;
    const notice = $('frame').contentDocument.querySelector('.notice');
    const title = $('frame').contentDocument.querySelector('h2');
    $('status').textContent = notice ? 'Страница загружена · режим чтения' : (title?.textContent || 'Просмотр страницы');
  } catch { $('status').textContent = 'Просмотр страницы'; }
});
$('home').addEventListener('click', () => { clearTimeout(busyTimer); $('frame').src='about:blank'; $('viewer').hidden=true; $('welcome').hidden=false; $('status').textContent='Сервер подключён'; });
$('reload').addEventListener('click', () => openSite($('url').value));
$('logout').addEventListener('click', async () => {
  try { const r = await fetch('/logout',{method:'POST'}); if (!r.ok) throw new Error();
    $('home').click(); unlocked(false);
  } catch { $('status').textContent='Не удалось выйти. Повторите попытку.'; }
});
