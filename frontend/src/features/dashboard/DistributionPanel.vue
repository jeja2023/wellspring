<script setup lang="ts">
import { computed } from 'vue'
import { buildDonutSegments, colors, type Distribution } from './screen'

const props = withDefaults(
  defineProps<{
    title: string
    items: Distribution[]
    variant?: 'ring' | 'stacked'
  }>(),
  { variant: 'stacked' },
)

const total = computed(() => props.items.reduce((sum, item) => sum + item.value, 0))
const donut = computed(() => buildDonutSegments(props.items, 38))
const rows = computed(() =>
  props.items.map((item, index) => {
    const share = total.value ? (item.value / total.value) * 100 : 0
    return {
      ...item,
      color: colors[index % colors.length],
      share,
      shareText: total.value ? `${share >= 10 || share === 0 ? share.toFixed(0) : share.toFixed(1)}%` : '0%',
    }
  }),
)
</script>

<template>
  <section class="card screen-distribution" :class="'is-' + variant">
    <div class="screen-distribution-head">
      <h2>{{ title }}</h2>
      <span class="screen-distribution-badge">合计 {{ total.toLocaleString('zh-CN') }} 条</span>
    </div>

    <div v-if="!total" class="screen-distribution-empty">
      <svg v-if="variant === 'ring'" class="screen-donut-empty" viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="38" fill="none" stroke="var(--ws-border-default)" stroke-width="10" stroke-dasharray="4 4" />
      </svg>
      <p class="empty">暂无统计数据</p>
    </div>

    <div v-else-if="variant === 'ring'" class="screen-ring-body">
      <div class="screen-donut-wrap" aria-hidden="true">
        <svg viewBox="0 0 100 100" class="screen-donut-svg">
          <circle cx="50" cy="50" r="38" fill="none" stroke="var(--ws-bar-track)" stroke-width="11" />
          <circle
            v-for="seg in donut.segments"
            v-show="seg.value > 0"
            :key="seg.key"
            cx="50"
            cy="50"
            r="38"
            fill="none"
            :stroke="seg.color"
            stroke-width="11"
            stroke-linecap="butt"
            :stroke-dasharray="seg.dashArray"
            :stroke-dashoffset="seg.dashOffset"
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div class="screen-donut-center">
          <strong>{{ total.toLocaleString('zh-CN') }}</strong>
          <span>当前全量</span>
        </div>
      </div>
      <ul class="screen-dist-list">
        <li v-for="row in rows" :key="row.key">
          <div class="screen-dist-row-head">
            <span class="screen-dist-name"><i :style="{ background: row.color }"></i><span :title="row.label">{{ row.label }}</span></span>
            <span class="screen-dist-nums">
              <strong>{{ row.value.toLocaleString('zh-CN') }}</strong>
              <small>{{ row.shareText }}</small>
            </span>
          </div>
          <div class="screen-bar" aria-hidden="true">
            <span :style="{ width: row.share + '%', background: row.color }"></span>
          </div>
        </li>
      </ul>
    </div>

    <div v-else class="screen-stacked-body">
      <div class="screen-stacked-bar" aria-hidden="true">
        <span
          v-for="row in rows"
          v-show="row.value > 0"
          :key="'seg-' + row.key"
          :style="{ width: row.share + '%', background: row.color }"
        ></span>
      </div>
      <ul class="screen-dist-list is-compact">
        <li v-for="row in rows" :key="row.key">
          <div class="screen-dist-row-head">
            <span class="screen-dist-name"><i :style="{ background: row.color }"></i><span :title="row.label">{{ row.label }}</span></span>
            <span class="screen-dist-nums">
              <strong>{{ row.value.toLocaleString('zh-CN') }}</strong>
              <small>{{ row.shareText }}</small>
            </span>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>
