<template>
  <div class="app">
    <h1>Architectural Rendering Chain</h1>
    <p>建筑渲染图像生成 Agent —— AI 生成 + 人工审批</p>

    <section class="submit-section">
      <h2>1. 提交渲染任务</h2>
      <input v-model="userInput" placeholder="描述你想要的建筑效果图，例如：现代别墅 带泳池 庭院" />
      <input type="file" @change="onFileChange" accept="image/*" />
      <button @click="submitRender" :disabled="loading">生成初稿</button>
    </section>

    <section v-if="taskId" class="progress-section">
      <h2>2. 生成进度</h2>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
      </div>
      <p>当前阶段：{{ stage }} ({{ progress }}%)</p>
    </section>

    <section v-if="drafts.length" class="approval-section">
      <h2>3. 人工审批 —— 选择一张初稿</h2>
      <div class="draft-grid">
        <div v-for="(img, idx) in drafts" :key="idx" class="draft-item"
             :class="{ selected: selectedIndex === idx }" @click="selectedIndex = idx">
          <img :src="img" :alt="'Draft ' + (idx + 1)" />
          <span>{{ idx + 1 }}</span>
        </div>
      </div>
      <button @click="approve" :disabled="selectedIndex < 0">确认并精修</button>
    </section>

    <section v-if="finalImage" class="result-section">
      <h2>4. 最终结果</h2>
      <img :src="finalImage" alt="Final render" class="final-image" />
      <a :href="finalImage" download>下载效果图</a>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const API_BASE = 'http://localhost:8000'

const userInput = ref('')
const file = ref(null)
const taskId = ref('')
const stage = ref('')
const progress = ref(0)
const drafts = ref([])
const selectedIndex = ref(-1)
const finalImage = ref('')
const loading = ref(false)

function onFileChange(e) {
  file.value = e.target.files[0]
}

async function submitRender() {
  if (!userInput.value || !file.value) return
  loading.value = true

  const formData = new FormData()
  formData.append('user_input', userInput.value)
  formData.append('image', file.value)

  try {
    // 使用 fetch + POST（EventSource 只能 GET，此处选 fetch更灵活）
    const res = await fetch(`${API_BASE}/api/v1/render`, {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()
    taskId.value = data.task_id
    stage.value = data.status

    // 查询任务状态获取初稿
    const statusRes = await fetch(`${API_BASE}/api/task/${data.task_id}/status`)
    const status = await statusRes.json()
    drafts.value = status.draft_images.map(p => `${API_BASE}/${p}`)

    // SSE 进度监听
    listenProgress(data.task_id)
  } catch (err) {
    alert('提交失败: ' + err.message)
  } finally {
    loading.value = false
  }
}

function listenProgress(id) {
  const es = new EventSource(`${API_BASE}/api/v1/render/stream?task_id=${id}`)

  es.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data)
    stage.value = data.stage
    progress.value = data.pct
  })

  es.addEventListener('done', (e) => {
    const data = JSON.parse(e.data)
    finalImage.value = `${API_BASE}/${data.final_image}`
    es.close()
  })

  es.addEventListener('error', (e) => {
    console.error('SSE error:', e.data)
    es.close()
  })
}

async function approve() {
  const res = await fetch(`${API_BASE}/api/v1/render/${taskId.value}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_index: selectedIndex.value }),
  })
  const data = await res.json()
  stage.value = data.status

  const statusRes = await fetch(`${API_BASE}/api/task/${taskId.value}/status`)
  const status = await statusRes.json()
  finalImage.value = `${API_BASE}/${status.final_image}`
}
</script>

<style scoped>
.app { max-width: 1200px; margin: 0 auto; padding: 24px; font-family: system-ui, sans-serif; }
.submit-section, .progress-section, .approval-section, .result-section {
  margin: 24px 0; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;
}
input[type="text"], input:not([type]) { display: block; width: 100%; padding: 10px; margin: 10px 0; }
button { padding: 10px 24px; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; }
button:disabled { background: #ccc; cursor: not-allowed; }
.progress-bar { height: 12px; background: #eee; border-radius: 6px; overflow: hidden; }
.progress-fill { height: 100%; background: #2563eb; transition: width 0.3s; }
.draft-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.draft-item { border: 3px solid transparent; cursor: pointer; position: relative; }
.draft-item.selected { border-color: #2563eb; }
.draft-item img { width: 100%; display: block; }
.draft-item span { position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.6); color: white; padding: 2px 8px; }
.final-image { max-width: 100%; display: block; margin: 16px 0; }
</style>
