<template>
  <section class="page" data-module="insure">
    <header class="page-head">
      <div>
        <h2>财产保险管理</h2>
        <p class="page-desc">按设备编号登记出险报案，一次事故多台设备合并为一案，逐台定损后提交理赔，每个状态都留操作人与时间。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">登记出险报案</button>
        <button class="btn" type="button" @click="exportRows">导出保险案件清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="create-panel" @submit.prevent="submitCreate">
      <label class="filter-item">
        <span>事故名称</span>
        <input v-model="createForm.事故名称" placeholder="如：暴雨导致信号机房进水" />
      </label>
      <label class="filter-item">
        <span>出险时间</span>
        <input v-model="createForm.出险时间" type="date" />
      </label>
      <label class="filter-item">
        <span>报案人</span>
        <input v-model="createForm.报案人" />
      </label>
      <label class="filter-item create-devices">
        <span>设备编号（每行一台或逗号分隔，多台合并为一案）</span>
        <textarea v-model="createForm.设备编号" rows="3" placeholder="SIGN-0001&#10;TRAC-0003"></textarea>
      </label>
      <button class="btn primary" type="submit">提交报案</button>
      <button class="btn ghost" type="button" @click="toggleCreate">取消</button>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>案件编号 / 事故名称</span>
        <input v-model="filters.keyword" placeholder="按案件编号或事故名称检索" />
      </label>
      <label class="filter-item">
        <span>案件状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row.案件编号 }}</td>
          <td>{{ row.事故名称 }}</td>
          <td>{{ row.出险时间 }}</td>
          <td>{{ row.报案人 }}</td>
          <td>{{ row.设备台数 }}</td>
          <td>{{ fmtMoney(row.定损合计) }}</td>
          <td>{{ fmtMoney(row.赔款合计) }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in caseActions[row.status] ?? []"
              :key="action"
              class="link"
              type="button"
              @click="runCaseAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无保险案件数据，可先登记出险报案</td>
        </tr>
      </tbody>
    </table>

    <section v-if="current" class="detail-panel">
      <h3>案件 {{ current.案件编号 }} · {{ current.事故名称 }}（{{ current.status }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>设备编号</th>
            <th>设备名称</th>
            <th>定损金额</th>
            <th>免赔比例(%)</th>
            <th>赔款金额</th>
            <th>明细状态</th>
            <th>免赔说明 / 拒赔原因</th>
            <th>定损人</th>
            <th>定损时间</th>
            <th v-if="current.status === '定损中'">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in current.items ?? []" :key="item.id">
            <td>{{ item.设备编号 }}</td>
            <td>{{ item.设备名称 || '—' }}</td>
            <td>{{ fmtMoney(item.定损金额) }}</td>
            <td>{{ item.免赔比例 ?? '—' }}</td>
            <td>{{ fmtMoney(item.赔款金额) }}</td>
            <td>{{ item.明细状态 }}</td>
            <td>{{ item.明细状态 === '已拒赔' ? item.拒赔原因 : item.免赔说明 || '—' }}</td>
            <td>{{ item.定损人 || '—' }}</td>
            <td>{{ item.定损时间 || '—' }}</td>
            <td v-if="current.status === '定损中'" class="row-actions">
              <template v-if="item.明细状态 !== '已拒赔'">
                <button class="link" type="button" @click="startAssess(item)">
                  {{ item.明细状态 === '已定损' ? '重新定损' : '定损' }}
                </button>
                <button class="link" type="button" @click="startReject(item)">拒赔</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>

      <form v-if="assessTarget !== null" class="filter-bar action-form" @submit.prevent="submitAssess">
        <label class="filter-item">
          <span>定损金额（元）</span>
          <input v-model="assessForm.定损金额" type="number" min="0" step="0.01" placeholder="核定的损失金额" />
        </label>
        <label class="filter-item">
          <span>免赔比例（%）</span>
          <input v-model="assessForm.免赔比例" type="number" min="0" max="100" step="0.01" placeholder="0–100" />
        </label>
        <label class="filter-item">
          <span>免赔说明</span>
          <input v-model="assessForm.免赔说明" placeholder="免赔依据，如保单条款编号" />
        </label>
        <button class="btn primary" type="submit">确认定损</button>
        <button class="btn ghost" type="button" @click="assessTarget = null">取消</button>
      </form>

      <form v-if="rejectTarget !== null" class="filter-bar action-form" @submit.prevent="submitReject">
        <label class="filter-item">
          <span>拒赔原因（只影响该台设备）</span>
          <input v-model="rejectForm.拒赔原因" placeholder="如：人为拆改导致损坏，不在保单责任范围内" />
        </label>
        <button class="btn primary" type="submit">确认拒赔</button>
        <button class="btn ghost" type="button" @click="rejectTarget = null">取消</button>
      </form>

      <h4>操作轨迹</h4>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>状态</th><th>操作人</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="(trail, index) in current.轨迹 ?? []" :key="index">
            <td>{{ trail.时间 }}</td>
            <td>{{ trail.状态 }}</td>
            <td>{{ trail.操作人 }}</td>
            <td>{{ trail.说明 }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条保险案件记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type ClaimItem = {
  id: number
  设备编号: string
  设备名称: string
  明细状态: string
  定损金额: number | null
  免赔比例: number | null
  免赔说明: string
  赔款金额: number | null
  拒赔原因: string
  定损人: string
  定损时间: string
}

type TrailEntry = { 状态: string; 操作人: string; 时间: string; 说明: string }

type CaseRow = {
  id: number
  status: string
  案件编号: string
  事故名称: string
  出险时间: string
  报案人: string
  设备台数: number
  定损合计: number | null
  赔款合计: number | null
  items?: ClaimItem[]
  轨迹?: TrailEntry[]
}

type ActionResult = { ok: boolean; message: string; entry: CaseRow | null }

const ENDPOINT = '/api/insure'
const columns = ['案件编号', '事故名称', '出险时间', '报案人', '设备台数', '定损合计', '赔款合计', '案件状态']
const statuses = ['已报案', '定损中', '待赔付', '已结案']
const caseActions: Record<string, string[]> = {
  已报案: ['转入定损'],
  定损中: ['提交理赔'],
  待赔付: ['结案'],
  已结案: [],
}

const store = useSessionStore()
const rows = ref<CaseRow[]>([])
const allRows = ref<CaseRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', status: '' })
const showCreate = ref(false)
const createForm = ref({ 事故名称: '', 出险时间: '', 报案人: store.operator, 设备编号: '' })
const current = ref<CaseRow | null>(null)
const assessTarget = ref<number | null>(null)
const assessForm = ref({ 定损金额: '', 免赔比例: '', 免赔说明: '' })
const rejectTarget = ref<number | null>(null)
const rejectForm = ref({ 拒赔原因: '' })

const stats = computed(() =>
  statuses.map((status) => ({
    label: `${status}案件`,
    value: allRows.value.filter((row) => row.status === status).length,
  })),
)

function fmtMoney(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return '—'
  }
  return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function toggleCreate() {
  showCreate.value = !showCreate.value
  if (showCreate.value) {
    createForm.value = { 事故名称: '', 出险时间: '', 报案人: store.operator, 设备编号: '' }
  }
}

async function postAction(path: string, values: Record<string, unknown>) {
  errorMessage.value = ''
  noticeMessage.value = ''
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values: { ...values, 操作人: store.operator } }),
  })
  const payload = (await response.json()) as ActionResult
  if (!payload.ok) {
    errorMessage.value = payload.message
    return false
  }
  noticeMessage.value = payload.message
  await reload()
  await refreshDetail()
  return true
}

async function submitCreate() {
  const ok = await postAction(ENDPOINT, { ...createForm.value })
  if (ok) {
    showCreate.value = false
  }
}

async function runCaseAction(action: string, row: CaseRow) {
  await postAction(`${ENDPOINT}/${row.id}/actions`, { action })
}

function startAssess(item: ClaimItem) {
  rejectTarget.value = null
  assessTarget.value = item.id
  assessForm.value = {
    定损金额: item.定损金额 === null ? '' : String(item.定损金额),
    免赔比例: item.免赔比例 === null ? '' : String(item.免赔比例),
    免赔说明: item.免赔说明 ?? '',
  }
}

async function submitAssess() {
  if (!current.value || assessTarget.value === null) {
    return
  }
  const ok = await postAction(`${ENDPOINT}/${current.value.id}/items/${assessTarget.value}/actions`, {
    action: '定损',
    ...assessForm.value,
  })
  if (ok) {
    assessTarget.value = null
  }
}

function startReject(item: ClaimItem) {
  assessTarget.value = null
  rejectTarget.value = item.id
  rejectForm.value = { 拒赔原因: '' }
}

async function submitReject() {
  if (!current.value || rejectTarget.value === null) {
    return
  }
  const ok = await postAction(`${ENDPOINT}/${current.value.id}/items/${rejectTarget.value}/actions`, {
    action: '拒赔',
    ...rejectForm.value,
  })
  if (ok) {
    rejectTarget.value = null
  }
}

async function openDetail(row: CaseRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('案件明细读取失败')
    }
    current.value = (await response.json()) as CaseRow
    assessTarget.value = null
    rejectTarget.value = null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '案件明细读取失败'
  }
}

async function refreshDetail() {
  if (!current.value) {
    return
  }
  const response = await request(`${ENDPOINT}/${current.value.id}`)
  if (response.ok) {
    current.value = (await response.json()) as CaseRow
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) {
    query.set('keyword', filters.value.keyword)
  }
  if (filters.value.status) {
    query.set('status', filters.value.status)
  }
  try {
    const [listResponse, allResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}?size=200`),
    ])
    if (!listResponse.ok) {
      throw new Error('保险案件列表读取失败')
    }
    const payload = (await listResponse.json()) as { items: CaseRow[]; total: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (allResponse.ok) {
      const allPayload = (await allResponse.json()) as { items: CaseRow[] }
      allRows.value = allPayload.items ?? []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保险案件列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.create-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.create-devices {
  flex: 1 1 100%;
}
.create-devices textarea {
  width: 100%;
  font-family: inherit;
}
.detail-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.detail-panel h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.detail-panel h4 {
  margin: 14px 0 8px;
  font-size: 13px;
}
.action-form {
  margin: 10px 0;
}
.notice-text {
  color: #067647;
}
</style>
