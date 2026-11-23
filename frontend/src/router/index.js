import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import MatchesHistory from '../views/MatchesHistory.vue'
import Predictions from '../views/Predictions.vue'
import PredictionDetail from '../views/PredictionDetail.vue'
import Analytics from '../views/Analytics.vue'
import Caja from '../views/Caja.vue'
import MyBets from '../views/MyBets.vue'
import Live from '../views/Live.vue'
import Football from '../views/Football.vue'
import FootballDetail from '../views/FootballDetail.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/matches', component: MatchesHistory },
  { path: '/predictions', component: Predictions },
  { path: '/predictions/:id', component: PredictionDetail, props: true },
  { path: '/analytics', component: Analytics },
  { path: '/caja', component: Caja },
  { path: '/mis-apuestas', component: MyBets },
  { path: '/en-vivo', component: Live },
  { path: '/futbol', component: Football },
  { path: '/futbol/:id', component: FootballDetail }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
