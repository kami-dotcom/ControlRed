'use strict';
const $ = (selector) => document.querySelector(selector);
const i18n = window.ControlI18n;
const t = (key, params) => i18n.t(key, params);
let token = location.hash.slice(1);
if (token) {
  sessionStorage.setItem('control-token', token);
  history.replaceState(null, '', location.pathname);
} else {
  token = sessionStorage.getItem('control-token') || '';
}
let state = null;
let filter = 'all';
let renameMac = '';
let requestPending = false;
let stopped = false;
let languageChanging = false;
let toastTimer;

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch('/api/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Control-Token': token, 'X-Control-Language': i18n.language, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || t('operation_failed'));
  return data;
}

async function refreshState() {
  const latest = await api('state');
  // A poll started in the previous language must not overwrite the new translation.
  if (latest.language === i18n.language) state = latest;
}

function roleName(device) {
  return device.role === 'Router' ? t('router') : device.role === 'Este PC' ? t('this_pc') : '';
}

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 5000);
}

async function command(action, data = {}) {
  requestPending = true;
  render();
  try {
    await api(action, data);
    await refreshState();
  } catch (error) {
    toast(error.message);
  } finally {
    requestPending = false;
    render();
  }
}

function deviceName(device) {
  return device.alias || device.hostname || roleName(device) || t('unknown_device');
}

function openRename(device) {
  renameMac = device.mac;
  $('#rename-description').textContent = device.ip + ' · ' + device.mac;
  $('#device-name').value = device.alias;
  $('#rename-dialog').showModal();
  $('#device-name').focus();
}

function deviceRow(device, busy) {
  const row = document.createElement('tr');
  const nameCell = document.createElement('td');
  const nameWrap = element('div', 'device');
  const icon = element('span', 'device-icon', device.role === 'Router' ? '⌁' : '▣');
  icon.setAttribute('aria-hidden', 'true');
  const details = element('div', 'device-text');
  const name = element('span', 'device-name', deviceName(device));
  name.title = deviceName(device);
  details.append(name);
  const meta = element('div', 'device-meta');
  meta.append(element('span', '', roleName(device) || (device.hostname ? t('name_detected') : t('name_pending'))));
  const ipv6 = (device.addresses || []).filter(ip => ip.includes(':'));
  if (ipv6.length) {
    const addressInfo = element('span', '', '· IPv6');
    addressInfo.title = ipv6.join('\n');
    meta.append(addressInfo);
  }
  const rename = element('button', 'rename', t('rename'));
  rename.dataset.key = 'rename-' + device.mac;
  rename.setAttribute('aria-label', t('rename') + ' · ' + deviceName(device));
  rename.disabled = busy;
  rename.onclick = () => openRename(device);
  meta.append(rename);
  details.append(meta);
  nameWrap.append(icon, details);
  nameCell.append(nameWrap);
  const makerCell = element('td', 'manufacturer', device.manufacturer || t('unknown_maker'));
  makerCell.title = (device.manufacturer || '') + ' · ' + t('mac_owner');
  row.append(nameCell, makerCell, element('td', '', device.ip), element('td', 'mono', device.mac));
  const statusCell = document.createElement('td');
  let label = t('permitted');
  let className = 'status';
  if (device.blocked) {
    label = t('block_requested');
    className += ' blocked';
  } else if (!device.online) {
    label = t('no_response');
    className += ' offline';
  }
  if (state.policy.mode === 'allowlist' && device.allowed && !device.protected) {
    label = device.online ? t('in_allowlist') : t('permitted_offline');
  }
  statusCell.append(element('span', className, label));
  row.append(statusCell);
  const actionCell = element('td', 'access');
  if (device.protected) {
    actionCell.append(element('span', 'protected', t('protected')));
  } else {
    const allowlist = state.policy.mode === 'allowlist';
    const granting = allowlist ? !device.allowed : device.blocked;
    const label = allowlist ? (granting ? t('allow') : t('revoke')) : (granting ? t('unblock') : t('block'));
    const action = element('button', 'action-button' + (granting ? ' unblock' : ''), label);
    action.dataset.key = 'block-' + device.mac;
    action.disabled = busy || (!allowlist && !device.blocked && (!state.can_block || !device.online));
    action.setAttribute('aria-label', label + ' · ' + deviceName(device));
    action.title = allowlist ? t('permission_by_mac') : (!state.can_block ? state.problem : t('control_bidirectional'));
    action.onclick = () => allowlist ? command('allow', {mac: device.mac, allowed: granting}) : command('block', {mac: device.mac, blocked: !device.blocked});
    actionCell.append(action);
  }
  row.append(actionCell);
  return row;
}

function renderPolicy(busy) {
  const policy = state.policy;
  const allowlist = policy.mode === 'allowlist';
  const hasNetwork = Boolean(state.context?.router_mac);
  $('#access-mode').value = policy.mode;
  $('#access-mode').disabled = busy || !hasNetwork;
  $('#access-mode option[value="allowlist"]').disabled = !state.can_block;
  $('#policy-description').textContent = allowlist
    ? t('policy_auto_description')
    : t('policy_manual_description');
  $('#policy-paused').hidden = !allowlist || !policy.paused;
  $('#resume-policy').disabled = busy || !state.can_block;
  $('#add-allowed').disabled = busy || !hasNetwork;
  $('#save-allowed').disabled = busy || !hasNetwork;
  $('#saved-count').textContent = policy.entries.length;
  $('#no-allowed').hidden = policy.entries.length > 0;
  $('#allowed-list').replaceChildren(...policy.entries.map(entry => {
    const item = element('li', 'allowed-entry');
    const description = element('div', 'allowed-description');
    description.append(element('strong', '', entry.name || t('allowed_device')));
    description.append(element('span', 'mono', entry.mac));
    description.append(element('span', 'hint', entry.manufacturer + ' · ' + (entry.online ? t('detected') : t('not_detected'))));
    const remove = element('button', 'action-button', t('revoke'));
    remove.dataset.key = 'remove-' + entry.mac;
    remove.disabled = busy;
    remove.setAttribute('aria-label', t('revoke') + ' · ' + (entry.name || entry.mac));
    remove.onclick = () => command('allow', {mac: entry.mac, allowed: false});
    item.append(description, remove);
    return item;
  }));
}

function render() {
  if (!state) return;
  const busy = requestPending || state.busy || state.scanning || state.closing || !state.ready;
  $('#demo').hidden = !state.demo;
  $('#error').hidden = !state.error;
  $('#error').textContent = state.error;
  $('#setup').hidden = !state.problem;
  $('#setup-text').textContent = state.problem;
  $('#scan').disabled = busy || !state.context;
  $('#scan-label').textContent = state.scanning ? t('scanning') : t('refresh');
  $('#scan-icon').classList.toggle('spinning', state.scanning);
  const devices = state.devices;
  const online = devices.filter(d => d.online);
  const blocked = devices.filter(d => d.blocked);
  $('#total').textContent = devices.length;
  $('#nav-count').textContent = devices.length;
  $('#tab-total').textContent = devices.length;
  $('#online-count').textContent = t('online_count', {count: online.length});
  $('#allowed').textContent = online.filter(d => !d.blocked).length;
  $('#blocked').textContent = blocked.length;
  const allowlist = state.policy.mode === 'allowlist';
  $('#release').textContent = allowlist ? t('pause_release') : t('release_all');
  $('#release').disabled = busy || (allowlist ? state.policy.paused : blocked.length === 0);
  const select = $('#interface');
  const signature = i18n.language + JSON.stringify(state.interfaces);
  if (select.dataset.signature !== signature) {
    select.replaceChildren(...state.interfaces.map(item => {
      const option = element('option', '', item.label);
      option.value = item.id;
      return option;
    }));
    select.dataset.signature = signature;
  }
  select.value = state.context?.id || '';
  select.disabled = busy || state.interfaces.length < 2;
  $('#network-detail').textContent = state.context ? t('network_detail', {subnet: state.context.subnet, gateway: state.context.gateway}) : t('no_network');
  $('#coverage').textContent = state.context?.routers_v6?.length ? t('ipv6_found') : t('ipv6_missing');
  const query = $('#search').value.toLocaleLowerCase(i18n.locale);
  const filtered = devices.filter(device => {
    const matchesFilter = filter === 'all' || (filter === 'blocked' ? device.blocked : (allowlist ? device.allowed : !device.blocked));
    const searchable = [deviceName(device), device.manufacturer, device.ip, device.mac, device.hostname, ...(device.addresses || [])].join(' ').toLocaleLowerCase(i18n.locale);
    return matchesFilter && searchable.includes(query);
  });
  const focusedKey = document.activeElement?.dataset.key;
  const rows = filtered.map(device => deviceRow(device, busy));
  $('#device-list').replaceChildren(...rows);
  renderPolicy(busy);
  if (focusedKey) {
    const next = [...document.querySelectorAll('[data-key]')].find(node => node.dataset.key === focusedKey);
    next?.focus({preventScroll: true});
  }
  $('#empty').hidden = filtered.length > 0;
  $('#empty h2').textContent = state.scanning && !devices.length ? t('finding_devices') : t('no_devices');
  $('#empty p').textContent = devices.length ? t('search_hint') : t('scan_hint');
  $('#last-scan').textContent = state.last_scan ? t('updated_at', {time: new Date(state.last_scan * 1000).toLocaleTimeString(i18n.locale, {hour:'2-digit', minute:'2-digit', second:'2-digit'})}) : t('waiting_scan');
  $('#events').replaceChildren(...state.events.slice(0, 5).map(event => {
    const item = document.createElement('li');
    item.append(element('time', '', new Date(event.time * 1000).toLocaleTimeString(i18n.locale, {hour:'2-digit',minute:'2-digit'})), element('span', '', event.text));
    return item;
  }));
  if (!state.events.length) $('#events').append(element('li', '', t('empty_events')));
}

$('#scan').onclick = () => command('scan');
$('#release').onclick = () => command('release');
$('#access-mode').onchange = event => command('mode', {mode: event.target.value});
$('#resume-policy').onclick = () => command('resume');
$('#add-allowed').onclick = () => {
  $('#allow-form').reset();
  $('#allowed-mac').setCustomValidity('');
  $('#allow-dialog').showModal();
  $('#allowed-mac').focus();
};
$('#cancel-allow').onclick = () => $('#allow-dialog').close();
$('#allowed-mac').oninput = () => $('#allowed-mac').setCustomValidity('');
$('#allow-form').onsubmit = event => {
  event.preventDefault();
  const input = $('#allowed-mac');
  const mac = input.value.trim().toLowerCase().replaceAll('-', ':');
  if (!/^([0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(mac) || (parseInt(mac.slice(0, 2), 16) & 1) || mac === '00:00:00:00:00:00') {
    input.setCustomValidity(t('invalid_mac_input'));
    input.reportValidity();
    return;
  }
  const name = $('#allowed-name').value.trim();
  $('#allow-dialog').close();
  command('allow', {mac, allowed: true, name});
};
$('#interface').onchange = event => command('select', {id: event.target.value});
$('#search').oninput = render;
document.querySelectorAll('.tab').forEach(tab => {
  tab.onclick = () => {
    filter = tab.dataset.filter;
    document.querySelectorAll('.tab').forEach(item => {
      item.classList.toggle('selected', item === tab);
      item.setAttribute('aria-selected', String(item === tab));
    });
    render();
  };
});
$('#cancel-rename').onclick = () => $('#rename-dialog').close();
$('#rename-form').onsubmit = event => {
  event.preventDefault();
  const name = $('#device-name').value.trim();
  $('#rename-dialog').close();
  command('rename', {mac: renameMac, name});
};
$('#quit').onclick = async () => {
  try {
    await api('shutdown', {});
    stopped = true;
    document.querySelectorAll('button, select, input').forEach(node => { node.disabled = true; });
    $('#error').textContent = t('closing_notice');
    $('#error').hidden = false;
  } catch (error) { toast(error.message); }
};

async function poll() {
  if (stopped) return;
  try {
    await refreshState();
    render();
  } catch (error) {
    $('#error').textContent = t('connection_lost', {detail: error.message});
    $('#error').hidden = false;
    document.querySelectorAll('.action-button, #scan, #release, #interface, #access-mode, #add-allowed, #save-allowed, #resume-policy').forEach(node => { node.disabled = true; });
  } finally {
    if (!stopped) setTimeout(poll, 2000);
  }
}
async function changeLanguage(code) {
  if (languageChanging) return;
  languageChanging = true;
  document.querySelectorAll('[data-language]').forEach(button => { button.disabled = true; });
  try {
    await i18n.setLanguage(code);
    $('#allowed-mac').setCustomValidity('');
    if (stopped) {
      $('#error').textContent = t('closing_notice');
    } else {
      render();
      await refreshState();
      render();
    }
  } catch (error) {
    toast(t('language_failed'));
  } finally {
    languageChanging = false;
    document.querySelectorAll('[data-language]').forEach(button => { button.disabled = false; });
  }
}

document.querySelectorAll('[data-language]').forEach(button => {
  button.onclick = () => changeLanguage(button.dataset.language);
});
i18n.init().then(() => {
  document.querySelectorAll('[data-language]').forEach(button => { button.disabled = false; });
  poll();
}).catch(() => {
  $('#error').textContent = 'Could not load language files. Restart the application.';
  $('#error').hidden = false;
});
