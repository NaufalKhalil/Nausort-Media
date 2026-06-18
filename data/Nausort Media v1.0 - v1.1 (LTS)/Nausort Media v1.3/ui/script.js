'use strict';

// ── State ──────────────────────────────────────────────────
const S = {
  categories:   [],
  total:        0,
  photoCount:   0,
  videoCount:   0,
  currentIndex: -1,
  zoom:         1.0,
  panX:         0,
  panY:         0,
  isPanning:    false,
  panStartX:    0,
  panStartY:    0,
  imgNaturalW:  0,
  imgNaturalH:  0,
  baseScale:    1,
  ctxTarget:    null,
  ctxFolder:    '',
  colorTarget:  null,
  pickedColor:  '#2a2a2a',
  busy:         false,
};

// ── Color palette ──────────────────────────────────────────
const PALETTE = [
  ["#ff5050","#ff8c50","#ffc850","#dcff50","#8cff50","#50ff78","#50ffc8","#50c8ff","#508cff","#7850ff","#c850ff","#ff50c8"],
  ["#dc4646","#dc7846","#dcb446","#bedc46","#78dc46","#46dc64","#46dcb4","#46b4dc","#4678dc","#6446dc","#b446dc","#dc46b4"],
  ["#b43c3c","#b4643c","#b4963c","#a0b43c","#64b43c","#3cb45a","#3cb496","#3c96b4","#3c64b4","#5a3cb4","#963cb4","#b43c96"],
  ["#823232","#825032","#826e32","#788232","#508232","#328246","#32826e","#326e82","#325082","#463282","#6e3282","#82326e"],
  ["#5a2828","#5a3c28","#5a5028","#505a28","#3c5a28","#285a3c","#285a50","#28505a","#283c5a","#3c285a","#50285a","#5a2850"],
];

// ── Init ───────────────────────────────────────────────────
window.addEventListener('pywebviewready', async () => {
  buildColorPalette();
  bindColorPickerButtons();
  initResizeH();
  initResizeV();
  initDragDrop();
  await initApp();
});

async function initApp() {
  try {
    const data = await window.pywebview.api.get_init_data();
    S.categories   = data.categories || [];
    S.photoCount   = data.photo_count || 0;
    S.videoCount   = data.video_count || 0;
    S.total        = data.media_count ?? data.photo_count ?? 0;
    S.currentIndex = data.current_index ?? -1;
    renderCategories();
    updateStats();
    for (const entry of (data.log || [])) _appendLog(entry.msg, entry.tag);
    if (data.config_notice) showToast(data.config_notice, false);
  } catch(e) {
    console.error('Init failed:', e);
    setTimeout(initApp, 800);
  }
}

// ── Import folder ──────────────────────────────────────────
async function importFolder() {
  try {
    const res = await window.pywebview.api.import_folder();
    applyImportResult(res);
  } catch(e) { console.error(e); }
}

function applyImportResult(res) {
  if (!res || !res.ok) {
    if (res && res.silent) return;
    if (res && res.error) showToast(res.error, false);
    return;
  }
  S.total        = res.total ?? 0;
  S.photoCount   = res.photo_count ?? S.total;
  S.videoCount   = res.video_count ?? 0;
  S.currentIndex = res.current_index ?? -1;
  updateStats();
  if (res.toast) showToast(res.toast, true);
  if (res.image_data || res.is_video === true) showImage(res);
  else showPlaceholder(false);
}

window._onFolderDropped = function(jsonStr) {
  try {
    applyImportResult(JSON.parse(jsonStr));
  } catch(e) { console.error(e); }
};

window._setDropHighlight = function(active) {
  const container = document.getElementById('imgContainer');
  const overlay   = document.getElementById('dropOverlay');
  if (!container || !overlay) return;
  container.classList.toggle('drop-active', !!active);
  overlay.classList.toggle('hidden', !active);
};

function initDragDrop() {
  const zone = document.getElementById('imgContainer');
  if (!zone) return;
  ['dragenter', 'dragover'].forEach(ev => {
    zone.addEventListener(ev, e => {
      e.preventDefault();
      e.stopPropagation();
      window._setDropHighlight(true);
    });
  });
  zone.addEventListener('dragleave', e => {
    e.preventDefault();
    if (!zone.contains(e.relatedTarget)) window._setDropHighlight(false);
  });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    e.stopPropagation();
    window._setDropHighlight(false);
  });
}

// ── Image display ──────────────────────────────────────────
// Remember the original "Import a folder" placeholder markup so we can
// restore it after showing a "file rusak" error state.
let _defaultPlaceholderHTML = null;

function showImage(data) {
  const img         = document.getElementById('mainImage');
  const placeholder = document.getElementById('imgPlaceholder');
  const zoomCtrl    = document.getElementById('zoomControls');

  if (_defaultPlaceholderHTML === null) {
    _defaultPlaceholderHTML = placeholder.innerHTML;
  }

  if (data.is_video) {
    showVideoPreview(data);
    S.currentIndex = data.index ?? S.currentIndex;
    S.total        = data.total ?? S.total;
    if (data.photo_count !== undefined) S.photoCount = data.photo_count;
    if (data.video_count !== undefined) S.videoCount = data.video_count;
    updateStats();
    updateProgress();
    return;
  }

  if (!data.image_data) {
    if (data.error) {
      showCorruptError(data);
    } else {
      showPlaceholder();
    }
    // Even if the image itself failed to load, keep stats/progress/index
    // in sync so the user can still navigate away from the bad file.
    S.currentIndex = data.index ?? S.currentIndex;
    S.total        = data.total ?? S.total;
    updateStats();
    updateProgress();
    return;
  }

  // Remove any video-preview injected directly into the container
  const vp = document.getElementById('imgContainer').querySelector('.video-preview');
  if (vp) vp.remove();

  placeholder.innerHTML = _defaultPlaceholderHTML;
  placeholder.classList.add('hidden');
  img.classList.remove('hidden');
  zoomCtrl.classList.remove('hidden');

  S.zoom = 1; S.panX = 0; S.panY = 0;
  img.onload = () => {
    S.imgNaturalW = img.naturalWidth;
    S.imgNaturalH = img.naturalHeight;
    fitImage();
  };
  img.src = data.image_data;
  document.getElementById('filenameLabel').textContent = data.filename || '';
  S.currentIndex = data.index ?? S.currentIndex;
  S.total        = data.total ?? S.total;
  if (data.photo_count !== undefined) S.photoCount = data.photo_count;
  if (data.video_count !== undefined) S.videoCount = data.video_count;
  updateStats();
  updateProgress();
}

function showVideoPreview(data) {
  const container   = document.getElementById('imgContainer');
  const img         = document.getElementById('mainImage');
  const placeholder = document.getElementById('imgPlaceholder');
  const zoomCtrl    = document.getElementById('zoomControls');

  // Save default placeholder HTML before we hide/modify it
  if (_defaultPlaceholderHTML === null) {
    _defaultPlaceholderHTML = placeholder.innerHTML;
  }

  img.classList.add('hidden');
  zoomCtrl.classList.add('hidden');
  img.removeAttribute('src');

  // Hide placeholder so it doesn't overlap
  placeholder.classList.add('hidden');

  // Remove any existing video-preview element
  const existing = container.querySelector('.video-preview');
  if (existing) existing.remove();

  // Append video-preview directly to imgContainer so
  // position:absolute / inset:0 resolves correctly
  const wrap = document.createElement('div');
  wrap.className = 'video-preview';

  const icon = document.createElement('div');
  icon.className   = 'video-preview-icon';
  icon.textContent = '🎬';

  const nameEl = document.createElement('div');
  nameEl.className   = 'video-preview-filename';
  nameEl.textContent = data.filename || 'Video';

  const label = document.createElement('div');
  label.className   = 'video-preview-text';
  label.textContent = 'Video Preview';
  label.style.opacity = '0.5';

  wrap.appendChild(icon);
  wrap.appendChild(nameEl);
  wrap.appendChild(label);
  container.appendChild(wrap);

  document.getElementById('filenameLabel').textContent = data.filename || '';
}

// Shown when the current photo exists but couldn't be decoded (corrupt /
// unsupported file). Lets the user skip to the next photo instead of
// staring at a blank viewer.
function showCorruptError(data) {
  const img         = document.getElementById('mainImage');
  const placeholder = document.getElementById('imgPlaceholder');
  const zoomCtrl    = document.getElementById('zoomControls');

  img.classList.add('hidden');
  zoomCtrl.classList.add('hidden');
  img.removeAttribute('src');

  // Remove any video-preview injected directly into the container
  const vp = document.getElementById('imgContainer').querySelector('.video-preview');
  if (vp) vp.remove();

  placeholder.innerHTML = '';

  const icon = document.createElement('div');
  icon.className   = 'placeholder-icon';
  icon.textContent = '⚠️';

  const text = document.createElement('div');
  text.className   = 'placeholder-text';
  text.style.color = 'var(--error)';
  text.textContent = `File rusak: ${data.filename || ''}`;

  const skipBtn = document.createElement('button');
  skipBtn.className   = 'import-btn-big';
  skipBtn.textContent = 'Skip ke foto berikutnya';
  skipBtn.onclick     = () => goNext();

  placeholder.appendChild(icon);
  placeholder.appendChild(text);
  placeholder.appendChild(skipBtn);
  placeholder.classList.remove('hidden');

  document.getElementById('filenameLabel').textContent = data.filename || '';
  showToast(`File rusak, dilewati: ${data.filename || ''}`, false);
}

function showPlaceholder(resetStats = true) {
  const container   = document.getElementById('imgContainer');
  const placeholder = document.getElementById('imgPlaceholder');

  // Remove any video-preview injected directly into the container
  const vp = container.querySelector('.video-preview');
  if (vp) vp.remove();

  if (_defaultPlaceholderHTML !== null) placeholder.innerHTML = _defaultPlaceholderHTML;
  document.getElementById('mainImage').classList.add('hidden');
  placeholder.classList.remove('hidden');
  document.getElementById('zoomControls').classList.add('hidden');
  document.getElementById('filenameLabel').textContent = 'No media loaded';
  document.getElementById('progressBar').style.width   = '0%';
  if (resetStats) {
    S.total = 0; S.photoCount = 0; S.videoCount = 0; S.currentIndex = -1;
    updateStats();
  }
}

// ── Fit image ──────────────────────────────────────────────
function fitImage() {
  const container = document.getElementById('imgContainer');
  const img       = document.getElementById('mainImage');
  if (!img || img.classList.contains('hidden')) return;

  const cw = container.clientWidth;
  const ch = container.clientHeight;
  const iw = S.imgNaturalW || img.naturalWidth  || cw;
  const ih = S.imgNaturalH || img.naturalHeight || ch;

  S.baseScale = Math.min(cw / iw, ch / ih, 1);
  const dispW = iw * S.baseScale * S.zoom;
  const dispH = ih * S.baseScale * S.zoom;

  img.style.width    = dispW + 'px';
  img.style.height   = dispH + 'px';
  img.style.left     = ((cw - dispW) / 2 + S.panX) + 'px';
  img.style.top      = ((ch - dispH) / 2 + S.panY) + 'px';
  img.style.position = 'absolute';
}

// ── Zoom (cursor-centred) ──────────────────────────────────
function applyZoom(newZoom, cursorX, cursorY) {
  const container = document.getElementById('imgContainer');
  const img       = document.getElementById('mainImage');
  if (!img || img.classList.contains('hidden')) return;

  const cw = container.clientWidth,  ch = container.clientHeight;
  const iw = S.imgNaturalW || img.naturalWidth  || cw;
  const ih = S.imgNaturalH || img.naturalHeight || ch;
  const bs = S.baseScale || Math.min(cw / iw, ch / ih, 1);

  const cx = (cursorX !== undefined) ? cursorX : cw / 2;
  const cy = (cursorY !== undefined) ? cursorY : ch / 2;

  const oldW   = iw * bs * S.zoom;
  const oldH   = ih * bs * S.zoom;
  const imgL   = (cw - oldW) / 2 + S.panX;
  const imgT   = (ch - oldH) / 2 + S.panY;
  const fracX  = (cx - imgL) / oldW;
  const fracY  = (cy - imgT) / oldH;

  S.zoom = Math.min(Math.max(newZoom, 0.1), 12);
  const newW = iw * bs * S.zoom;
  const newH = ih * bs * S.zoom;
  S.panX = cx - (cw - newW) / 2 - fracX * newW;
  S.panY = cy - (ch - newH) / 2 - fracY * newH;
  fitImage();
}

function zoomIn(cx, cy)  { applyZoom(S.zoom * 1.25, cx, cy); }
function zoomOut(cx, cy) { applyZoom(S.zoom / 1.25, cx, cy); }
function zoomReset()     { S.zoom = 1; S.panX = 0; S.panY = 0; fitImage(); }

// ── Pan + scroll ───────────────────────────────────────────
(function initPan() {
  const container = document.getElementById('imgContainer');

  container.addEventListener('mousedown', e => {
    const img = document.getElementById('mainImage');
    if (e.target !== img) return;
    S.isPanning = true;
    S.panStartX = e.clientX - S.panX;
    S.panStartY = e.clientY - S.panY;
    img.style.cursor = 'grabbing';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!S.isPanning) return;
    S.panX = e.clientX - S.panStartX;
    S.panY = e.clientY - S.panStartY;
    fitImage();
  });
  document.addEventListener('mouseup', () => {
    if (!S.isPanning) return;
    S.isPanning = false;
    const img = document.getElementById('mainImage');
    if (img) img.style.cursor = 'grab';
  });
  container.addEventListener('wheel', e => {
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    if (e.deltaY < 0) zoomIn(e.clientX - rect.left, e.clientY - rect.top);
    else              zoomOut(e.clientX - rect.left, e.clientY - rect.top);
  }, { passive: false });
  container.addEventListener('dblclick', () => zoomReset());
  new ResizeObserver(() => fitImage()).observe(container);
})();

// ── Navigation ─────────────────────────────────────────────
async function goPrev() {
  const res = await window.pywebview.api.go_prev();
  if (res) showImage(res);
}
async function goNext() {
  const res = await window.pywebview.api.go_next();
  if (res) showImage(res);
}
async function doUndo() {
  const res = await window.pywebview.api.undo();
  if (res && res.ok) {
    if (res.photo_count !== undefined) S.photoCount = res.photo_count;
    if (res.video_count !== undefined) S.videoCount = res.video_count;
    S.total = res.total ?? S.total;
    if (res.image_data || res.is_video === true) showImage(res);
    else showPlaceholder(false);
  }
}
async function doRedo() {
  const res = await window.pywebview.api.redo();
  if (res && res.ok) {
    if (res.photo_count !== undefined) S.photoCount = res.photo_count;
    if (res.video_count !== undefined) S.videoCount = res.video_count;
    S.total = res.total ?? S.total;
    if (res.image_data || res.is_video === true) showImage(res);
    else showPlaceholder(false);
  }
}

// ── Sort ───────────────────────────────────────────────────
async function sortTo(index, conflictAction) {
  if (S.busy) return; // ignore clicks/shortcuts while a move is in progress
  S.busy = true;
  setCatButtonsBusy(true);
  try {
    const res = await window.pywebview.api.sort_to(index, conflictAction);
    if (!res) { showToast('Move failed', false); return; }

    if (res.conflict) {
      // Destination already has a file with this name - let the user decide.
      S.busy = false;
      setCatButtonsBusy(false);
      showConflictModal(res.filename, () => sortTo(index, 'replace'),
                                       () => sortTo(index, 'keep_both'),
                                       () => sortTo(index, 'cancel'));
      return;
    }

    if (!res.ok) {
      if (!res.cancelled) showToast(res.error || 'Move failed', false);
      if (res.cancelled) showToast('Sorting dibatalkan', true);
      return;
    }

    S.total = res.total ?? S.total;
    if (res.photo_count !== undefined) S.photoCount = res.photo_count;
    if (res.video_count !== undefined) S.videoCount = res.video_count;

    if (res.session_complete && res.summary) {
      showSummaryModal(res.summary);
    }

    if (res.image_data || res.is_video === true) showImage(res);
    else if (res.error)  showImage(res);
    else                 showPlaceholder(false);
  } finally {
    S.busy = false;
    setCatButtonsBusy(false);
  }
}

// Visually disable category buttons while a sort operation is running so
// holding/spamming a shortcut or clicking repeatedly can't queue up
// multiple moves at once.
function setCatButtonsBusy(isBusy) {
  const wrap = document.getElementById('catWrap');
  if (wrap) wrap.classList.toggle('busy', isBusy);
}

// 3-way modal for filename conflicts: Replace / Keep Both / Cancel
function showConflictModal(filename, onReplace, onKeepBoth, onCancel) {
  document.getElementById('modalTitle').textContent = 'File Sudah Ada';

  const body = document.getElementById('modalBody');
  body.innerHTML = '';
  const p = document.createElement('p');
  p.style.cssText = 'font-size:12px;color:var(--text);';
  p.textContent   = `"${filename}" sudah ada di folder tujuan. Pilih tindakan:`;
  body.appendChild(p);

  const footer = document.getElementById('modalFooter');
  footer.innerHTML = '';

  const btnCancel = document.createElement('button');
  btnCancel.className   = 'modal-btn';
  btnCancel.textContent = 'Cancel';
  btnCancel.addEventListener('click', e => { e.stopPropagation(); _dismissModal(); onCancel(); });

  const btnKeepBoth = document.createElement('button');
  btnKeepBoth.className   = 'modal-btn';
  btnKeepBoth.textContent = 'Keep Both';
  btnKeepBoth.addEventListener('click', e => { e.stopPropagation(); _dismissModal(); onKeepBoth(); });

  const btnReplace = document.createElement('button');
  btnReplace.className   = 'modal-btn primary';
  btnReplace.textContent = 'Replace';
  btnReplace.addEventListener('click', e => { e.stopPropagation(); _dismissModal(); onReplace(); });

  footer.appendChild(btnCancel);
  footer.appendChild(btnKeepBoth);
  footer.appendChild(btnReplace);
  _modalCallback = null;
  _openModal();
}

// ── Render categories ──────────────────────────────────────
function renderCategories() {
  const wrap = document.getElementById('catWrap');
  wrap.innerHTML = '';
  S.categories.forEach((cat, i) => {
    const btn = document.createElement('button');
    btn.className        = 'cat-btn';
    btn.style.background = cat.color || '#2a2a2a';
    btn.appendChild(document.createTextNode(cat.name));
    if (cat.shortcut) {
      const sc = document.createElement('span');
      sc.className   = 'cat-shortcut';
      sc.textContent = `[${cat.shortcut}]`;
      btn.appendChild(sc);
    }
    btn.addEventListener('click',       () => sortTo(i));
    btn.addEventListener('contextmenu', e  => { e.preventDefault(); showCtxMenu(e, i, cat); });
    wrap.appendChild(btn);
  });
}

async function addCategory() {
  showInputModal('Add Category', 'Category name:', '', async (name) => {
    if (!name || !name.trim()) return;
    const res = await window.pywebview.api.add_category(name.trim());
    if (res && res.ok) { S.categories = res.categories; renderCategories(); }
  });
}

// ── Context menu ───────────────────────────────────────────
let _ctxIndex = -1;

function showCtxMenu(e, index, cat) {
  _ctxIndex   = index;
  S.ctxTarget = cat;
  S.ctxFolder = cat.folder || '';

  const menu     = document.getElementById('ctxMenu');
  const info     = document.getElementById('ctxFolderInfo');
  const openBtn  = document.getElementById('ctxOpenFolder');

  if (S.ctxFolder) {
    const name = S.ctxFolder.split(/[\\/]/).pop();
    openBtn.textContent = `📁 ${name.length > 28 ? name.slice(0,27)+'…' : name} ↗`;
    info.classList.remove('hidden');
  } else {
    info.classList.add('hidden');
  }

  menu.classList.remove('hidden');
  menu.style.left = e.clientX + 'px';
  menu.style.top  = e.clientY + 'px';

  requestAnimationFrame(() => {
    const r = menu.getBoundingClientRect();
    if (r.right  > window.innerWidth)  menu.style.left = (e.clientX - r.width)  + 'px';
    if (r.bottom > window.innerHeight) menu.style.top  = (e.clientY - r.height) + 'px';
  });
}

function hideCtxMenu() { document.getElementById('ctxMenu').classList.add('hidden'); }

function ctxOpenFolder() {
  hideCtxMenu();
  window.pywebview.api.open_category_folder(_ctxIndex);
}
async function ctxSetFolder() {
  hideCtxMenu();
  const res = await window.pywebview.api.choose_category_folder(_ctxIndex);
  if (res && res.ok) { S.categories = res.categories; renderCategories(); }
}
function ctxRename() {
  hideCtxMenu();
  showInputModal('Rename Category', 'New name:', S.ctxTarget?.name || '', async (name) => {
    if (!name || !name.trim()) return;
    const res = await window.pywebview.api.rename_category(_ctxIndex, name.trim());
    if (res && res.ok) { S.categories = res.categories; renderCategories(); }
  });
}
function ctxChangeColor() {
  hideCtxMenu();
  S.colorTarget = _ctxIndex;
  openColorPicker(S.ctxTarget?.color || '#2a2a2a');
}
function ctxChangeShortcut() {
  hideCtxMenu();
  showInputModal('Change Shortcut', 'New shortcut (1 character):', S.ctxTarget?.shortcut || '', async (sc) => {
    const res = await window.pywebview.api.set_category_shortcut(_ctxIndex, sc || '');
    if (res && res.ok) {
      S.categories = res.categories;
      renderCategories();
    } else {
      showToast(res?.error || 'Gagal mengubah shortcut', false);
    }
  });
}

function ctxDelete() {
  const index = _ctxIndex;
  const name  = S.ctxTarget?.name || 'this category';
  hideCtxMenu();
  // Defer so the document click from hiding ctx-menu doesn't close the modal
  setTimeout(() => {
    showConfirmModal(`Delete category "${name}"?`, async () => {
      const res = await window.pywebview.api.delete_category(index);
      if (res && res.ok) {
        S.categories = res.categories;
        renderCategories();
        showToast(`Deleted: ${name}`, true);
      } else {
        showToast('Delete failed', false);
      }
    });
  }, 0);
}

// ── Keyboard shortcuts ─────────────────────────────────────
document.addEventListener('keydown', async e => {
  const active    = document.activeElement;
  const inInput   = active && (
    active.tagName === 'INPUT' ||
    active.tagName === 'TEXTAREA' ||
    active.tagName === 'SELECT' ||
    active.isContentEditable
  );
  const modalOpen = !document.getElementById('modalOverlay').classList.contains('hidden')
                 || !document.getElementById('colorOverlay').classList.contains('hidden');
  if (inInput || modalOpen) return;

  if      (e.key === 'ArrowLeft')  { e.preventDefault(); goPrev(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); goNext(); }
  else if ((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='z') {
    // Fix #3: Ignore key-repeat so holding Ctrl+Z can't fire multiple undos.
    if (e.repeat) return;
    e.preventDefault();
    doUndo();
  }
  else if ((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='y') {
    // Fix #3: Same repeat guard for Ctrl+Y / Redo.
    if (e.repeat) return;
    e.preventDefault();
    doRedo();
  }
  else if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomIn();  }
  else if (e.key === '-')                  { e.preventDefault(); zoomOut(); }
  else if (e.key === 'Backspace')          { e.preventDefault(); zoomReset(); }
  else {
    // Category shortcuts: 1 keypress = 1 sort. Holding the key down fires
    // repeated keydown events with e.repeat = true - ignore those so a
    // held key can't spam-sort multiple photos.
    if (e.repeat) return;
    // Fix #9: Don't fire category shortcuts when there are no photos loaded.
    if (S.total === 0) return;
    const char = e.key.toUpperCase();
    S.categories.forEach((cat, i) => {
      if (cat.shortcut && cat.shortcut.toUpperCase() === char) sortTo(i);
    });
  }
});

// ── Stats / Progress ───────────────────────────────────────
function updateStats() {
  document.getElementById('statsPhotos').textContent = S.photoCount;
  document.getElementById('statsVideos').textContent = S.videoCount;
  document.getElementById('statsTotal').textContent  = S.total;
  document.getElementById('statsIndex').textContent =
    S.currentIndex >= 0 ? `${S.currentIndex + 1}/${S.total}` : '-';
}
function updateProgress() {
  const pct = S.total > 0 ? ((S.currentIndex + 1) / S.total) * 100 : 0;
  document.getElementById('progressBar').style.width = pct + '%';
}

// ── Terminal ───────────────────────────────────────────────
const MAX_LOG = 500, TRIM_LOG = 350;
let logCount = 0;

window._appendLog = function(msg, tag = 'info') {
  const lines = document.getElementById('termLines');
  const div   = document.createElement('div');
  const tagMap = { info:'log-info', move:'log-move', undo:'log-undo',
                   redo:'log-redo', warn:'log-warn', dim:'log-dim' };
  div.className   = tagMap[tag] || '';
  div.textContent = msg;
  lines.appendChild(div);
  if (++logCount >= MAX_LOG) {
    const del = logCount - TRIM_LOG;
    for (let i = 0; i < del; i++) if (lines.firstChild) lines.removeChild(lines.firstChild);
    logCount = TRIM_LOG;
  }
  document.getElementById('terminal').scrollTop = 999999;
};

function clearTerminal() {
  document.getElementById('termLines').innerHTML = '';
  logCount = 0;
}

// ── Color Picker ───────────────────────────────────────────
function buildColorPalette() {
  const grid = document.getElementById('colorPalette');
  PALETTE.forEach(row => row.forEach(color => {
    const sw = document.createElement('div');
    sw.className = 'swatch';
    sw.style.background = color;
    sw.dataset.color = color;
    sw.addEventListener('click', () => selectSwatch(color));
    grid.appendChild(sw);
  }));
}

function bindColorPickerButtons() {
  const cancelBtn = document.getElementById('colorCancelBtn');
  const applyBtn  = document.getElementById('colorApplyBtn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', e => {
      e.stopPropagation();
      document.getElementById('colorOverlay').classList.add('hidden');
    });
  }
  if (applyBtn) {
    applyBtn.addEventListener('click', e => {
      e.stopPropagation();
      applyColor();
    });
  }
}

function openColorPicker(initial = '#2a2a2a') {
  S.pickedColor = initial;
  document.getElementById('colorOverlay').classList.remove('hidden');
  updateColorUI(initial);
}

function selectSwatch(color) { S.pickedColor = color; updateColorUI(color); }

function updateColorUI(hex) {
  document.getElementById('colorPreview').style.background = hex;
  document.getElementById('colorHexInput').value = hex;
  document.querySelectorAll('.swatch').forEach(sw =>
    sw.classList.toggle('selected', sw.dataset.color === hex));
  const rgb = hexToRgb(hex);
  if (rgb) {
    ['R','G','B'].forEach(c => {
      document.getElementById('slider'+c).value = rgb[c.toLowerCase()];
      document.getElementById('val'+c).textContent = rgb[c.toLowerCase()];
    });
  }
}

function onHexInput(val) {
  if (!val.startsWith('#')) val = '#' + val;
  if (/^#[0-9a-fA-F]{6}$/.test(val)) { S.pickedColor = val; updateColorUI(val); }
}

function onSlider() {
  const r = +document.getElementById('sliderR').value;
  const g = +document.getElementById('sliderG').value;
  const b = +document.getElementById('sliderB').value;
  document.getElementById('valR').textContent = r;
  document.getElementById('valG').textContent = g;
  document.getElementById('valB').textContent = b;
  const hex = rgbToHex(r, g, b);
  S.pickedColor = hex;
  document.getElementById('colorPreview').style.background = hex;
  document.getElementById('colorHexInput').value = hex;
  document.querySelectorAll('.swatch').forEach(sw =>
    sw.classList.toggle('selected', sw.dataset.color === hex));
}

async function applyColor() {
  const color  = S.pickedColor;
  const target = S.colorTarget;
  document.getElementById('colorOverlay').classList.add('hidden');
  if (target === null) return;
  const res = await window.pywebview.api.set_category_color(target, color);
  if (res && res.ok) { S.categories = res.categories; renderCategories(); }
}

function closeColorPicker(e) {
  if (e && e.target !== document.getElementById('colorOverlay')) return;
  document.getElementById('colorOverlay').classList.add('hidden');
}

function hexToRgb(hex) {
  const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return r ? { r:parseInt(r[1],16), g:parseInt(r[2],16), b:parseInt(r[3],16) } : null;
}
function rgbToHex(r, g, b) {
  return '#' + [r,g,b].map(v => Math.max(0,Math.min(255,v)).toString(16).padStart(2,'0')).join('');
}

// ── Modal (Input + Confirm) ────────────────────────────────
let _modalCallback = null;

function _openModal()    { document.getElementById('modalOverlay').classList.remove('hidden'); }
function _dismissModal() { document.getElementById('modalOverlay').classList.add('hidden'); _modalCallback = null; }

function closeModal(e) {
  if (e && e.target !== document.getElementById('modalOverlay')) return;
  _dismissModal();
}

function showInputModal(title, label, initial, onOk) {
  _modalCallback = onOk;
  document.getElementById('modalTitle').textContent = title;

  const body  = document.getElementById('modalBody');
  body.innerHTML = '';
  const p = document.createElement('p');
  p.style.cssText = 'font-size:11px;color:var(--text-dim);margin-bottom:8px;';
  p.textContent   = label;

  const input   = document.createElement('input');
  input.type    = 'text';
  input.value   = initial;
  input.id      = 'modalInput';
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.stopPropagation(); confirmModal(); }
    if (e.key === 'Escape') { e.stopPropagation(); _dismissModal(); }
  });
  body.appendChild(p);
  body.appendChild(input);

  const footer = document.getElementById('modalFooter');
  footer.innerHTML = '';

  const btnCancel = document.createElement('button');
  btnCancel.className   = 'modal-btn';
  btnCancel.textContent = 'Cancel';
  btnCancel.addEventListener('click', e => { e.stopPropagation(); _dismissModal(); });

  const btnOk = document.createElement('button');
  btnOk.className   = 'modal-btn primary';
  btnOk.textContent = 'OK';
  btnOk.addEventListener('click', e => { e.stopPropagation(); confirmModal(); });

  footer.appendChild(btnCancel);
  footer.appendChild(btnOk);
  _openModal();
  setTimeout(() => input.focus(), 50);
}

function showConfirmModal(message, onOk) {
  _modalCallback = onOk;
  document.getElementById('modalTitle').textContent = 'Confirm';

  const body = document.getElementById('modalBody');
  body.innerHTML = '';
  const p = document.createElement('p');
  p.style.cssText = 'font-size:12px;color:var(--text);';
  p.textContent   = message;
  body.appendChild(p);

  const footer = document.getElementById('modalFooter');
  footer.innerHTML = '';

  const btnCancel = document.createElement('button');
  btnCancel.className   = 'modal-btn';
  btnCancel.textContent = 'Cancel';
  btnCancel.addEventListener('click', e => { e.stopPropagation(); _dismissModal(); });

  const btnDelete = document.createElement('button');
  btnDelete.className        = 'modal-btn primary';
  btnDelete.textContent      = 'Delete';
  btnDelete.style.background = 'var(--error)';
  btnDelete.style.borderColor= 'var(--error)';
  btnDelete.style.color      = '#fff';
  btnDelete.addEventListener('click', e => {
    e.stopPropagation();
    const cb = _modalCallback;
    _dismissModal();
    if (cb) cb();
  });

  footer.appendChild(btnCancel);
  footer.appendChild(btnDelete);
  _openModal();
}

function confirmModal() {
  const input = document.getElementById('modalInput');
  const val   = input ? input.value : '';
  const cb    = _modalCallback;
  _dismissModal();
  if (cb) cb(val);
}

// ── Toast ──────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg, ok = true) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = 'toast' + (ok ? '' : ' error');
  t.classList.remove('hidden');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.add('hidden'), 2500);
}

// ── Sorting summary ────────────────────────────────────────
function showSummaryModal(summary) {
  const body = document.getElementById('summaryBody');
  body.innerHTML = '';

  const rows = [
    ['Foto Disortir',       summary.photos_sorted],
    ['Video Disortir',      summary.videos_sorted],
    ['Total Media',         summary.total_media],
    ['Folder Dibuat',       summary.folders_created],
    ['File Tidak Didukung', summary.unsupported_files],
  ];
  rows.forEach(([label, value]) => body.appendChild(_summaryRow(label, value)));

  const divider = document.createElement('div');
  divider.className = 'summary-divider';
  body.appendChild(divider);

  const statusRow = document.createElement('div');
  statusRow.className = 'summary-row';
  const statusLabel = document.createElement('span');
  statusLabel.className   = 'summary-label';
  statusLabel.textContent = 'Status';
  const statusValue = document.createElement('span');
  statusValue.className = 'summary-value ' + (summary.source_clean ? 'summary-status-clean' : 'summary-status-warn');
  statusValue.textContent = summary.source_clean
    ? 'Folder sumber sudah kosong'
    : 'Folder sumber masih berisi file';
  statusRow.appendChild(statusLabel);
  statusRow.appendChild(statusValue);
  body.appendChild(statusRow);

  if (!summary.source_clean) {
    body.appendChild(_summaryRow('File Tersisa', summary.source_remaining));
    body.appendChild(_summaryRow('File Tidak Didukung', summary.source_unsupported));
  }

  body.appendChild(_summaryRow('Total Data', summary.total_data));

  document.getElementById('summaryOverlay').classList.remove('hidden');
}

function _summaryRow(label, value) {
  const row = document.createElement('div');
  row.className = 'summary-row';
  const l = document.createElement('span');
  l.className   = 'summary-label';
  l.textContent = label;
  const v = document.createElement('span');
  v.className   = 'summary-value';
  v.textContent = value;
  row.appendChild(l);
  row.appendChild(v);
  return row;
}

function closeSummary(e) {
  if (e && e.target !== document.getElementById('summaryOverlay')) return;
  document.getElementById('summaryOverlay').classList.add('hidden');
}

// ── Global click: close context menu ──────────────────────
document.addEventListener('click', e => {
  if (!e.target.closest('#ctxMenu')) hideCtxMenu();
});
document.addEventListener('contextmenu', e => {
  if (!e.target.closest('.cat-btn')) { e.preventDefault(); hideCtxMenu(); }
});

// ── Horizontal splitter: left ↔ right ─────────────────────
function initResizeH() {
  const handle    = document.getElementById('resizeHandle');
  const panelLeft = document.getElementById('panelLeft');
  let dragging = false, startX = 0, startW = 0;

  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX;
    startW   = panelLeft.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const nw = Math.min(Math.max(startW + e.clientX - startX, 400), window.innerWidth - 220);
    panelLeft.style.width = nw + 'px';
    fitImage();
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
  });
}

// ── Vertical splitter: image ↕ categories ─────────────────
function initResizeV() {
  const handle  = document.getElementById('resizeHandleV');
  const catArea = document.getElementById('catArea');
  let dragging = false, startY = 0, startH = 0;

  handle.addEventListener('mousedown', e => {
    dragging = true; startY = e.clientY;
    startH   = catArea.getBoundingClientRect().height;
    handle.classList.add('dragging');
    document.body.style.cursor = 'row-resize';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newH = Math.min(Math.max(startH + (startY - e.clientY), 70), 400);
    catArea.style.height = newH + 'px';
    fitImage();
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
  });
}
