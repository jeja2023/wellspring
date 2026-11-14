<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
import { formatTimestamp } from '../../shared/time'
import Pagination from '../../shared/components/Pagination.vue'
import DistributionPanel from './DistributionPanel.vue'
import StatisticsDialog from './StatisticsDialog.vue'
import { areaPath, chartX, chartY, colors, linePath, seriesAxisMax, type ChartBox, type Distribution, type Overview } from './screen'
import './screen.css'

const { api, can } = useWorkspace()
const requests = createLatestRequests(api)
const board = ref<HTMLElement | null>(null)
const data = ref<Overview | null>(null)
const days = ref<7 | 30 | 90>(30)
const statisticsOpen = ref(false)
const loading = ref(false)
const error = ref('')
const fullscreen = ref(false)
const automatic = ref(false)
const seriesKey = ref('')
const trendMode = ref<'split' | 'combined'>('split')
const hoveredSeriesKey = ref('')
const dailyPage = ref(1)
const showDaily = ref(false)
const hoverIndex = ref<number | null>(null)
const sparkHoverIndex = ref<number | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const miniBox: ChartBox = { left: 26, top: 12, width: 314, height: 74 }
const wideBox: ChartBox = { left: 44, top: 24, width: 1012, height: 186 }

const allSeries = computed(() => data.value?.trend.series || [])
const series = computed(() => allSeries.value.filter((item) => !seriesKey.value || item.key === seriesKey.value))
const isSplitView = computed(() => !seriesKey.value && trendMode.value === 'split' && allSeries.value.length > 1)
const maximum = computed(() => seriesAxisMax(series.value.flatMap((item) => item.values), 3))
const dateTicks = computed(() => {
  const dates = data.value?.trend.dates || []
  return [...new Set([0, Math.floor((dates.length - 1) / 2), dates.length - 1])]
    .filter((i) => i >= 0)
    .map((index) => ({ index, label: dates[index]?.slice(5) }))
})
const dailyRows = computed(() => data.value?.trend.dates.map((date, index) => ({ date, index })).slice((dailyPage.value - 1) * 20, dailyPage.value * 20) || [])

function seriesColor(key: string): string {
  const index = allSeries.value.findIndex((row) => row.key === key)
  return colors[(index >= 0 ? index : 0) % colors.length]
}

function seriesTotal(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0)
}

function seriesPeak(values: number[]): number {
  return Math.max(0, ...values)
}

function selectModule(key: string) {
  seriesKey.value = seriesKey.value === key ? '' : key
  hoverIndex.value = null
  sparkHoverIndex.value = null
  hoveredSeriesKey.value = ''
}

const hoverX = computed(() => {
  const dates = data.value?.trend.dates || []
  if (hoverIndex.value === null || !dates.length) return null
  return chartX(hoverIndex.value, dates.length, wideBox)
})

const sparkHoverX = computed(() => {
  const dates = data.value?.trend.dates || []
  if (sparkHoverIndex.value === null || !dates.length) return null
  return chartX(sparkHoverIndex.value, dates.length, miniBox)
})

const hoverSummary = computed(() => {
  const dates = data.value?.trend.dates || []
  if (isSplitView.value) {
    if (sparkHoverIndex.value === null || !dates[sparkHoverIndex.value]) return ''
    return `${dates[sparkHoverIndex.value]} · 已同步各模块当日新增`
  }
  if (hoverIndex.value === null || !dates[hoverIndex.value]) return ''
  const parts = series.value.map((item) => `${item.label} ${item.values[hoverIndex.value!] ?? 0}`)
  return `${dates[hoverIndex.value]} · ${parts.join(' / ')}`
})

function bandWidth(box: ChartBox = wideBox) {
  const count = Math.max(1, data.value?.trend.dates.length || 1)
  return box.width / count
}

function bandX(index: number, box: ChartBox = wideBox) {
  const dates = data.value?.trend.dates || []
  return chartX(index, dates.length, box) - bandWidth(box) / 2
}

const distributionPanels = computed(() => {
  const breakdowns = data.value?.breakdowns
  if (!breakdowns) return [] as Array<{ key: string; title: string; items: Distribution[]; variant: 'ring' | 'stacked' }>
  const raw: Array<{ key: string; title: string; items: Distribution[] | undefined }> = [
    { key: 'intake', title: '接警类型分布', items: breakdowns.intake },
    { key: 'tasks', title: '核查工单状态', items: breakdowns.tasks },
    { key: 'models', title: '业务模型状态', items: breakdowns.models },
    { key: 'results', title: '污水检测复核状态', items: breakdowns.results },
    { key: 'sites', title: '采样点运行状态', items: breakdowns.sites },
  ]
  const visible = raw.filter((item): item is { key: string; title: string; items: Distribution[] } => Boolean(item.items))
  return visible.map((item, index) => ({
    ...item,
    variant: (visible.length <= 2 || (visible.length >= 4 && index < 2) ? 'ring' : 'stacked') as 'ring' | 'stacked',
  }))
})

async function load(target = days.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await requests.latest<Overview>('overview', `/dashboard/overview?days=${target}`)
    data.value = result
    days.value = result.range.days
    dailyPage.value = 1
    hoverIndex.value = null
  } catch (e) {
    if (!isCancelled(e)) error.value = e instanceof Error ? e.message : '统计加载失败'
  } finally {
    loading.value = false
  }
}

async function toggleFullscreen() {
  error.value = ''
  try {
    if (document.fullscreenElement === board.value) await document.exitFullscreen()
    else if (board.value?.requestFullscreen) await board.value.requestFullscreen()
    else error.value = '当前浏览器不支持全屏展示'
  } catch {
    error.value = '无法进入全屏，请检查浏览器设置'
  }
}

function fullscreenChanged() {
  fullscreen.value = document.fullscreenElement === board.value
}

onMounted(() => {
  void load()
  document.addEventListener('fullscreenchange', fullscreenChanged)
  refreshTimer = setInterval(() => {
    if (automatic.value && !loading.value && !statisticsOpen.value && !document.hidden) void load()
  }, 60000)
})

onBeforeUnmount(() => {
  requests.dispose()
  clearInterval(refreshTimer)
  document.removeEventListener('fullscreenchange', fullscreenChanged)
  if (document.fullscreenElement === board.value) void document.exitFullscreen()
})
</script>

<template>
  <div ref="board" class="data-screen" :class="{ 'is-fullscreen': fullscreen }">
    <section class="card screen-toolbar">
      <div class="screen-identity">
        <strong>{{ data?.organization || '当前组织' }}</strong>
        <span class="muted screen-updated">{{ data ? '更新于 ' + formatTimestamp(data.generated_at) : '综合业务统计' }}</span>
      </div>
      <div class="screen-controls">
        <label>
          新增统计周期
          <select :value="days" :disabled="loading" @change="load(Number(($event.target as HTMLSelectElement).value) as 7 | 30 | 90)">
            <option :value="7">近 7 天</option>
            <option :value="30">近 30 天</option>
            <option :value="90">近 90 天</option>
          </select>
        </label>
        <label class="check-label"><input v-model="automatic" type="checkbox" />每分钟刷新</label>
        <button class="secondary" :disabled="loading" @click="load()">{{ loading ? '更新中…' : '刷新数据' }}</button>
        <button v-if="can('ai.read') && can('ai.generate')" class="secondary" :disabled="loading || !data?.metrics.length" @click="statisticsOpen = true">
          AI 统计解读
        </button>
        <button class="secondary" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '全屏展示' }}</button>
      </div>
    </section>
    <p v-if="error" class="error" role="alert">{{ error }} <span v-if="data">当前仍显示上次成功获取的数据。</span></p>
    <p v-if="loading && !data" class="card muted" role="status">正在汇总授权范围内的数据…</p>
    <template v-if="data">
      <div v-if="!data.metrics.length" class="card empty">当前角色没有可统计的业务模块权限，请联系管理员。</div>
      <div class="screen-metrics">
        <div v-for="(metric, index) in data.metrics" :key="metric.key" class="card screen-metric" :style="{ '--metric-color': colors[index % colors.length] }">
          <span>{{ metric.label }}</span>
          <div>
            <strong>{{ metric.total.toLocaleString('zh-CN') }}</strong>
            <small>{{ metric.unit }}</small>
          </div>
          <p>近 {{ data.range.days }} 天新增 <b>{{ metric.period_count.toLocaleString('zh-CN') }}</b></p>
        </div>
      </div>
      <section v-if="data.metrics.length" class="card screen-trend">
        <div class="page-toolbar">
          <div class="screen-trend-heading">
            <h2>业务新增趋势</h2>
            <p class="muted">{{ data.range.start_date }} 至 {{ data.range.end_date }} · 按北京时间的记录创建日期统计</p>
          </div>
          <div class="screen-trend-tools">
            <span v-if="hoverSummary" class="screen-hover-readout">{{ hoverSummary }}</span>
            <div v-if="allSeries.length > 1" class="screen-view-switch" role="group" aria-label="趋势视图切换">
              <button
                type="button"
                class="screen-switch-btn"
                :class="{ active: isSplitView }"
                @click="seriesKey = ''; trendMode = 'split'"
              >
                分项趋势
              </button>
              <button
                type="button"
                class="screen-switch-btn"
                :class="{ active: !seriesKey && trendMode === 'combined' }"
                @click="seriesKey = ''; trendMode = 'combined'"
              >
                叠加对比
              </button>
            </div>
            <label>
              查看模块
              <select v-model="seriesKey">
                <option value="">全部授权模块</option>
                <option v-for="item in data.trend.series" :key="item.key" :value="item.key">{{ item.label }}</option>
              </select>
            </label>
          </div>
        </div>

        <div class="screen-legend">
          <div class="screen-legend-items">
            <button
              v-for="item in allSeries"
              :key="item.key"
              type="button"
              class="screen-legend-chip"
              :class="{ active: seriesKey === item.key, muted: Boolean(seriesKey) && seriesKey !== item.key }"
              @mouseenter="!isSplitView ? (hoveredSeriesKey = item.key) : undefined"
              @mouseleave="hoveredSeriesKey = ''"
              @click="selectModule(item.key)"
            >
              <i :style="{ background: seriesColor(item.key) }"></i>
              <span>{{ item.label }}</span>
              <em>{{ seriesTotal(item.values) }}</em>
            </button>
          </div>
          <button class="link" type="button" @click="showDaily = !showDaily">{{ showDaily ? '收起每日数据' : '查看每日数据' }}</button>
        </div>

        <div v-if="isSplitView" class="screen-small-multiples" @mouseleave="sparkHoverIndex = null">
          <article
            v-for="item in allSeries"
            :key="'mini-' + item.key"
            class="screen-mini-card"
            tabindex="0"
            @click="selectModule(item.key)"
            @keydown.enter.prevent="selectModule(item.key)"
          >
            <header class="screen-mini-head">
              <div class="screen-mini-title">
                <i :style="{ background: seriesColor(item.key) }"></i>
                <strong>{{ item.label }}</strong>
              </div>
              <div class="screen-mini-stats">
                <span v-if="sparkHoverIndex !== null" class="screen-mini-hover-val" :style="{ color: seriesColor(item.key) }">
                  {{ data.trend.dates[sparkHoverIndex]?.slice(5) }} 新增 {{ item.values[sparkHoverIndex] ?? 0 }}
                </span>
                <template v-else>
                  <span class="screen-mini-total">{{ seriesTotal(item.values) }} 条</span>
                  <span class="screen-mini-peak">峰值 {{ seriesPeak(item.values) }}</span>
                </template>
              </div>
            </header>
            <svg viewBox="0 0 360 108" class="screen-mini-svg" role="img" :aria-label="item.label + '新增趋势'">
              <defs>
                <linearGradient :id="'mini-grad-' + item.key" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" :stop-color="seriesColor(item.key)" stop-opacity="0.22" />
                  <stop offset="100%" :stop-color="seriesColor(item.key)" stop-opacity="0.01" />
                </linearGradient>
              </defs>
              <g v-for="tick in [0, 1, 2]" :key="tick">
                <line
                  :x1="miniBox.left"
                  :x2="miniBox.left + miniBox.width"
                  :y1="miniBox.top + miniBox.height - (tick * miniBox.height) / 2"
                  :y2="miniBox.top + miniBox.height - (tick * miniBox.height) / 2"
                  class="screen-grid-line"
                />
                <text
                  :x="miniBox.left - 6"
                  :y="miniBox.top + miniBox.height - (tick * miniBox.height) / 2 + 3"
                  text-anchor="end"
                  class="screen-mini-axis"
                >
                  {{ Math.round((seriesAxisMax(item.values, 2) * tick) / 2) }}
                </text>
              </g>
              <line
                v-if="sparkHoverX !== null"
                :x1="sparkHoverX"
                :x2="sparkHoverX"
                :y1="miniBox.top"
                :y2="miniBox.top + miniBox.height"
                class="screen-crosshair"
              />
              <path
                :d="areaPath(item.values, seriesAxisMax(item.values, 2), miniBox)"
                :fill="'url(#mini-grad-' + item.key + ')'"
              />
              <path
                :d="linePath(item.values, seriesAxisMax(item.values, 2), miniBox)"
                fill="none"
                :stroke="seriesColor(item.key)"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <circle
                v-if="sparkHoverIndex !== null && sparkHoverX !== null"
                :cx="sparkHoverX"
                :cy="chartY(item.values[sparkHoverIndex] ?? 0, seriesAxisMax(item.values, 2), miniBox)"
                r="4"
                fill="var(--ws-bg-surface)"
                :stroke="seriesColor(item.key)"
                stroke-width="2.2"
              />
              <rect
                v-for="(_, index) in data.trend.dates"
                :key="'mini-band-' + item.key + '-' + index"
                :x="bandX(index, miniBox)"
                :y="miniBox.top - 4"
                :width="bandWidth(miniBox)"
                :height="miniBox.height + 10"
                class="screen-hit-band"
                @mouseenter="sparkHoverIndex = index"
              />
              <text
                v-for="tick in dateTicks"
                :key="'mini-tick-' + tick.index"
                :x="chartX(tick.index, data.trend.dates.length, miniBox)"
                y="102"
                text-anchor="middle"
                class="screen-mini-axis"
              >
                {{ tick.label }}
              </text>
            </svg>
          </article>
        </div>

        <div v-else class="screen-chart" @mouseleave="hoverIndex = null">
          <svg viewBox="0 0 1080 248" role="img" aria-label="各业务模块每天新增记录折线图">
            <title>各业务模块每天新增记录；准确数值可在下方每日数据表查看</title>
            <defs>
              <linearGradient
                v-for="item in series"
                :id="'grad-' + item.key"
                :key="'grad-' + item.key"
                x1="0"
                x2="0"
                y1="0"
                y2="1"
              >
                <stop offset="0%" :stop-color="seriesColor(item.key)" stop-opacity="0.2" />
                <stop offset="100%" :stop-color="seriesColor(item.key)" stop-opacity="0" />
              </linearGradient>
            </defs>
            <g v-for="tick in [0, 1, 2, 3]" :key="tick">
              <line
                :x1="wideBox.left"
                :x2="wideBox.left + wideBox.width"
                :y1="wideBox.top + wideBox.height - (tick * wideBox.height) / 3"
                :y2="wideBox.top + wideBox.height - (tick * wideBox.height) / 3"
                class="screen-grid-line"
              />
              <text
                :x="wideBox.left - 10"
                :y="wideBox.top + wideBox.height - (tick * wideBox.height) / 3 + 4"
                text-anchor="end"
              >
                {{ Math.round((maximum * tick) / 3) }}
              </text>
            </g>
            <line
              v-if="hoverX !== null"
              :x1="hoverX"
              :x2="hoverX"
              :y1="wideBox.top"
              :y2="wideBox.top + wideBox.height"
              class="screen-crosshair"
            />
            <path
              v-for="item in series"
              v-show="series.length === 1 || hoveredSeriesKey === item.key"
              :key="'area-' + item.key"
              :d="areaPath(item.values, maximum, wideBox)"
              :fill="'url(#grad-' + item.key + ')'"
            />
            <path
              v-for="item in series"
              :key="item.key"
              :d="linePath(item.values, maximum, wideBox)"
              fill="none"
              :stroke="seriesColor(item.key)"
              :stroke-width="series.length === 1 || hoveredSeriesKey === item.key ? 2.8 : 2.1"
              :stroke-opacity="!hoveredSeriesKey || hoveredSeriesKey === item.key ? 1 : 0.22"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <g v-if="hoverIndex !== null && hoverX !== null">
              <circle
                v-for="item in series"
                :key="'dot-' + item.key"
                :cx="hoverX"
                :cy="chartY(item.values[hoverIndex] ?? 0, maximum, wideBox)"
                r="4.5"
                fill="var(--ws-bg-surface)"
                :stroke="seriesColor(item.key)"
                :opacity="!hoveredSeriesKey || hoveredSeriesKey === item.key ? 1 : 0.25"
                stroke-width="2.5"
              />
            </g>
            <rect
              v-for="(_, index) in data.trend.dates"
              :key="'band-' + index"
              :x="bandX(index, wideBox)"
              :y="wideBox.top - 4"
              :width="bandWidth(wideBox)"
              :height="wideBox.height + 12"
              class="screen-hit-band"
              @mouseenter="hoverIndex = index"
            />
            <text
              v-for="tick in dateTicks"
              :key="tick.index"
              :x="chartX(tick.index, data.trend.dates.length, wideBox)"
              y="236"
              text-anchor="middle"
            >
              {{ tick.label }}
            </text>
          </svg>
        </div>
        <template v-if="showDaily">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col" class="row-number">序号</th>
                  <th scope="col">日期</th>
                  <th v-for="item in data.trend.series" :key="item.key" scope="col">{{ item.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in dailyRows" :key="row.date">
                  <td class="row-number">{{ row.index + 1 }}</td>
                  <td>{{ row.date }}</td>
                  <td v-for="item in data.trend.series" :key="item.key">{{ item.values[row.index] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <Pagination :page="dailyPage" :total="data.trend.dates.length" @change="dailyPage = $event" />
        </template>
      </section>
      <div class="screen-distributions" :data-count="distributionPanels.length">
        <DistributionPanel
          v-for="panel in distributionPanels"
          :key="panel.key"
          :title="panel.title"
          :items="panel.items"
          :variant="panel.variant"
        />
      </div>
    </template>
    <StatisticsDialog :open="statisticsOpen" :days="days" :organization="data?.organization || '当前组织'" @close="statisticsOpen = false" />
  </div>
</template>
