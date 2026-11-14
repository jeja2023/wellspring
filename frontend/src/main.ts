import { createApp } from 'vue'
import { applyThemeAttributes } from './app/theme'
import App from './App.vue'
import './styles/tokens.css'
import './style.css'

applyThemeAttributes()
createApp(App).mount('#app')
