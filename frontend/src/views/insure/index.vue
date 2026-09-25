<template>
  <section class="page" data-module="insure">
    <header class="page-head">
      <div>
        <h2>财产保险管理</h2>
        <p class="page-desc">按设备编号登记出险报案，多台设备合并成一案后逐台定损，案件在已报案、定损中、待赔付、已结案之间流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记出险报案</button>
        <button class="btn" type="button" @click="exportRows">导出财产保险清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

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
        <tr v-for="row in rows" :key="row.id" :class="{ 'row-active': current?.id === row.id }">
          <td>{{ row.案件编号 }}</td>
          <td>{{ row.事故名称 }}</td>
          <td>{{ row.devices.length }} 台</td>
          <td>{{ fmtMoney(row.赔款合计) }}</td>
          <td>{{ row.报案人 }}</td>
          <td>{{ row.出险时间 }}</td>
          <td><span class="tag" :data-status="row.status">{{ row.status }}</span></td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in caseActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runCaseAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!caseActions(row).length" class="muted-text">已封存</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无财产保险案件，可先登记出险报案</td>
        </tr>
      </tbody>
    </table>

    <section v-if="current" class="detail-panel">
      <header class="detail-head">
        <h3>案件 {{ current.案件编号 }} · {{ current.事故名称 }}</h3>
        <button class="btn ghost" type="button" @click="current = null">收起</button>
      </header>

      <table class="data-table">
        <thead>
          <tr>
            <th>设备编号</th>
            <th>定损状态</th>
            <th>定损金额</th>
            <th>免赔比例</th>
            <th>赔款金额</th>
            <th>说明</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="dev in current.devices" :key="dev.设备编号">
            <td>{{ dev.设备编号 }}</td>
            <td><span class="tag" :data-status="dev.定损状态">{{ dev.定损状态 }}</span></td>
            <td>{{ fmtMoney(dev.定损金额) }}</td>
            <td>{{ fmtRatio(dev.免赔比例) }}</td>
            <td>{{ fmtMoney(dev.赔款金额) }}</td>
            <td>{{ dev.拒赔原因 || dev.免赔说明 || '—' }}</td>
            <td class="row-actions">
              <template v-if="current.status === '定损中'">
                <button class="link" type="button" @click="startAssess(dev)">定损</button>
                <button v-if="dev.定损状态 !== '已拒赔'" class="link" type="button" @click="startReject(dev)">拒赔</button>
              </template>
              <span v-else class="muted-text">—</span>
            </td>
          </tr>
        </tbody>
      </table>

      <form v-if="assessTarget" class="inline-form" @submit.prevent="submitAssess">
        <strong>逐台定损：{{ assessTarget }}</strong>
        <label>定损金额（元）<input v-model="assessForm.定损金额" type="number" min="0" step="0.01" placeholder="如 12000" /></label>
        <label>免赔比例（%）<input v-model="assessForm.免赔比例" type="number" min="0" max="100" step="0.01" placeholder="不填需写明原因" /></label>
        <label>免赔说明<input v-model="assessForm.免赔说明" placeholder="免赔比例没写清楚时，在此说明原因" /></label>
        <button class="btn primary" type="submit">确认定损</button>
        <button class="btn ghost" type="button" @click="assessTarget = ''">取消</button>
      </form>

      <form v-if="rejectTarget" class="inline-form" @submit.prevent="submitReject">
        <strong>拒赔：{{ rejectTarget }}</strong>
        <label>拒赔原因<input v-model="rejectReason" placeholder="拒赔只影响该设备，必须写明原因" /></label>
        <button class="btn primary" type="submit">确认拒赔</button>
        <button class="btn ghost" type="button" @click="rejectTarget = ''">取消</button>
      </form>

      <h4 class="log-title">流转记录</h4>
      <ul class="log-list">
        <li v-for="(log, index) in current.logs" :key="index">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-operator">{{ log.operator }}</span>
          <span class="log-action">{{ log.action }}</span>
          <span class="log-note">{{ log.note }}</span>
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条财产保险案件</span>
      <span v-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记出险报案</h3>
        <label class="form-item">
          <span>事故名称</span>
          <input v-model="createForm.事故名称" placeholder="如：暴雨导致信号机进水烧损" />
        </label>
        <label class="form-item">
          <span>出险时间</span>
          <input v-model="createForm.出险时间" type="datetime-local" />
        </label>
        <label class="form-item">
          <span>报案人</span>
          <input v-model="createForm.报案人" />
        </label>
        <label class="form-item">
          <span>设备编号（多台用逗号或换行分隔，合并为一案）</span>
          <textarea v-model="createForm.设备编号" rows="3" placeholder="如：SIGN-0001, SIGN-0002"></textarea>
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">提交报案</button>
          <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type DeviceRow = {
  设备编号: string
  定损状态: string
  定损金额: number | null
  免赔比例: number | null
  免赔说明: string
  赔款金额: number | null
  拒赔原因: string
}

type LogRow = { time: string; operator: string; action: string; note: string }

type CaseRow = {
  id: number
  案件编号: string
  事故名称: string
  出险时间: string
  报案人: string
  status: string
  devices: DeviceRow[]
  赔款合计: number
  logs: LogRow[]
}

type ActionPayload = { ok: boolean; message: string; entry: CaseRow | null }

const ENDPOINT = '/api/insure'
const columns = ['案件编号', '事故名称', '涉及设备', '赔款合计(元)', '报案人', '出险时间', '案件状态']
const statuses = ['已报案', '定损中', '待赔付', '已结案']
const CASE_ACTIONS: Record<string, string[]> = {
  已报案: ['转入定损'],
  定损中: ['提交理赔'],
  待赔付: ['确认结案'],
  已结案: [],
}

const store = useSessionStore()
const rows = ref<CaseRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', status: '' })
const current = ref<CaseRow | null>(null)
const assessTarget = ref('')
const assessForm = ref({ 定损金额: '', 免赔比例: '', 免赔说明: '' })
const rejectTarget = ref('')
const rejectReason = ref('')
const showCreate = ref(false)
const createError = ref('')
const createForm = ref({ 事故名称: '', 出险时间: '', 报案人: '', 设备编号: '' })

const stats = computed(() =>
  statuses.map((status) => ({
    label: `${status}案件`,
    value: rows.value.filter((row) => row.status === status).length,
  })),
)

function caseActions(row: CaseRow): string[] {
  return CASE_ACTIONS[row.status] ?? []
}

function fmtMoney(value: number | null): string {
  return value === null || value === undefined ? '—' : Number(value).toFixed(2)
}

function fmtRatio(value: number | null): string {
  return value === null || value === undefined ? '—' : `${Number(value)}%`
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {
    事故名称: '',
    出险时间: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16),
    报案人: store.operator,
    设备编号: '',
  }
  createError.value = ''
  showCreate.value = true
}

async function postAction(id: number, values: Record<string, unknown>): Promise<boolean> {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...values, operator: store.operator } }),
    })
    const payload = (await response.json()) as ActionPayload
    if (!payload.ok) {
      errorMessage.value = payload.message
      return false
    }
    noticeMessage.value = payload.message
    await reload()
    if (current.value) {
      await openDetail({ id } as CaseRow)
    }
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '财产保险操作失败'
    return false
  }
}

async function runCaseAction(action: string, row: CaseRow) {
  await postAction(row.id, { action })
}

async function openDetail(row: CaseRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('案件明细读取失败')
    }
    current.value = (await response.json()) as CaseRow
    assessTarget.value = ''
    rejectTarget.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '案件明细读取失败'
  }
}

function startAssess(dev: DeviceRow) {
  rejectTarget.value = ''
  assessTarget.value = dev.设备编号
  assessForm.value = {
    定损金额: dev.定损金额 === null ? '' : String(dev.定损金额),
    免赔比例: dev.免赔比例 === null ? '' : String(dev.免赔比例),
    免赔说明: dev.免赔说明 ?? '',
  }
}

async function submitAssess() {
  if (!current.value) {
    return
  }
  const ok = await postAction(current.value.id, {
    action: '逐台定损',
    设备编号: assessTarget.value,
    定损金额: assessForm.value.定损金额,
    免赔比例: assessForm.value.免赔比例,
    免赔说明: assessForm.value.免赔说明,
  })
  if (ok) {
    assessTarget.value = ''
  }
}

function startReject(dev: DeviceRow) {
  assessTarget.value = ''
  rejectTarget.value = dev.设备编号
  rejectReason.value = dev.拒赔原因 ?? ''
}

async function submitReject() {
  if (!current.value) {
    return
  }
  const ok = await postAction(current.value.id, {
    action: '拒赔',
    设备编号: rejectTarget.value,
    拒赔原因: rejectReason.value,
  })
  if (ok) {
    rejectTarget.value = ''
    rejectReason.value = ''
  }
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          事故名称: createForm.value.事故名称,
          出险时间: createForm.value.出险时间.replace('T', ' '),
          报案人: createForm.value.报案人,
          设备编号: createForm.value.设备编号,
        },
      }),
    })
    const payload = (await response.json()) as ActionPayload
    if (!payload.ok) {
      createError.value = payload.message
      return
    }
    showCreate.value = false
    noticeMessage.value = payload.message
    await reload()
    if (payload.entry) {
      await openDetail(payload.entry)
    }
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '出险报案登记失败'
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
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('保险案件列表读取失败')
    }
    const payload = (await response.json()) as { items: CaseRow[]; total: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保险案件列表读取失败'
  }
}

onMounted(reload)
</script>
