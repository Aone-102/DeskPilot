// Global App State
let state = {
  tasks: [],
  taskFilter: 'all',
  settings: {},
  systemStatus: {},
  notesTimer: null,
  pendingScan: { files: [], total_count: 0, total_size: 0 },
  sharedClips: [],
  noteCandidateLines: [],
  activeTab: 'tasks',
  isMobile: false,
  deviceToken: localStorage.getItem('deskpilot_device_token') || ''
};

// Check if running on mobile
function checkMobile() {
  state.isMobile = window.innerWidth <= 720 || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}
window.addEventListener('resize', checkMobile);
checkMobile();

// Formatting helpers
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  toast.innerText = message;
  
  if (type === 'success') {
    toast.className = 'fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-2xl text-sm font-medium bg-emerald-600 text-white';
  } else if (type === 'error') {
    toast.className = 'fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-2xl text-sm font-medium bg-rose-600 text-white';
  } else {
    toast.className = 'fixed bottom-6 right-6 z-50 transform translate-y-0 opacity-100 transition-all duration-300 pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-2xl text-sm font-medium bg-indigo-600 text-white';
  }

  setTimeout(() => {
    toast.className = 'fixed bottom-6 right-6 z-50 transform translate-y-12 opacity-0 transition-all duration-300 pointer-events-none flex items-center gap-2 px-4 py-3 rounded-xl shadow-2xl text-sm font-medium';
  }, 2800);
}

// Custom authenticated fetch wrapper
async function apiFetch(url, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.deviceToken) {
    headers['X-DeskPilot-Device-Token'] = state.deviceToken;
  }
  return fetch(url, { ...options, headers });
}

// Clock updater
function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('ko-KR', { hour12: false });
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  const dateStr = `${now.getFullYear()}. ${now.getMonth() + 1}. ${now.getDate()}. (${days[now.getDay()]})`;

  const clockEl = document.getElementById('liveClock');
  const dateEl = document.getElementById('liveDate');
  if (clockEl) clockEl.innerText = timeStr;
  if (dateEl) dateEl.innerText = dateStr;
}
setInterval(updateClock, 1000);
updateClock();

// Tab Switcher
function switchTab(tabId) {
  state.activeTab = tabId;
  
  // Desktop tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active-tab', 'border-indigo-500', 'text-indigo-400');
    btn.classList.add('border-transparent', 'text-slate-400');
  });
  const activeBtn = document.getElementById(`tabBtn-${tabId}`);
  if (activeBtn) {
    activeBtn.classList.add('active-tab', 'border-indigo-500', 'text-indigo-400');
    activeBtn.classList.remove('border-transparent', 'text-slate-400');
  }

  // Mobile bottom nav buttons
  ['tasks', 'share', 'screen', 'organize', 'settings'].forEach(id => {
    const mBtn = document.getElementById(`mobileNav-${id}`);
    if (mBtn) {
      if (id === tabId) {
        mBtn.className = 'flex flex-col items-center gap-1 text-indigo-400 font-medium';
      } else {
        mBtn.className = 'flex flex-col items-center gap-1 text-slate-400 hover:text-slate-200';
      }
    }
  });

  // Switch content
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.add('hidden');
  });
  const activeTab = document.getElementById(`tab-${tabId}`);
  if (activeTab) {
    activeTab.classList.remove('hidden');
  }

  if (tabId === 'organize') {
    fetchScanFiles();
    fetchHistory();
  } else if (tabId === 'share') {
    fetchSharedFiles();
    fetchSharedClips();
  } else if (tabId === 'settings') {
    fetchSettings();
  } else if (tabId === 'screen') {
    refreshScreenShot();
    fetchActiveWindows();
    if (state.screenLiveActive) {
      runAdaptiveScreenLiveLoop();
    }
  }
}

// --- Task API & Auto-sort (PRD 5.3 & 7장) ---
async function fetchTasks(silent = false) {
  try {
    const res = await apiFetch('/api/tasks');
    const data = await res.json();
    state.tasks = data.tasks || [];
    renderTasks();
    if (!silent && data.carried_count && data.carried_count > 0) {
      showToast(`${data.carried_count}개의 어제 미완료 할 일이 오늘로 자동 이월되었습니다!`, 'info');
    }
  } catch (err) {
    console.error('fetchTasks error:', err);
  }
}

async function addTask(e) {
  e.preventDefault();
  const input = document.getElementById('taskInput');
  const priority = document.getElementById('taskPriority').value;
  const dueDate = document.getElementById('taskDueDate').value || new Date().toISOString().split('T')[0];
  const estimateMin = parseInt(document.getElementById('taskEstimate').value || '30', 10);
  const title = input.value.trim();
  if (!title) return;

  try {
    const res = await apiFetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ title, priority, dueDate, estimateMin })
    });
    const data = await res.json();
    if (data.success) {
      input.value = '';
      fetchTasks();
      fetchStatus();
      showToast('할 일이 등록되었습니다.', 'success');
    }
  } catch (err) {
    showToast('할 일 추가 실패', 'error');
  }
}

async function toggleTask(id, currentDone) {
  try {
    await apiFetch(`/api/tasks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ done: !currentDone })
    });
    fetchTasks();
    fetchStatus();
  } catch (err) {
    console.error('toggleTask error:', err);
  }
}

async function deleteTask(id) {
  try {
    await apiFetch(`/api/tasks/${id}`, { method: 'DELETE' });
    fetchTasks();
    fetchStatus();
    showToast('할 일이 삭제되었습니다.');
  } catch (err) {
    showToast('삭제 실패', 'error');
  }
}

async function carryOverTasks() {
  try {
    const res = await apiFetch('/api/tasks/carryover', { method: 'POST' });
    const data = await res.json();
    if (data.carried_count > 0) {
      showToast(`${data.carried_count}개의 미완료 할 일을 오늘로 이월했습니다!`, 'success');
      fetchTasks();
      fetchStatus();
    } else {
      showToast('이월할 이전 작업이 없습니다.');
    }
  } catch (err) {
    showToast('이월 처리 중 오류 발생', 'error');
  }
}

function setTaskFilter(filter) {
  state.taskFilter = filter;
  ['all', 'active', 'done'].forEach(f => {
    const btn = document.getElementById(`filter-${f}`);
    if (btn) {
      btn.className = (f === filter)
        ? 'px-2.5 py-1 rounded-lg bg-indigo-500/20 text-indigo-400 font-medium'
        : 'px-2.5 py-1 rounded-lg text-slate-400 hover:text-slate-200';
    }
  });
  renderTasks();
}

function renderTasks() {
  const container = document.getElementById('tasksList');
  let tasks = [...state.tasks];

  // Calculate today's stats (PRD D6)
  const todayStr = new Date().toISOString().split('T')[0];
  const todayTasks = tasks.filter(t => t.date === todayStr);
  const doneToday = todayTasks.filter(t => t.done).length;
  const totalToday = todayTasks.length;
  const percent = totalToday > 0 ? Math.round((doneToday / totalToday) * 100) : 0;
  
  // Total estimate minutes remaining
  const remainingMin = todayTasks.filter(t => !t.done).reduce((acc, t) => acc + (t.estimateMin || 30), 0);

  // Update Progress
  document.getElementById('progressBar').style.width = `${percent}%`;
  document.getElementById('progressPercent').innerText = `${percent}%`;
  document.getElementById('progressFraction').innerText = `${doneToday} / ${totalToday} 완료`;
  document.getElementById('progressStatusText').innerText =
    totalToday > 0 ? `오늘 할 일 ${totalToday}개 중 ${doneToday}개 완료 · 남은 예상 시간 ${remainingMin}분` : '오늘 해야 할 일을 등록해 보세요.';

  // Badges
  const activeCount = tasks.filter(t => !t.done).length;
  document.getElementById('tabTaskCount').innerText = activeCount;

  // Filter
  if (state.taskFilter === 'active') {
    tasks = tasks.filter(t => !t.done);
  } else if (state.taskFilter === 'done') {
    tasks = tasks.filter(t => t.done);
  }

  if (tasks.length === 0) {
    container.innerHTML = `
      <div class="text-center py-12 text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-700/40">
        <i data-lucide="check-circle-2" class="w-8 h-8 mx-auto mb-2 opacity-40 text-emerald-400"></i>
        <p class="text-xs">할 일 목록이 비어있습니다.</p>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = tasks.map(t => {
    const isDone = t.done;
    const priBadge = (t.priority === 'urgent')
      ? '<span class="text-[10px] px-2 py-0.5 rounded badge-priority-urgent font-bold">긴급</span>'
      : (t.priority === 'high')
      ? '<span class="text-[10px] px-2 py-0.5 rounded badge-priority-high font-bold">높음</span>'
      : (t.priority === 'low')
      ? '<span class="text-[10px] px-2 py-0.5 rounded badge-priority-low font-medium">낮음</span>'
      : '<span class="text-[10px] px-2 py-0.5 rounded badge-priority-normal font-medium">보통</span>';

    const carriedBadge = (t.carriedCount && t.carriedCount > 0)
      ? `<span class="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-semibold border border-amber-500/30">↻ 이월 ${t.carriedCount}</span>`
      : '';

    const dueStr = t.dueDate ? `📅 ${t.dueDate}` : '';
    const estStr = t.estimateMin ? `⏱️ ${t.estimateMin}분` : '';

    return `
      <div class="task-item bg-slate-800/80 border border-slate-700/60 rounded-xl px-4 py-3 flex items-center justify-between gap-3 ${isDone ? 'opacity-60 bg-slate-900/40' : ''}">
        <div class="flex items-center gap-3 flex-1 min-w-0">
          <button onclick="toggleTask('${t.id}', ${isDone})" class="w-5 h-5 rounded-md border flex items-center justify-center transition-colors shrink-0 ${isDone ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-600 hover:border-indigo-400'}">
            ${isDone ? '<i data-lucide="check" class="w-3.5 h-3.5"></i>' : ''}
          </button>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-slate-100 truncate ${isDone ? 'line-through text-slate-500' : ''}">${escapeHtml(t.title || t.text)}</div>
            <div class="flex flex-wrap items-center gap-2 mt-1">
              ${priBadge}
              ${carriedBadge}
              ${dueStr ? `<span class="text-[11px] text-slate-400">${dueStr}</span>` : ''}
              ${estStr ? `<span class="text-[11px] text-slate-500">${estStr}</span>` : ''}
            </div>
          </div>
        </div>
        <button onclick="deleteTask('${t.id}')" class="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg transition-colors shrink-0">
          <i data-lucide="trash-2" class="w-4 h-4"></i>
        </button>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

function escapeHtml(text) {
  if (!text) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.replace(/[&<>"']/g, m => map[m]);
}

// --- Scratchpad Notes API ---
async function fetchNotes(force = false) {
  const notesEl = document.getElementById('notesArea');
  if (!notesEl) return;
  // If user is focused on textarea, do not overwrite while typing!
  if (!force && document.activeElement === notesEl) return;
  try {
    const res = await apiFetch('/api/notes');
    const data = await res.json();
    if (!force && document.activeElement === notesEl) return;
    if (notesEl.value !== (data.content || '')) {
      notesEl.value = data.content || '';
    }
  } catch (err) {
    console.error('fetchNotes error:', err);
  }
}

function saveNotesDebounced() {
  clearTimeout(state.notesTimer);
  document.getElementById('notesStatus').innerText = '저장 중...';
  state.notesTimer = setTimeout(async () => {
    const content = document.getElementById('notesArea').value;
    try {
      await apiFetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ content })
      });
      document.getElementById('notesStatus').innerText = '자동 저장됨';
    } catch (err) {
      document.getElementById('notesStatus').innerText = '저장 실패';
    }
  }, 600);
}

function copyNotes() {
  const content = document.getElementById('notesArea').value;
  if (!content) return;
  navigator.clipboard.writeText(content).then(() => {
    showToast('메모가 클립보드에 복사되었습니다!', 'success');
  });
}

// --- Memo to Task Conversion ---
function openNoteToTaskModal() {
  const content = (document.getElementById('notesArea') ? document.getElementById('notesArea').value : '') || '';
  const lines = content.split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0);

  if (lines.length === 0) {
    showToast('메모장에 등록할 내용이 없습니다.', 'info');
    return;
  }

  state.noteCandidateLines = lines;
  const container = document.getElementById('noteToTaskListContainer');
  if (container) {
    container.innerHTML = lines.map((line, idx) => {
      const cleanTitle = line.replace(/^([*\-+•]\s*(\[[ xX]?\]\s*)?|\d+[\.\)]\s*)/, '').trim() || line;
      return `
        <label class="flex items-start gap-2.5 p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 hover:border-slate-500 cursor-pointer transition-colors">
          <input type="checkbox" id="noteTaskCheck_${idx}" checked class="mt-0.5 w-4 h-4 text-indigo-600 rounded bg-slate-800 border-slate-700 focus:ring-indigo-500 shrink-0">
          <span class="text-xs text-slate-200 select-none flex-1 break-all">${escapeHtml(cleanTitle)}</span>
        </label>
      `;
    }).join('');
  }

  const modal = document.getElementById('noteToTaskModal');
  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeNoteToTaskModal() {
  const modal = document.getElementById('noteToTaskModal');
  if (modal) modal.classList.add('hidden');
}

async function submitNoteToTasks() {
  const lines = state.noteCandidateLines || [];
  const selectedTitles = [];
  const selectedRawLines = [];

  lines.forEach((line, idx) => {
    const cb = document.getElementById(`noteTaskCheck_${idx}`);
    if (cb && cb.checked) {
      const cleanTitle = line.replace(/^([*\-+•]\s*(\[[ xX]?\]\s*)?|\d+[\.\)]\s*)/, '').trim() || line;
      selectedTitles.push(cleanTitle);
      selectedRawLines.push(line);
    }
  });

  if (selectedTitles.length === 0) {
    showToast('등록할 항목을 선택해주세요.', 'error');
    return;
  }

  const priority = (document.getElementById('noteToTaskPriority') ? document.getElementById('noteToTaskPriority').value : 'normal') || 'normal';
  const shouldDelete = document.getElementById('noteToTaskDeleteFromMemo') ? document.getElementById('noteToTaskDeleteFromMemo').checked : true;
  const todayStr = new Date().toISOString().split('T')[0];

  const submitBtn = document.getElementById('btnSubmitNoteToTasks');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = '등록 중...';
  }

  try {
    const res = await apiFetch('/api/tasks/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        titles: selectedTitles,
        priority: priority,
        dueDate: todayStr,
        estimateMin: 30
      })
    });
    const data = await res.json();
    if (data.success) {
      if (shouldDelete) {
        const notesArea = document.getElementById('notesArea');
        if (notesArea) {
          const currentLines = notesArea.value.split('\n');
          const remaining = currentLines.filter(l => !selectedRawLines.includes(l.trim()));
          notesArea.value = remaining.join('\n');
          saveNotesDebounced();
        }
      }

      await fetchTasks();
      closeNoteToTaskModal();
      showToast(`${selectedTitles.length}개의 할 일이 추가되었습니다!`, 'success');
    } else {
      showToast(data.error || '할 일 등록 실패', 'error');
    }
  } catch (err) {
    showToast('할 일 등록 중 오류가 발생했습니다.', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<i data-lucide="check" class="w-4 h-4"></i><span>할 일 등록하기</span>';
      lucide.createIcons();
    }
  }
}

// --- File Organizer API & Safety (PRD B2, B4, B5) ---
async function fetchScanFiles() {
  try {
    const res = await apiFetch('/api/organize/scan');
    const data = await res.json();
    state.pendingScan = data;

    const count = data.total_count || 0;
    const size = formatBytes(data.total_size || 0);

    document.getElementById('quickBadgeCount').innerText = count;
    document.getElementById('tabOrganizeCount').innerText = count;
    document.getElementById('statPendingCount').innerText = count;
    document.getElementById('statPendingSize').innerText = `(${size})`;

    renderScanTable(data.files || []);
  } catch (err) {
    console.error('fetchScanFiles error:', err);
  }
}

function renderScanTable(files) {
  const tbody = document.getElementById('scanTableBody');
  if (files.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-12 text-center text-slate-500">
          <i data-lucide="sparkles" class="w-7 h-7 mx-auto mb-1.5 text-emerald-400 opacity-60"></i>
          정리할 파일이 없습니다. 바탕화면과 다운로드 폴더가 깨끗합니다!
        </td>
      </tr>`;
    lucide.createIcons();
    return;
  }

  tbody.innerHTML = files.map((f, idx) => {
    const catColors = {
      '문서': 'bg-blue-500/10 text-blue-400 border-blue-500/20',
      '이미지': 'bg-pink-500/10 text-pink-400 border-pink-500/20',
      '압축파일': 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      '설치파일': 'bg-purple-500/10 text-purple-400 border-purple-500/20',
      '미디어': 'bg-rose-500/10 text-rose-400 border-rose-500/20',
      '코드': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      '기타': 'bg-slate-700 text-slate-400 border-slate-600'
    };
    const badgeCls = catColors[f.category] || catColors['기타'];

    return `
      <tr class="hover:bg-slate-800/40 transition-colors">
        <td class="py-2.5 px-4 text-center">
          <input type="checkbox" ${f.selected !== false ? 'checked' : ''} onchange="toggleFileSelection(${idx}, this.checked)" class="rounded bg-slate-900 border-slate-700 text-indigo-600">
        </td>
        <td class="py-2.5 px-4 font-medium text-slate-200 truncate max-w-xs" title="${escapeHtml(f.name)}">
          ${escapeHtml(f.name)}
        </td>
        <td class="py-2.5 px-4 text-slate-400">${f.folder}</td>
        <td class="py-2.5 px-4">
          <span class="inline-block px-2 py-0.5 rounded text-[11px] border ${badgeCls}">
            ${f.destination || f.category}
          </span>
        </td>
        <td class="py-2.5 px-4 text-right text-slate-400 font-mono">${formatBytes(f.size)}</td>
        <td class="py-2.5 px-4 text-center">
          <button onclick="excludeFileFromScan(${idx})" title="이번 정리에서 제외" class="text-slate-500 hover:text-amber-400 p-1">
            <i data-lucide="eye-off" class="w-3.5 h-3.5"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');

  lucide.createIcons();
}

function toggleSelectAllFiles(checked) {
  if (state.pendingScan.files) {
    state.pendingScan.files.forEach(f => f.selected = checked);
    renderScanTable(state.pendingScan.files);
  }
}

function toggleFileSelection(idx, checked) {
  if (state.pendingScan.files && state.pendingScan.files[idx]) {
    state.pendingScan.files[idx].selected = checked;
  }
}

function excludeFileFromScan(idx) {
  if (state.pendingScan.files && state.pendingScan.files[idx]) {
    state.pendingScan.files.splice(idx, 1);
    state.pendingScan.total_count = state.pendingScan.files.length;
    renderScanTable(state.pendingScan.files);
    showToast('해당 파일이 정리 대상에서 제외되었습니다.');
  }
}

async function runOrganize() {
  const selected = (state.pendingScan.files || []).filter(f => f.selected !== false);
  if (selected.length === 0) {
    showToast('정리할 선택된 파일이 없습니다.', 'info');
    return;
  }

  try {
    showToast('파일 정리를 시작합니다...', 'info');
    const res = await apiFetch('/api/organize/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: selected })
    });
    const data = await res.json();
    if (data.success) {
      if (data.moved_count > 0) {
        showToast(`${data.moved_count}개의 파일이 안전하게 정리되었습니다!`, 'success');
      } else {
        showToast('정리된 파일이 없습니다.');
      }
      fetchScanFiles();
      fetchHistory();
    }
  } catch (err) {
    showToast('파일 정리 중 오류 발생', 'error');
  }
}

async function undoOrganize(batchId = null) {
  try {
    const res = await apiFetch('/api/organize/undo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`${data.reverted_count}개 파일이 원래 위치로 완벽히 복구되었습니다!`, 'success');
      fetchScanFiles();
      fetchHistory();
    } else {
      showToast(data.message || '되돌릴 내역이 없습니다.', 'error');
    }
  } catch (err) {
    showToast('되돌리기 실패', 'error');
  }
}

async function fetchHistory() {
  try {
    const res = await apiFetch('/api/organize/history');
    const data = await res.json();
    const list = document.getElementById('historyList');
    const history = data.history || [];

    if (history.length === 0) {
      list.innerHTML = '<div class="text-slate-500 py-4 text-center">정리 이력이 없습니다.</div>';
      return;
    }

    list.innerHTML = history.slice(0, 8).map(h => {
      const isUndone = !!h.undoneAt;
      return `
        <div class="p-3 rounded-xl bg-slate-900/50 border border-slate-700/50 flex items-center justify-between gap-3 ${isUndone ? 'opacity-50' : ''}">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg ${isUndone ? 'bg-slate-700 text-slate-400' : 'bg-emerald-500/10 text-emerald-400'} flex items-center justify-center shrink-0">
              <i data-lucide="${isUndone ? 'rotate-ccw' : 'check'}" class="w-4 h-4"></i>
            </div>
            <div>
              <div class="font-medium text-slate-200">${h.count}개 파일 정리 완료 ${isUndone ? '<span class="text-amber-400 text-[10px] ml-1">(복구됨)</span>' : ''}</div>
              <div class="text-slate-500 text-[11px]">${h.startedAt} &middot; 트리거: ${h.trigger || '수동'}</div>
            </div>
          </div>
          <div>
            ${!isUndone && h.count > 0 ? `
              <button onclick="undoOrganize('${h.batchId}')" class="bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1">
                <i data-lucide="undo-2" class="w-3.5 h-3.5"></i>
                <span>되돌리기</span>
              </button>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');

    lucide.createIcons();
  } catch (err) {
    console.error('fetchHistory error:', err);
  }
}

async function openOrganizedFolder() {
  const orgDir = state.settings.organizedDir || state.settings.organized_dir;
  await apiFetch('/api/system/open_folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: orgDir })
  });
}

async function openLogsFolder() {
  await apiFetch('/api/system/open_logs', { method: 'POST' });
}

// --- Smartphone Pairing Flow & Tunnel ---
let phonePairPollTimer = null;
let lastKnownDeviceCount = 0;

async function openPhoneModal() {
  window.__phoneModalOpen = true;
  try {
    const res = await apiFetch('/api/phone/info');
    const data = await res.json();
    document.getElementById('pairingUrlText').innerText = data.pairing_url;
    document.getElementById('pairingCodeText').innerText = data.pairing_code;
    
    // Fetch live vector SVG QR code
    document.getElementById('qrCodeContainer').innerHTML = `<img src="/api/phone/qr.svg?t=${Date.now()}" alt="QR" class="w-48 h-48">`;

    lastKnownDeviceCount = (data.devices || []).length;
    const statusLiveEl = document.getElementById('pairingStatusLive');
    if (statusLiveEl) {
      statusLiveEl.classList.add('hidden');
    }

    // Tunnel switch UI
    const t = data.tunnel || {};
    window.__tunnelRunning = !!(t.running && t.url);
    const tunnelBtn = document.getElementById('tunnelToggleBtn');
    const tunnelDot = document.getElementById('tunnelToggleDot');
    if (tunnelBtn && tunnelDot) {
      if (window.__tunnelRunning) {
        tunnelBtn.className = 'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-emerald-600';
        tunnelDot.className = 'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 translate-x-4';
      } else {
        tunnelBtn.className = 'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-slate-700';
        tunnelDot.className = 'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 translate-x-0';
      }
    }

    document.getElementById('phoneModal').classList.remove('hidden');

    // Start live auto-detection polling while modal is open
    if (phonePairPollTimer) clearInterval(phonePairPollTimer);
    phonePairPollTimer = setInterval(async () => {
      try {
        const pollRes = await apiFetch('/api/phone/info');
        const pollData = await pollRes.json();
        const curDevices = pollData.devices || [];
        if (curDevices.length > lastKnownDeviceCount) {
          const newDev = curDevices[curDevices.length - 1];
          lastKnownDeviceCount = curDevices.length;
          showToast(`✨ 새 스마트폰(${newDev.name || '기기'}) 연동 완료!`, 'success');
          
          if (statusLiveEl) {
            statusLiveEl.classList.remove('hidden');
            const txt = document.getElementById('pairingStatusLiveText');
            if (txt) txt.innerText = `✨ '${newDev.name || '스마트폰'}' 연동 성공!`;
          }
          fetchSettings();
          fetchStatus();
        }
      } catch (err) {
        // ignore polling errors
      }
    }, 2000);

  } catch (err) {
    showToast('스마트폰 연동 정보 로드 실패', 'error');
  }
}

async function toggleCloudflareTunnel() {
  const isCurrentlyOn = window.__tunnelRunning;
  showToast(isCurrentlyOn ? '외부 접속 터널을 종료합니다...' : '외부 접속용 공용 보안 터널을 생성 중입니다 (약 3초)...', 'info');
  try {
    await apiFetch('/api/tunnel/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable: !isCurrentlyOn })
    });
    setTimeout(() => {
      openPhoneModal();
      showToast(!isCurrentlyOn ? '외부 네트워크(LTE/5G) 접속 활성화 완료!' : '외부 접속 터널이 꺼졌습니다.', 'success');
    }, 2800);
  } catch (err) {
    showToast('터널 설정 실패', 'error');
  }
}

function closePhoneModal() {
  window.__phoneModalOpen = false;
  if (phonePairPollTimer) {
    clearInterval(phonePairPollTimer);
    phonePairPollTimer = null;
  }
  document.getElementById('phoneModal').classList.add('hidden');
  fetchSettings();
  fetchStatus();
}

// Mobile Side: Check query parameter `?pair=XXXXXX`
async function checkMobilePairingPrompt() {
  const params = new URLSearchParams(window.location.search);
  const pairCode = params.get('pair');
  
  if (pairCode) {
    // If device is already paired with token, ignore or verify
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      document.getElementById('confirmHostName').innerText = data.hostname || '사용자의 PC';
      document.getElementById('confirmIpAddress').innerText = `IP: ${data.lan_ip}`;
      document.getElementById('phoneConfirmModal').classList.remove('hidden');
      window.__activePairCode = pairCode;
    } catch (err) {
      console.error(err);
    }
  }
}

async function confirmPairing() {
  const pairCode = window.__activePairCode;
  if (!pairCode) return;

  const deviceName = /iPhone/i.test(navigator.userAgent) ? 'iPhone'
    : /Android/i.test(navigator.userAgent) ? 'Galaxy'
    : '스마트폰';

  try {
    const res = await fetch('/api/phone/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: pairCode, device_name: deviceName })
    });
    const data = await res.json();
    if (data.success) {
      state.deviceToken = data.token;
      localStorage.setItem('deskpilot_device_token', data.token);
      document.getElementById('phoneConfirmModal').classList.add('hidden');
      // Clean query parameter from URL
      window.history.replaceState({}, document.title, window.location.pathname);
      showToast('🎉 컴퓨터와 연동되었습니다! 이제 자유롭게 이용하세요.', 'success');
      fetchTasks();
      fetchNotes();
      fetchStatus();
    } else {
      showToast(data.message || '연동 실패', 'error');
    }
  } catch (err) {
    showToast('연동 승인 중 오류 발생', 'error');
  }
}

function cancelPairing() {
  document.getElementById('phoneConfirmModal').classList.add('hidden');
  window.history.replaceState({}, document.title, window.location.pathname);
}

function openPhoneDisconnectModal() {
  if (confirm('현재 스마트폰과 컴퓨터의 연동을 해제하시겠습니까?')) {
    localStorage.removeItem('deskpilot_device_token');
    state.deviceToken = '';
    showToast('연동이 해제되었습니다.');
    setTimeout(() => window.location.reload(), 800);
  }
}

async function deletePhoneDevice(devId) {
  if (!confirm('이 스마트폰의 접근 권한을 삭제하시겠습니까?')) return;
  try {
    const res = await apiFetch('/api/phone/devices/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: devId })
    });
    const data = await res.json();
    if (data.success) {
      showToast('기기 연동이 해제되었습니다.', 'success');
      fetchSettings();
      fetchStatus();
    } else {
      showToast('기기 연동 해제 실패', 'error');
    }
  } catch (err) {
    showToast('해제 실패', 'error');
  }
}

// --- Settings & Status API ---
async function fetchStatus() {
  try {
    const res = await apiFetch('/api/status');
    const data = await res.json();
    state.systemStatus = data;

    // Badges & Labels
    const hostEl = document.getElementById('hostnameBadge');
    if (hostEl) hostEl.innerText = data.hostname || 'PC';
    const mobileHostEl = document.getElementById('mobileHostName');
    if (mobileHostEl) mobileHostEl.innerText = `${data.hostname} 연동됨`;
    const quickCardHost = document.getElementById('quickCardHostName');
    if (quickCardHost) quickCardHost.innerText = data.hostname || '내 컴퓨터';
    const settingsHostDesc = document.getElementById('settingsHostDesc');
    if (settingsHostDesc) settingsHostDesc.innerText = `${data.hostname || '내 컴퓨터'}의 실시간 화면과 작업 현황을 확인합니다.`;

    const phoneCount = data.phone_connected_count || 0;
    const phoneBadge = document.getElementById('headerPhoneBadge');
    if (phoneBadge) phoneBadge.innerText = `${phoneCount}대`;

    // Onboarding Wizard check
    if (data.first_run_done === false) {
      document.getElementById('wizardModal').classList.remove('hidden');
    }

    updateStartupUI(data.startup_enabled);
    fetchSettings();
  } catch (err) {
    console.error('fetchStatus error:', err);
  }
}

async function fetchSettings() {
  try {
    const res = await apiFetch('/api/settings');
    const cfg = await res.json();
    state.settings = cfg;

    const autoCfg = cfg.automation || {};
    const cleanEl = document.getElementById('cfgCleanOnStartup');
    if (cleanEl) cleanEl.checked = !!autoCfg.cleanOnStartup;
    const periodicEl = document.getElementById('cfgPeriodic');
    if (periodicEl) periodicEl.checked = !!(autoCfg.periodic && autoCfg.periodic.enabled);
    const intervalEl = document.getElementById('cfgInterval');
    if (intervalEl) intervalEl.value = (autoCfg.periodic && autoCfg.periodic.minutes) || 30;
    const orgDirEl = document.getElementById('cfgOrganizedDir');
    if (orgDirEl) orgDirEl.value = cfg.organizedDir || cfg.organized_dir || '';

    // Watch folders
    const wfList = cfg.watchFolders || cfg.watch_folders || [];
    const wfContainer = document.getElementById('watchFoldersContainer');
    if (wfContainer) {
      wfContainer.innerHTML = wfList.map((wf, idx) => `
        <div class="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40 border border-slate-700/40">
          <div>
            <span class="font-medium text-slate-200">${escapeHtml(wf.name)}</span>
            <span class="text-slate-500 ml-2 font-mono text-[11px]">${escapeHtml(wf.path)}</span>
          </div>
          <input type="checkbox" ${wf.enabled ? 'checked' : ''} onchange="toggleWatchFolder(${idx})" class="w-4 h-4 text-indigo-600 rounded bg-slate-900 border-slate-700">
        </div>
      `).join('');
    }

    // Connected devices list
    const devices = (cfg.phone && cfg.phone.devices) || [];
    const countBadge = document.getElementById('devicesCountLabel');
    if (countBadge) countBadge.innerText = `${devices.length}대`;
    const phoneBadge = document.getElementById('headerPhoneBadge');
    if (phoneBadge) phoneBadge.innerText = `${devices.length}대`;

    const devContainer = document.getElementById('connectedDevicesList');
    if (devContainer) {
      if (devices.length === 0) {
        devContainer.innerHTML = '<div class="text-slate-500 py-3 text-center bg-slate-900/30 rounded-xl border border-dashed border-slate-700/60">연동된 스마트폰이 없습니다.<br><span class="text-[11px] text-slate-500">위 [QR 코드 열기]를 눌러 스마트폰을 연동해보세요.</span></div>';
      } else {
        devContainer.innerHTML = devices.map(d => `
          <div class="flex items-center justify-between p-3 rounded-xl bg-slate-900/40 border border-slate-700/40 hover:border-slate-600/60 transition-colors">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0 border border-emerald-500/20">
                <i data-lucide="smartphone" class="w-4 h-4"></i>
              </div>
              <div>
                <div class="font-semibold text-slate-200 flex items-center gap-2">
                  <span>${escapeHtml(d.name || '스마트폰')}</span>
                  <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">연동됨</span>
                </div>
                <div class="text-slate-400 text-[11px] mt-0.5">
                  등록일: ${escapeHtml(d.createdAt || d.created_at || '알 수 없음')}
                  ${d.lastUsedAt ? `<span class="ml-2 text-slate-500">(최근 사용: ${escapeHtml(d.lastUsedAt)})</span>` : ''}
                </div>
              </div>
            </div>
            <button onclick="deletePhoneDevice('${d.id}')" class="text-rose-400 hover:text-rose-300 text-xs px-2.5 py-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 active:scale-95 transition-all">
              연결 해제
            </button>
          </div>
        `).join('');
        lucide.createIcons();
      }
    }
  } catch (err) {
    console.error('fetchSettings error:', err);
  }
}

async function saveSettings() {
  const cleanOnStartup = document.getElementById('cfgCleanOnStartup').checked;
  const periodic = document.getElementById('cfgPeriodic').checked;
  const interval = parseInt(document.getElementById('cfgInterval').value, 10);

  const autoCfg = state.settings.automation || {};
  autoCfg.cleanOnStartup = cleanOnStartup;
  autoCfg.periodic = { enabled: periodic, minutes: interval };

  try {
    await apiFetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ automation: autoCfg })
    });
    showToast('설정이 저장되었습니다.');
  } catch (err) {
    showToast('설정 저장 실패', 'error');
  }
}

async function toggleStartup() {
  const current = state.systemStatus.startup_enabled;
  try {
    const res = await apiFetch('/api/settings/startup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable: !current })
    });
    const data = await res.json();
    if (data.success) {
      state.systemStatus.startup_enabled = data.enabled;
      updateStartupUI(data.enabled);
      showToast(data.message, 'success');
    }
  } catch (err) {
    showToast('부팅 자동실행 변경 실패', 'error');
  }
}

function updateStartupUI(enabled) {
  const headerBtn = document.getElementById('headerStartupBtn');
  const headerDot = document.getElementById('headerStartupDot');
  const settingsBtn = document.getElementById('settingsStartupBtn');
  const settingsDot = document.getElementById('settingsStartupDot');

  if (enabled) {
    if (headerBtn) headerBtn.className = 'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-indigo-600';
    if (headerDot) headerDot.className = 'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 translate-x-4';
    if (settingsBtn) settingsBtn.className = 'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-indigo-600';
    if (settingsDot) settingsDot.className = 'inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 translate-x-5';
  } else {
    if (headerBtn) headerBtn.className = 'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-slate-700';
    if (headerDot) headerDot.className = 'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 translate-x-0';
    if (settingsBtn) settingsBtn.className = 'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 bg-slate-700';
    if (settingsDot) settingsDot.className = 'inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 translate-x-0';
  }
}

async function toggleWatchFolder(idx) {
  const wfList = state.settings.watchFolders || state.settings.watch_folders || [];
  if (!wfList[idx]) return;
  wfList[idx].enabled = !wfList[idx].enabled;
  await apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ watchFolders: wfList })
  });
  fetchScanFiles();
}

async function completeWizard() {
  await apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firstRunDone: true })
  });
  document.getElementById('wizardModal').classList.add('hidden');
  showToast('DeskPilot 환영합니다! 안전한 PC 환경을 시작합니다.', 'success');
}

// --- Cross-device File Sharing & Drop (QuickDrop) ---
async function fetchSharedFiles() {
  try {
    const res = await apiFetch('/api/shared/files');
    const data = await res.json();
    const files = data.files || [];

    const countEl = document.getElementById('sharedFilesCountBadge');
    if (countEl) countEl.innerText = `${files.length}개`;
    const tabCountEl = document.getElementById('tabShareCount');
    if (tabCountEl) tabCountEl.innerText = files.length;

    renderSharedFiles(files);
  } catch (err) {
    console.error('fetchSharedFiles error:', err);
  }
}

function renderSharedFiles(files) {
  const container = document.getElementById('sharedFilesList');
  if (!container) return;

  if (files.length === 0) {
    container.innerHTML = `
      <div class="py-12 text-center text-slate-500">
        <i data-lucide="inbox" class="w-8 h-8 mx-auto mb-2 opacity-50"></i>
        <p class="text-xs">공유 및 전송된 파일이 없습니다. 상단 버튼으로 파일을 전송해 보세요.</p>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = files.map(f => {
    const isImage = ['.jpg', '.jpeg', '.png', '.gif', '.webp'].includes(f.ext);
    const iconName = isImage ? 'image' : f.ext === '.pdf' ? 'file-text' : ['.zip', '.rar', '.7z'].includes(f.ext) ? 'archive' : 'file';
    const uploaderBadge = f.uploader === 'PC'
      ? '<span class="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">💻 PC</span>'
      : `<span class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/30">📱 ${escapeHtml(f.uploader)}</span>`;

    return `
      <div class="p-3.5 sm:p-4 hover:bg-slate-800/40 transition-colors flex items-center justify-between gap-3">
        <div class="flex items-center gap-3 flex-1 min-w-0">
          <div class="w-10 h-10 rounded-xl bg-slate-800 text-indigo-400 flex items-center justify-center shrink-0 border border-slate-700/60">
            <i data-lucide="${iconName}" class="w-5 h-5"></i>
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-slate-200 truncate text-sm" title="${escapeHtml(f.name)}">
              ${escapeHtml(f.name)}
            </div>
            <div class="flex flex-wrap items-center gap-2 mt-1">
              ${uploaderBadge}
              <span class="text-slate-400 font-mono text-[11px]">${formatBytes(f.size)}</span>
              <span class="text-slate-500 text-[11px]">${f.timestamp}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-1.5 shrink-0">
          <a href="/api/shared/download/${encodeURIComponent(f.name)}" download="${escapeHtml(f.name)}" class="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1 shadow-sm active:scale-95 transition-all">
            <i data-lucide="download" class="w-3.5 h-3.5"></i>
            <span>받기</span>
          </a>
          <button onclick="deleteSharedFile('${f.id}')" title="삭제" class="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg transition-colors">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

async function handleSharedFileSelect(fileList) {
  if (!fileList || fileList.length === 0) return;
  const files = Array.from(fileList);

  const progContainer = document.getElementById('uploadProgressContainer');
  const progBar = document.getElementById('uploadProgressBar');
  const progText = document.getElementById('uploadPercent');
  const progName = document.getElementById('uploadFileName');

  if (progContainer) progContainer.classList.remove('hidden');

  const uploaderName = state.isMobile 
    ? (navigator.userAgent.includes('iPhone') ? 'iPhone' : 'Galaxy')
    : 'PC';

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (progName) progName.innerText = `전송 중 (${i+1}/${files.length}): ${file.name}`;
    if (progBar) progBar.style.width = '40%';
    if (progText) progText.innerText = '전송 중...';

    try {
      const res = await apiFetch('/api/shared/upload', {
        method: 'POST',
        headers: {
          'X-File-Name': encodeURIComponent(file.name),
          'X-Uploader': encodeURIComponent(uploaderName)
        },
        body: file
      });
      const data = await res.json();
      if (data.success) {
        if (progBar) progBar.style.width = '100%';
        if (progText) progText.innerText = '완료!';
      }
    } catch (err) {
      showToast(`${file.name} 전송 실패`, 'error');
    }
  }

  setTimeout(() => {
    if (progContainer) progContainer.classList.add('hidden');
    fetchSharedFiles();
    showToast(`${files.length}개 파일 전송 완료!`, 'success');
  }, 400);
}

async function openSharedFolder() {
  await apiFetch('/api/shared/open_folder', { method: 'POST' });
}

async function deleteSharedFile(fileId) {
  if (!confirm('이 공유 파일을 삭제하시겠습니까?')) return;
  try {
    await apiFetch(`/api/shared/files/${fileId}`, { method: 'DELETE' });
    fetchSharedFiles();
    showToast('공유 파일이 삭제되었습니다.');
  } catch (err) {
    showToast('삭제 실패', 'error');
  }
}

// --- Clipboard & Link Instant Transfer (QuickDrop Extension) ---
async function fetchSharedClips() {
  try {
    const res = await apiFetch('/api/shared/clips');
    const data = await res.json();
    state.sharedClips = data.clips || [];
    renderSharedClips(state.sharedClips);
  } catch (err) {
    console.error('fetchSharedClips error:', err);
  }
}

function renderSharedClips(clips) {
  const container = document.getElementById('sharedClipsContainer');
  if (!container) return;

  if (!clips || clips.length === 0) {
    container.innerHTML = `
      <div class="text-center py-5 border border-dashed border-slate-700/60 rounded-xl text-slate-500 text-xs">
        <i data-lucide="inbox" class="w-6 h-6 mx-auto mb-1 opacity-50"></i>
        <span>공유된 텍스트나 링크가 없습니다. 위 입력창에 입력하고 전송해보세요.</span>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  container.innerHTML = clips.map(clip => {
    const isUrl = clip.type === 'url' || /^https?:\/\//i.test(clip.content);
    const uploaderBadge = clip.uploader === 'PC'
      ? '<span class="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">💻 PC</span>'
      : `<span class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/30">📱 ${escapeHtml(clip.uploader || '스마트폰')}</span>`;

    const typeBadge = isUrl
      ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-medium">🔗 링크</span>'
      : '<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-medium">📝 텍스트</span>';

    const contentHtml = isUrl
      ? `<a href="${escapeHtml(clip.content)}" target="_blank" rel="noopener noreferrer" class="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 break-all text-xs font-mono select-text flex items-center gap-1">
          <span>${escapeHtml(clip.content)}</span>
          <i data-lucide="external-link" class="w-3 h-3 inline shrink-0"></i>
         </a>`
      : `<div class="text-xs text-slate-200 select-text whitespace-pre-wrap break-all leading-relaxed">${escapeHtml(clip.content)}</div>`;

    return `
      <div class="p-3 bg-slate-900/60 hover:bg-slate-900/90 border border-slate-700/60 rounded-xl transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div class="flex-1 min-w-0 space-y-1">
          <div class="flex items-center gap-2">
            ${uploaderBadge}
            ${typeBadge}
            <span class="text-slate-500 text-[11px]">${clip.timestamp || ''}</span>
          </div>
          <div class="pt-0.5">
            ${contentHtml}
          </div>
        </div>

        <div class="flex items-center gap-1.5 self-end sm:self-center shrink-0">
          <button onclick="copyClipContent('${clip.id}')" title="클립보드에 복사" class="bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 active:scale-95 transition-all">
            <i data-lucide="copy" class="w-3.5 h-3.5 text-indigo-400"></i>
            <span>복사</span>
          </button>
          ${isUrl ? `
            <a href="${escapeHtml(clip.content)}" target="_blank" rel="noopener noreferrer" class="bg-indigo-600/80 hover:bg-indigo-600 text-white px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 active:scale-95 transition-all">
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
              <span>열기</span>
            </a>
          ` : ''}
          <button onclick="deleteSharedClip('${clip.id}')" title="삭제" class="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg transition-colors">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

async function sendSharedClip() {
  const input = document.getElementById('clipInputText');
  if (!input) return;
  const content = input.value.trim();
  if (!content) {
    showToast('전송할 내용이나 링크를 입력하세요.', 'info');
    return;
  }

  const uploader = state.isMobile 
    ? (navigator.userAgent.includes('iPhone') ? 'iPhone' : 'Galaxy')
    : 'PC';

  try {
    const res = await apiFetch('/api/shared/clips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ content, uploader })
    });
    const data = await res.json();
    if (data.success) {
      input.value = '';
      await fetchSharedClips();
      showToast('클립보드 내용이 전송되었습니다!', 'success');
    } else {
      showToast(data.error || data.message || '전송 실패', 'error');
    }
  } catch (err) {
    showToast('전송 중 오류 발생', 'error');
  }
}

function copyClipContent(clipId) {
  const clip = (state.sharedClips || []).find(c => c.id === clipId);
  if (!clip || !clip.content) return;
  navigator.clipboard.writeText(clip.content).then(() => {
    showToast('클립보드에 복사되었습니다!', 'success');
  }).catch(() => {
    showToast('복사 실패', 'error');
  });
}

async function deleteSharedClip(clipId) {
  try {
    await apiFetch(`/api/shared/clips/${clipId}`, { method: 'DELETE' });
    await fetchSharedClips();
    showToast('공유 항목이 삭제되었습니다.');
  } catch (err) {
    showToast('삭제 실패', 'error');
  }
}

// Drag & drop dropzone support
window.addEventListener('DOMContentLoaded', () => {
  const dropZone = document.getElementById('dropZone');
  if (dropZone) {
    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.add('border-indigo-500', 'bg-indigo-500/10');
      }, false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-indigo-500', 'bg-indigo-500/10');
      }, false);
    });
    dropZone.addEventListener('drop', (e) => {
      if (e.dataTransfer && e.dataTransfer.files) {
        handleSharedFileSelect(e.dataTransfer.files);
      }
    });
  }
});

// --- Remote PC Screen & Active Windows Monitor (Real-time Adaptive Streaming) ---
let lastScreenBlobUrl = null;
let screenLiveLoopRunning = false;

function getAuthQuery() {
  return state.deviceToken ? `&token=${encodeURIComponent(state.deviceToken)}` : '';
}

function changeScreenQuality() {
  const select = document.getElementById('screenQualitySelect');
  if (select) {
    state.screenQuality = select.value || 'fast';
    refreshScreenShot(true);
  }
}

async function refreshScreenShot(silent = false) {
  const spinner = document.getElementById('screenLoadingSpinner');
  if (!silent && spinner) spinner.classList.remove('hidden');

  const btn = document.getElementById('btnRefreshScreen');
  if (!silent && btn) btn.classList.add('opacity-75');

  const qualityMode = state.screenQuality || 'fast';
  const qVal = qualityMode === 'hd' ? 75 : 60;
  const wVal = qualityMode === 'hd' ? 1280 : 960;

  const startTime = performance.now();

  try {
    const url = `/api/screen/shot?t=${Date.now()}&q=${qVal}&w=${wVal}${getAuthQuery()}`;
    const res = await apiFetch(url);
    if (!res.ok) throw new Error('화면 캡처 응답 오류 (' + res.status + ')');

    const width = res.headers.get('X-Screen-Width') || '1920';
    const height = res.headers.get('X-Screen-Height') || '1080';
    const capTime = res.headers.get('X-Captured-At') || new Date().toLocaleTimeString('ko-KR');

    const blob = await res.blob();
    if (lastScreenBlobUrl) {
      URL.revokeObjectURL(lastScreenBlobUrl);
    }
    lastScreenBlobUrl = URL.createObjectURL(blob);

    const img = document.getElementById('pcScreenImage');
    if (img) {
      img.src = lastScreenBlobUrl;
    }

    const modalImg = document.getElementById('modalScreenImage');
    if (modalImg) {
      modalImg.src = lastScreenBlobUrl;
    }

    const badge = document.getElementById('screenResolutionBadge');
    if (badge) badge.innerText = `${width}x${height}`;

    const timeEl = document.getElementById('screenTimestamp');
    if (timeEl) timeEl.innerText = `마지막 갱신: ${capTime}`;

    const modalTime = document.getElementById('modalScreenTime');
    if (modalTime) modalTime.innerText = `(${width}x${height} / ${capTime})`;

    const rtt = Math.round(performance.now() - startTime);
    return { success: true, rtt };

  } catch (err) {
    console.error('refreshScreenShot error:', err);
    if (!silent) {
      showToast('컴퓨터 화면을 불러오지 못했습니다. 연동 상태를 확인해 주세요.', 'error');
    }
    return { success: false, rtt: 0 };
  } finally {
    if (spinner) spinner.classList.add('hidden');
    if (btn) btn.classList.remove('opacity-75');
  }
}

function onScreenImageLoaded() {
  const spinner = document.getElementById('screenLoadingSpinner');
  if (spinner) spinner.classList.add('hidden');
}

function onScreenImageError() {
  const spinner = document.getElementById('screenLoadingSpinner');
  if (spinner) spinner.classList.add('hidden');
}

async function runAdaptiveScreenLiveLoop() {
  if (screenLiveLoopRunning) return;
  screenLiveLoopRunning = true;

  const fpsBadge = document.getElementById('screenFpsBadge');
  const liveBadge = document.getElementById('screenLiveBadge');

  if (liveBadge) liveBadge.classList.remove('hidden');
  if (fpsBadge) fpsBadge.classList.remove('hidden');

  while (state.screenLiveActive && state.activeTab === 'screen' && !document.hidden) {
    const { success, rtt } = await refreshScreenShot(true);
    if (fpsBadge && success) {
      fpsBadge.innerText = `⚡ LIVE (${rtt}ms)`;
    }

    // Adaptive minimal pacing: RTT is naturally rate-limiting; short pause prevents CPU spike
    const pauseMs = (state.screenQuality === 'hd') ? 120 : 60;
    await new Promise(resolve => setTimeout(resolve, pauseMs));
  }

  screenLiveLoopRunning = false;
  if (!state.screenLiveActive) {
    if (liveBadge) liveBadge.classList.add('hidden');
    if (fpsBadge) fpsBadge.classList.add('hidden');
  }
}

function toggleScreenAutoRefresh() {
  const checkbox = document.getElementById('screenAutoRefreshToggle');
  const liveBadge = document.getElementById('screenLiveBadge');
  const fpsBadge = document.getElementById('screenFpsBadge');
  
  if (checkbox && checkbox.checked) {
    state.screenLiveActive = true;
    if (liveBadge) liveBadge.classList.remove('hidden');
    runAdaptiveScreenLiveLoop();
  } else {
    state.screenLiveActive = false;
    if (liveBadge) liveBadge.classList.add('hidden');
    if (fpsBadge) fpsBadge.classList.add('hidden');
  }
}

function openScreenFullscreen() {
  const modal = document.getElementById('screenFullscreenModal');
  const img = document.getElementById('pcScreenImage');
  const modalImg = document.getElementById('modalScreenImage');
  if (img && modalImg && img.src) {
    modalImg.src = img.src;
  }
  if (modal) modal.classList.remove('hidden');
  lucide.createIcons();
}

function closeScreenFullscreen() {
  const modal = document.getElementById('screenFullscreenModal');
  if (modal) modal.classList.add('hidden');
}

async function fetchActiveWindows() {
  try {
    const res = await apiFetch(`/api/screen/windows?t=${Date.now()}${getAuthQuery()}`);
    const data = await res.json();
    renderActiveWindows(data.windows || []);
  } catch (err) {
    console.error('fetchActiveWindows error:', err);
  }
}

function copyWindowName(title) {
  if (!title) return;
  navigator.clipboard.writeText(title).then(() => {
    showToast(`창 제목 '${title}'을(를) 복사했습니다!`, 'success');
  }).catch(() => {
    showToast('창 제목 복사 완료', 'info');
  });
}

function renderActiveWindows(windows) {
  const container = document.getElementById('activeWindowsList');
  const badge = document.getElementById('activeWindowsCountBadge');
  if (!container) return;

  if (badge) badge.innerText = `${windows.length}개`;

  if (!windows || windows.length === 0) {
    container.innerHTML = `
      <div class="col-span-full text-center py-6 border border-dashed border-slate-700/60 rounded-xl text-slate-500 text-xs">
        열려 있는 창이 없거나 정보를 불러올 수 없습니다.
      </div>
    `;
    return;
  }

  container.innerHTML = windows.map((w) => {
    let icon = 'app-window';
    let appType = '프로그램';
    const lower = w.title.toLowerCase();
    if (lower.includes('chrome') || lower.includes('edge') || lower.includes('whale') || lower.includes('firefox')) {
      icon = 'globe';
      appType = '웹 브라우저';
    } else if (lower.includes('discord')) {
      icon = 'message-square';
      appType = '디스코드';
    } else if (lower.includes('카카오톡') || lower.includes('kakaotalk')) {
      icon = 'message-circle';
      appType = '카카오톡';
    } else if (lower.includes('visual studio') || lower.includes('code') || lower.includes('ide')) {
      icon = 'code';
      appType = '개발 도구';
    } else if (lower.includes('deskpilot')) {
      icon = 'compass';
      appType = 'DeskPilot';
    } else if (lower.includes('탐색기') || lower.includes('explorer')) {
      icon = 'folder';
      appType = '파일 탐색기';
    }

    return `
      <div onclick="copyWindowName('${escapeHtml(w.title)}')" class="p-3 bg-slate-900/60 hover:bg-slate-900/90 active:scale-98 border border-slate-700/60 hover:border-indigo-500/50 rounded-xl flex items-center justify-between gap-2.5 transition-all cursor-pointer group" title="클릭하여 창 제목 복사">
        <div class="flex items-center gap-2.5 min-w-0 flex-1">
          <div class="w-8 h-8 rounded-lg bg-indigo-500/10 group-hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 flex items-center justify-center shrink-0 transition-colors">
            <i data-lucide="${icon}" class="w-4 h-4"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-xs font-semibold text-slate-200 truncate group-hover:text-white transition-colors" title="${escapeHtml(w.title)}">
              ${escapeHtml(w.title)}
            </div>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-[10px] text-indigo-300 font-medium">${appType}</span>
              ${w.width ? `<span class="text-[10px] text-slate-500 font-mono">${w.width}x${w.height}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">실행 중</span>
          <i data-lucide="copy" class="w-3.5 h-3.5 text-slate-500 group-hover:text-indigo-300 opacity-0 group-hover:opacity-100 transition-opacity"></i>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

// Initial Boot
window.addEventListener('DOMContentLoaded', () => {
  fetchTasks();
  fetchNotes();
  fetchScanFiles();
  fetchSharedFiles();
  fetchSharedClips();
  fetchStatus();
  checkMobilePairingPrompt();
  lucide.createIcons();
});

// --- Realtime Auto-Sync Engine ---
// Periodically synchronizes tasks, notes, shared files, clips, status, and settings across PC & Smartphone
let syncTickCount = 0;

async function performAutoSync() {
  if (document.hidden) return; // Paused when window/tab is hidden

  syncTickCount++;

  // 1. Every 2.5 seconds: Status & Tasks & Shared Files & Shared Clips
  try {
    await fetchStatus();
  } catch (e) {}

  try {
    await fetchTasks(true);
  } catch (e) {}

  try {
    await fetchSharedFiles();
  } catch (e) {}

  try {
    await fetchSharedClips();
  } catch (e) {}

  // 2. Notes sync (only when user is not actively typing in notesArea)
  try {
    await fetchNotes(false);
  } catch (e) {}

  // 3. Tab-specific sync:
  if (state.activeTab === 'settings' || window.__phoneModalOpen) {
    try {
      await fetchSettings();
    } catch (e) {}
  } else if (state.activeTab === 'organize' && syncTickCount % 2 === 0) {
    // Every 5s on organize tab
    try {
      await fetchScanFiles();
    } catch (e) {}
  } else if (state.activeTab === 'screen' && syncTickCount % 2 === 0) {
    // Every 5s on screen tab: refresh open windows
    try {
      await fetchActiveWindows();
    } catch (e) {}
  }
}

// Start auto-sync interval (every 2500ms)
setInterval(performAutoSync, 2500);

// Immediate sync when window regains focus or tab becomes visible
window.addEventListener('focus', () => {
  performAutoSync();
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    performAutoSync();
    if (state.activeTab === 'screen' && state.screenLiveActive) {
      runAdaptiveScreenLiveLoop();
    }
  }
});
