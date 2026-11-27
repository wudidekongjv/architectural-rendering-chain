<template>
  <div class="app-shell">
    <!-- 左侧渲染记录侧栏 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="brand">
        <div class="brand-mark">A</div>
        <span v-if="!sidebarCollapsed" class="brand-name">ArchRender</span>
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '收起'">
          {{ sidebarCollapsed ? '»' : '«' }}
        </button>
      </div>

      <button class="new-chat-btn" @click="newRender" :title="sidebarCollapsed ? '新建渲染' : ''">
        <span class="plus">＋</span>
        <span v-if="!sidebarCollapsed">新建渲染</span>
      </button>

      <div v-if="!sidebarCollapsed" class="history-section">
        <div class="history-label">渲染记录</div>
        <div v-if="historyLoading" class="history-empty">加载中…</div>
        <div v-else-if="history.length === 0" class="history-empty">暂无渲染记录</div>
        <div v-else class="history-list">
          <div v-for="task in history" :key="task.task_id" class="history-item"
               :class="{ active: currentTask && currentTask.task_id === task.task_id }"
               @click="loadHistory(task)">
            <img v-if="task.thumb" :src="task.thumb" class="history-thumb" alt="" />
            <div v-else class="history-thumb placeholder">✦</div>
            <div class="history-info">
              <div class="history-prompt">{{ task.prompt }}</div>
              <div class="history-time">{{ task.time_label }}</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!sidebarCollapsed" class="sidebar-footer">
        <div class="avatar">{{ (identity.user_id || 'BZ').slice(-4) }}</div>
        <div class="footer-text">
          <div class="footer-name">{{ identity.user_id || '连接中…' }}</div>
          <div class="footer-plan">{{ identity.role_name || '方案组' }} · {{ identity.quota_per_day || 0 }} 次/日</div>
        </div>
      </div>
    </aside>

    <!-- 主区域 -->
    <main class="main-area">
      <header class="topbar">
        <span class="topbar-title">建筑渲染工作台</span>
        <div class="topbar-right">
          <span class="status-dot" :class="{ online: serverOk }"></span>
          <span class="status-text">{{ serverOk ? '局域网已连接' : (initError || '连接中…') }}</span>
          <button v-if="!serverOk" class="retry-btn" @click="init">重试</button>
        </div>
      </header>

      <div class="content-area" ref="contentArea">
        <!-- 连接失败提示（不伪造任何内容） -->
        <div v-if="initError" class="error-screen">
          <div class="error-icon">⚠</div>
          <h2>无法连接到渲染服务</h2>
          <p>{{ initError }}</p>
          <ul>
            <li>确认你处于服务器所在局域网</li>
            <li>确认后端服务已启动（端口 8000）</li>
            <li>联系管理员检查设备授权状态</li>
          </ul>
          <button class="retry-btn big" @click="init">重新连接</button>
        </div>

        <!-- 空状态 Hero -->
        <div v-else-if="!currentTask && messages.length === 0" class="hero">
          <div class="hero-mark">✦</div>
          <h1>What can we create together?</h1>
          <p class="hero-sub">描述你的建筑构想，或直接拖入白模 / 线稿图片，AI 将为你生成可交付效果图</p>
          <div class="quick-tags">
            <button v-for="tag in quickTags" :key="tag.label" class="quick-tag" @click="applyQuickTag(tag)">
              <span class="tag-icon">{{ tag.icon }}</span>{{ tag.label }}
            </button>
          </div>
        </div>

        <!-- 对话流程（全部来自真实后端数据） -->
        <div v-else class="conversation">
          <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="msg.role">
            <template v-if="msg.role === 'user'">
              <div class="msg-bubble user-bubble">
                <div class="msg-images" v-if="msg.images && msg.images.length">
                  <img v-for="(im, i) in msg.images" :key="i" :src="im" class="msg-user-img"
                       @click="referenceExisting(im)" title="点击引用此图" />
                </div>
                <div class="msg-text">{{ msg.text }}</div>
              </div>
            </template>
            <template v-else>
              <div class="msg-bubble ai-bubble">
                <div class="ai-header">
                  <span class="ai-avatar">✦</span>
                  <span class="ai-name">ArchRender Agent</span>
                  <span class="ai-stage">{{ msg.stageLabel }}</span>
                </div>

                <div v-if="msg.type === 'progress'" class="stage-timeline">
                  <div v-for="(s, i) in renderStages" :key="s.key" class="stage-item"
                       :class="{ done: i < msg.stageIdx, active: i === msg.stageIdx }">
                    <span class="stage-dot">{{ i < msg.stageIdx ? '✓' : i + 1 }}</span>
                    <span class="stage-name">{{ s.label }}</span>
                  </div>
                </div>

                <div v-if="msg.type === 'drafts'" class="drafts-section">
                  <p class="section-hint">已生成 4 张候选初稿，点击选择一张进入精修：</p>
                  <div class="draft-grid">
                    <div v-for="(img, idx) in msg.images" :key="idx" class="draft-card"
                         :class="{ selected: msg.selected === idx }" @click="msg.selected = idx">
                      <img :src="img" :alt="'候选 ' + (idx + 1)" />
                      <div class="draft-index">{{ idx + 1 }}</div>
                      <button class="draft-ref" @click.stop="referenceExisting(img)" title="引用此图">引用</button>
                    </div>
                  </div>
                  <button class="approve-btn" :disabled="msg.selected === null || msg.approving" @click="approveDraft(msg)">
                    {{ msg.approving ? '精修中…' : '确认选择，开始精修 →' }}
                  </button>
                </div>

                <div v-if="msg.type === 'final'" class="final-section">
                  <img :src="msg.image" class="final-img" alt="最终效果图" />
                  <div class="final-actions">
                    <button class="action-btn" @click="referenceExisting(msg.image)">引用此图</button>
                    <a class="action-btn primary" :href="msg.image" :download="msg.fileName || 'render.png'">下载效果图</a>
                  </div>
                </div>

                <div v-if="msg.type === 'text'" class="ai-text">{{ msg.text }}</div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-dock" :class="{ 'drag-over': isDragOver }"
           @dragover.prevent="isDragOver = true" @dragleave.prevent="isDragOver = false" @drop.prevent="onDrop">
        <div v-if="isDragOver" class="drag-overlay">
          <div class="drag-icon">↓</div>
          <div>松开即可上传图片</div>
        </div>

        <div v-if="attachedImages.length" class="attached-strip">
          <div v-for="(img, i) in attachedImages" :key="i" class="attached-chip" @click="focusInput">
            <img :src="img.url" alt="" />
            <span class="attached-name">{{ img.name }}</span>
            <button class="chip-remove" @click.stop="removeAttached(i)" title="移除">×</button>
          </div>
          <span class="attached-hint">点击图片可引用</span>
        </div>

        <div class="input-box">
          <button class="icon-btn" @click="triggerFileInput" title="上传图片">
            <svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M3 5h18a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm0 2v10h18V7H3zm2 2h4v2H5V9zm0 4h4v2H5v-2zm6-4h6v6h-6V9z"/></svg>
          </button>
          <input ref="fileInput" type="file" accept="image/*" multiple hidden @change="onFileChange" />
          <textarea ref="inputEl" v-model="inputText" rows="1"
                    placeholder="描述你想要的建筑效果图，或拖拽图片到此处…"
                    :disabled="!serverOk"
                    @keydown.enter.exact.prevent="sendMessage" @keydown.shift.enter.prevent="inputText += '\n'"></textarea>
          <button class="send-btn" @click="sendMessage" :disabled="!serverOk || (!inputText.trim() && !attachedImages.length)" title="发送">
            <svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M3 20l18-8L3 4v6l12 2-12 2v6z"/></svg>
          </button>
        </div>

        <div class="input-footer">
          <span>Enter 发送 · Shift+Enter 换行 · 支持拖拽上传</span>
          <span class="model-tag">{{ identity.user_id || '—' }} · SDXL + Flux</span>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'

const API_BASE = ''   // 同源部署（Vite 开发时通过 proxy 转发到后端）

const sidebarCollapsed = ref(false)
const serverOk = ref(false)
const initError = ref('')
const identity = ref({ user_id: '', role: '', role_name: '', quota_per_day: 0 })
const deviceId = ref('')

const inputText = ref('')
const attachedImages = ref([])   // {url, name, file?, serverPath?}
const fileInput = ref(null)
const inputEl = ref(null)
const contentArea = ref(null)
const isDragOver = ref(false)
const currentTask = ref(null)
const messages = ref([])
const history = ref([])
const historyLoading = ref(false)

const renderStages = [
  { key: 'prompt', label: 'LLM 提示词优化' },
  { key: 'controlnet', label: 'ControlNet 结构控制' },
  { key: 'sdxl', label: 'SDXL 多候选初稿' },
  { key: 'approval', label: '人工审批' },
  { key: 'flux', label: 'Flux 精修' },
]

const quickTags = [
  { label: '建筑外观', icon: '▣', text: '现代极简风格建筑外观，自然光照，建筑摄影' },
  { label: '室内空间', icon: '⌂', text: '现代简约室内设计，暖色调，柔和自然光' },
  { label: '概念草图', icon: '✎', text: '建筑概念设计草图，手绘风格，线稿表达' },
  { label: '景观庭院', icon: '❋', text: '庭院景观设计，绿植与水体，黄昏光照' },
]

// ============ 设备指纹（自动登录凭据） ============
function generateDeviceFingerprint() {
  let id = localStorage.getItem('archrender_device_id')
  if (id) return id

  // 组合多项设备信号 + 随机 UUID，保证唯一且稳定
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  ctx.textBaseline = 'top'
  ctx.font = '14px Arial'
  ctx.fillText('archrender-fingerprint', 2, 2)
  const canvasSig = canvas.toDataURL().slice(-64)

  const signals = [
    navigator.userAgent,
    navigator.language,
    (navigator.languages || []).join(','),
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    String(new Date().getTimezoneOffset()),
    String(navigator.hardwareConcurrency || ''),
    canvasSig,
    // crypto.randomUUID 仅在安全上下文(HTTPS/localhost)可用；
    // 局域网 HTTP 访问需降级到 Math.random + 时间戳
    (crypto.randomUUID ? crypto.randomUUID() :
      `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`),
  ]
  // 简单哈希（FNV-1a 变体），输出 32 位十六进制
  let h = 0x811c9dc5
  const str = signals.join('|')
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  const randomPart = crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : (Date.now().toString(16) + Math.random().toString(36).slice(2)).slice(0, 16)
  id = ('dev_' + (h >>> 0).toString(16).padStart(8, '0') + randomPart)
  localStorage.setItem('archrender_device_id', id)
  return id
}

// ============ API 客户端（所有请求带设备指纹） ============
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), 'X-Device-Id': deviceId.value }
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch {}
    throw new Error(detail)
  }
  return res.json()
}

async function init() {
  initError.value = ''
  serverOk.value = false
  try {
    deviceId.value = generateDeviceFingerprint()
    // 设备注册（后端放行该端点，无需预先鉴权）
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId.value, label: navigator.userAgent.slice(0, 80) }),
    })
    if (!res.ok) throw new Error('设备注册失败：' + res.statusText)
    identity.value = await res.json()
    serverOk.value = true
    await fetchHistoryList()
  } catch (err) {
    initError.value = err.message || '网络连接失败'
    serverOk.value = false
  }
}

async function fetchHistoryList() {
  historyLoading.value = true
  try {
    history.value = await api('/api/tasks')
  } catch (err) {
    initError.value = '加载渲染记录失败：' + err.message
  } finally {
    historyLoading.value = false
  }
}

onMounted(init)

// ============ 交互 ============
function applyQuickTag(tag) { inputText.value = tag.text; nextTick(() => inputEl.value?.focus()) }
function triggerFileInput() { fileInput.value?.click() }
function addFiles(files) {
  for (const file of files) {
    if (!file.type.startsWith('image/')) continue
    attachedImages.value.push({ url: URL.createObjectURL(file), name: file.name, file })
  }
  nextTick(() => inputEl.value?.focus())
}
function onFileChange(e) { addFiles(Array.from(e.target.files || [])); e.target.value = '' }
function onDrop(e) { isDragOver.value = false; addFiles(Array.from(e.dataTransfer.files || [])) }
function removeAttached(i) { attachedImages.value.splice(i, 1) }
function focusInput() { inputEl.value?.focus() }

// 点击历史/结果中的图片 → 作为引用加入输入框
function referenceExisting(url) {
  attachedImages.value.push({ url, name: '引用图片', file: null, serverPath: url })
  nextTick(() => {
    inputEl.value?.focus()
    document.querySelector('.input-dock')?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  })
}

async function sendMessage() {
  if (!inputText.value.trim() && !attachedImages.value.length) return
  if (!serverOk.value) return

  const text = inputText.value.trim()
  const displayImages = attachedImages.value.map(a => a.url)
  const referencePaths = attachedImages.value.filter(a => a.serverPath).map(a => a.serverPath)
  const realFiles = attachedImages.value.filter(a => a.file)

  // 用户消息（真实引用路径显示在图片上）
  messages.value.push({ id: Date.now(), role: 'user', text: text || '请根据这张图片生成效果图', images: displayImages })
  inputText.value = ''; attachedImages.value = []
  await nextTick(); scrollToBottom()

  if (!realFiles.length) {
    messages.value.push({ id: Date.now() + 1, role: 'ai', type: 'text', stageLabel: '提示', text: '请至少上传一张白模 / 线稿图片。' })
    return
  }

  try {
    const progressMsg = {
      id: Date.now() + 2, role: 'ai', type: 'progress', stageIdx: 0,
      stageLabel: '正在提交渲染任务…', images: [], taskId: null,
    }
    messages.value.push(progressMsg)
    await nextTick(); scrollToBottom()

    const formData = new FormData()
    formData.append('user_input', text)
    formData.append('image', realFiles[0].file)
    formData.append('reference_paths', JSON.stringify(referencePaths))
    const result = await api('/api/v1/render', { method: 'POST', body: formData })

    progressMsg.taskId = result.task_id
    progressMsg.stageIdx = 3
    progressMsg.stageLabel = '初稿已生成，待审批'

    messages.value.push({
      id: Date.now() + 3, role: 'ai', type: 'drafts', stageLabel: '人工审批',
      images: result.draft_images, selected: null, taskId: result.task_id, approving: false,
    })
    currentTask.value = {
      task_id: result.task_id, prompt: text, thumb: result.draft_images[0],
      time_label: '刚刚', final_image: '', images: result.draft_images,
    }
    history.value.unshift(currentTask.value)
    listenProgress(result.task_id, progressMsg)
    await nextTick(); scrollToBottom()
  } catch (err) {
    messages.value.push({ id: Date.now() + 4, role: 'ai', type: 'text', stageLabel: '错误', text: err.message })
    await nextTick(); scrollToBottom()
  }
}

function listenProgress(taskId, progressMsg) {
  const es = new EventSource(`${API_BASE}/api/v1/render/stream?task_id=${taskId}&device_id=${deviceId.value}`)
  // EventSource 不支持自定义 header，用 query 参数传递设备指纹（后端中间件同时接受 query）
  es.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data)
    const stageMap = { prompt_optimize: 0, controlnet: 1, sdxl_draft: 2, human_approval: 3, flux_refine: 4 }
    if (stageMap[data.stage] !== undefined) progressMsg.stageIdx = stageMap[data.stage]
    progressMsg.stageLabel = data.stage
  })
  es.addEventListener('done', (e) => {
    const data = JSON.parse(e.data)
    if (data.final_image) {
      const finalUrl = data.final_image
      messages.value.push({ id: Date.now(), role: 'ai', type: 'final', stageLabel: '交付', image: finalUrl, fileName: 'render.png' })
      if (currentTask.value) currentTask.value.final_image = finalUrl
    }
    es.close()
  })
  es.addEventListener('error', (e) => {
    if (e.data) progressMsg.stageLabel = '错误：' + e.data
    es.close()
  })
}

async function approveDraft(msg) {
  if (msg.selected === null || msg.approving) return
  msg.approving = true
  try {
    await api(`/api/v1/render/${msg.taskId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_index: msg.selected, reference_images: [] }),
    })
    msg.stageLabel = '精修完成，等待结果'
  } catch (err) {
    messages.value.push({ id: Date.now(), role: 'ai', type: 'text', stageLabel: '错误', text: err.message })
  } finally {
    msg.approving = false
    await nextTick(); scrollToBottom()
  }
}

async function loadHistory(task) {
  currentTask.value = task
  try {
    const detail = await api(`/api/tasks/${task.task_id}`)
    messages.value = [
      { id: Date.now(), role: 'user', text: detail.prompt, images: detail.reference_images },
    ]
    if (detail.draft_images && detail.draft_images.length && detail.stage === 'awaiting_approval') {
      messages.value.push({
        id: Date.now() + 1, role: 'ai', type: 'drafts', stageLabel: '人工审批',
        images: detail.draft_images, selected: null, taskId: task.task_id, approving: false,
      })
    } else if (detail.final_image) {
      messages.value.push({ id: Date.now() + 2, role: 'ai', type: 'final', stageLabel: '历史渲染', image: detail.final_image })
    } else {
      messages.value.push({ id: Date.now() + 3, role: 'ai', type: 'text', stageLabel: detail.stage, text: detail.error || '任务处理中' })
    }
  } catch (err) {
    messages.value.push({ id: Date.now(), role: 'ai', type: 'text', stageLabel: '错误', text: err.message })
  }
  await nextTick(); scrollToBottom()
}

function newRender() { currentTask.value = null; messages.value = []; inputText.value = ''; attachedImages.value = [] }
function scrollToBottom() { if (contentArea.value) contentArea.value.scrollTop = contentArea.value.scrollHeight }
</script>

<style scoped>
.app-shell {
  display: flex; height: 100vh; width: 100%;
  background:
    radial-gradient(ellipse 55% 45% at 50% -5%, rgba(28, 78, 88, 0.55) 0%, transparent 70%),
    radial-gradient(ellipse 45% 40% at 8% 100%, rgba(18, 92, 74, 0.32) 0%, transparent 70%),
    radial-gradient(ellipse 45% 40% at 92% 100%, rgba(26, 58, 116, 0.34) 0%, transparent 70%),
    #0b1016;
  color: #e8edf4;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.sidebar { width: 248px; flex-shrink: 0; display: flex; flex-direction: column; background: rgba(8,12,18,0.72); border-right: 1px solid rgba(255,255,255,0.06); backdrop-filter: blur(16px); transition: width 0.25s ease; overflow: hidden; }
.sidebar.collapsed { width: 64px; }
.brand { display: flex; align-items: center; gap: 10px; padding: 18px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.brand-mark { width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0; background: linear-gradient(135deg,#e8563f,#b8301c); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 15px; color: #fff; }
.brand-name { font-size: 15px; font-weight: 600; letter-spacing: 0.3px; flex: 1; }
.collapse-btn { background: none; border: none; color: #8b98a8; cursor: pointer; font-size: 18px; padding: 2px 6px; border-radius: 4px; }
.collapse-btn:hover { color: #e8edf4; background: rgba(255,255,255,0.06); }
.new-chat-btn { margin: 14px 12px 8px; padding: 11px 14px; background: rgba(232,86,63,0.12); border: 1px solid rgba(232,86,63,0.35); border-radius: 9px; color: #ff8a75; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 13px; transition: all 0.2s; }
.new-chat-btn:hover { background: rgba(232,86,63,0.2); }
.plus { font-size: 17px; line-height: 1; }
.history-section { flex: 1; overflow-y: auto; padding: 8px 10px; }
.history-label { font-size: 11px; color: #8b98a8; text-transform: uppercase; letter-spacing: 1px; padding: 8px 6px 10px; }
.history-empty { font-size: 11px; color: #647082; padding: 16px 6px; text-align: center; }
.history-item { display: flex; gap: 10px; align-items: center; padding: 8px; border-radius: 8px; cursor: pointer; margin-bottom: 3px; transition: background 0.15s; }
.history-item:hover { background: rgba(255,255,255,0.06); }
.history-item.active { background: rgba(232,86,63,0.14); }
.history-thumb { width: 38px; height: 38px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }
.history-thumb.placeholder { display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.06); color: #8b98a8; }
.history-info { min-width: 0; flex: 1; }
.history-prompt { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #d6dee8; }
.history-time { font-size: 10px; color: #8b98a8; margin-top: 3px; }
.sidebar-footer { display: flex; align-items: center; gap: 9px; padding: 14px; border-top: 1px solid rgba(255,255,255,0.05); }
.avatar { width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0; background: linear-gradient(135deg,#3b6ea5,#1e4b7a); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; }
.footer-name { font-size: 12px; font-weight: 600; color: #e8edf4; }
.footer-plan { font-size: 10px; color: #8b98a8; margin-top: 2px; }

.main-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar { height: 52px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; border-bottom: 1px solid rgba(255,255,255,0.05); }
.topbar-title { font-size: 13px; color: #b9c4d1; }
.topbar-right { display: flex; align-items: center; gap: 7px; font-size: 11px; color: #8b98a8; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: #e8a13f; }
.status-dot.online { background: #3fb98a; box-shadow: 0 0 8px rgba(63,185,138,0.6); }
.retry-btn { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); color: #d6dee8; border-radius: 5px; padding: 4px 10px; font-size: 11px; cursor: pointer; }
.retry-btn:hover { background: rgba(255,255,255,0.15); }
.retry-btn.big { padding: 10px 22px; font-size: 13px; margin-top: 8px; }
.content-area { flex: 1; overflow-y: auto; padding: 32px 24px; scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.15) transparent; }

.error-screen { max-width: 520px; margin: 12vh auto; text-align: center; }
.error-icon { font-size: 42px; color: #e8a13f; margin-bottom: 12px; }
.error-screen h2 { font-size: 20px; font-weight: 600; margin: 0 0 12px; }
.error-screen p { font-size: 13px; color: #ff9b87; margin: 0 0 20px; }
.error-screen ul { text-align: left; font-size: 12px; color: #8b98a8; line-height: 2; margin: 0 auto 20px; max-width: 320px; }

.hero { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding-bottom: 40px; }
.hero-mark { font-size: 34px; color: #e8563f; margin-bottom: 16px; text-shadow: 0 0 24px rgba(232,86,63,0.5); }
.hero h1 { font-size: 30px; font-weight: 600; letter-spacing: -0.4px; margin: 0 0 10px; background: linear-gradient(180deg,#fff,#b8c4d2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.hero-sub { font-size: 13px; color: #8b98a8; max-width: 560px; line-height: 1.7; margin: 0 0 28px; }
.quick-tags { display: flex; flex-wrap: wrap; gap: 9px; justify-content: center; }
.quick-tag { display: flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: 12px; cursor: pointer; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; color: #c5d0dc; transition: all 0.2s; }
.quick-tag:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.18); transform: translateY(-1px); }
.tag-icon { color: #e8563f; font-size: 13px; }

.conversation { max-width: 860px; margin: 0 auto; }
.msg-row { display: flex; margin-bottom: 22px; }
.msg-row.user { justify-content: flex-end; }
.msg-row.ai { justify-content: flex-start; }
.msg-bubble { max-width: 100%; border-radius: 14px; padding: 14px 16px; }
.user-bubble { background: rgba(232,86,63,0.13); border: 1px solid rgba(232,86,63,0.25); max-width: 76%; border-bottom-right-radius: 4px; }
.msg-user-img { width: 64px; height: 64px; object-fit: cover; border-radius: 7px; margin: 0 6px 8px 0; cursor: pointer; border: 1px solid rgba(255,255,255,0.2); transition: transform 0.15s; }
.msg-user-img:hover { transform: scale(1.06); border-color: #e8563f; }
.msg-text { font-size: 13px; line-height: 1.65; white-space: pre-wrap; }
.ai-bubble { background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.08); width: 100%; border-bottom-left-radius: 4px; }
.ai-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.ai-avatar { width: 22px; height: 22px; border-radius: 6px; background: rgba(232,86,63,0.2); display: flex; align-items: center; justify-content: center; color: #ff8a75; font-size: 12px; }
.ai-name { font-size: 12px; font-weight: 600; color: #dbe3ec; }
.ai-stage { font-size: 11px; color: #8b98a8; margin-left: auto; }
.stage-timeline { display: flex; flex-wrap: wrap; gap: 6px; }
.stage-item { display: flex; align-items: center; gap: 5px; padding: 5px 9px; border-radius: 6px; font-size: 11px; background: rgba(255,255,255,0.03); color: #8b98a8; }
.stage-item.active { background: rgba(232,86,63,0.15); color: #ff9b87; }
.stage-item.done { color: #5fc79a; }
.stage-dot { width: 15px; height: 15px; border-radius: 50%; font-size: 9px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.08); }
.stage-item.active .stage-dot { background: #e8563f; color: #fff; }
.stage-item.done .stage-dot { background: rgba(95,199,154,0.2); }
.section-hint { font-size: 12px; color: #8b98a8; margin: 0 0 12px; }
.draft-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; }
.draft-card { position: relative; border-radius: 9px; overflow: hidden; cursor: pointer; border: 2px solid transparent; transition: all 0.2s; }
.draft-card:hover { transform: translateY(-2px); }
.draft-card.selected { border-color: #e8563f; box-shadow: 0 0 0 3px rgba(232,86,63,0.15); }
.draft-card img { width: 100%; display: block; aspect-ratio: 4/3; object-fit: cover; }
.draft-index { position: absolute; top: 8px; left: 8px; width: 22px; height: 22px; border-radius: 50%; background: rgba(0,0,0,0.65); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 11px; }
.draft-ref { position: absolute; bottom: 8px; right: 8px; padding: 4px 9px; background: rgba(0,0,0,0.7); color: #fff; border: 1px solid rgba(255,255,255,0.25); border-radius: 5px; font-size: 10px; cursor: pointer; }
.draft-ref:hover { background: #e8563f; border-color: #e8563f; }
.approve-btn { margin-top: 14px; padding: 9px 18px; border: none; border-radius: 7px; background: #e8563f; color: #fff; font-size: 12px; cursor: pointer; transition: background 0.2s; }
.approve-btn:hover:not(:disabled) { background: #ff6a52; }
.approve-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.final-img { width: 100%; border-radius: 9px; display: block; margin-bottom: 12px; }
.final-actions { display: flex; gap: 9px; }
.action-btn { padding: 8px 14px; border-radius: 7px; font-size: 11px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); color: #d6dee8; text-decoration: none; display: inline-block; }
.action-btn:hover { background: rgba(255,255,255,0.12); }
.action-btn.primary { background: #e8563f; border-color: #e8563f; color: #fff; }
.ai-text { font-size: 13px; line-height: 1.7; color: #d6dee8; }

.input-dock { flex-shrink: 0; padding: 10px 24px 18px; background: linear-gradient(180deg,transparent,rgba(8,12,18,0.75) 30%); position: relative; }
.drag-overlay { position: absolute; inset: 0 24px 18px; border: 2px dashed #e8563f; border-radius: 14px; background: rgba(232,86,63,0.1); display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 13px; color: #ff9b87; z-index: 10; pointer-events: none; }
.drag-icon { font-size: 30px; margin-bottom: 6px; }
.attached-strip { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 9px; padding: 0 2px; }
.attached-chip { display: flex; align-items: center; gap: 7px; padding: 4px 8px 4px 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); border-radius: 7px; cursor: pointer; font-size: 11px; }
.attached-chip:hover { border-color: rgba(232,86,63,0.5); }
.attached-chip img { width: 28px; height: 28px; border-radius: 4px; object-fit: cover; }
.attached-name { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-remove { background: none; border: none; color: #8b98a8; cursor: pointer; font-size: 15px; padding: 0 2px; }
.chip-remove:hover { color: #ff8a75; }
.attached-hint { font-size: 10px; color: #8b98a8; }
.input-box { max-width: 860px; margin: 0 auto; display: flex; align-items: flex-end; gap: 9px; background: rgba(255,255,255,0.055); border: 1px solid rgba(255,255,255,0.12); border-radius: 15px; padding: 9px 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.25); transition: border-color 0.2s; }
.input-box:focus-within { border-color: rgba(232,86,63,0.5); }
.icon-btn { background: none; border: none; color: #8b98a8; cursor: pointer; padding: 7px; border-radius: 7px; flex-shrink: 0; display: flex; }
.icon-btn:hover { color: #e8edf4; background: rgba(255,255,255,0.08); }
.input-box textarea { flex: 1; background: transparent; border: none; outline: none; resize: none; color: #e8edf4; font-size: 13px; line-height: 1.55; font-family: inherit; min-height: 24px; max-height: 120px; padding: 7px 0; }
.input-box textarea::placeholder { color: #647082; }
.send-btn { width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0; background: #e8563f; border: none; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.2s; }
.send-btn:hover:not(:disabled) { background: #ff6a52; }
.send-btn:disabled { background: rgba(255,255,255,0.1); color: #8b98a8; cursor: not-allowed; }
.input-footer { max-width: 860px; margin: 8px auto 0; display: flex; justify-content: space-between; font-size: 10px; color: #5d6878; }
.model-tag { color: #8b98a8; }
</style>
