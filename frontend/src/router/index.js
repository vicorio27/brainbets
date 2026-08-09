import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Predictions from '../views/Predictions.vue'
import PredictionDetail from '../views/PredictionDetail.vue'
import Analytics from '../views/Analytics.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/predictions', component: Predictions },
  { path: '/predictions/:id', component: PredictionDetail, props: true },
  { path: '/analytics', component: Analytics }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
