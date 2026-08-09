# Roadmap y Plan de Evolución - BrainBets

## Fecha: 2026-06-10
## Estado: Planificado

---

## Fase 1: PoC Funcional (COMPLETADO)

### Estado: ✅ Implementado
- File-based storage (JSON en disco)
- n8n workflows (Data Collection, Prediction, Validation)
- FastAPI backend (solo lectura, BFF)
- Vue.js dashboard (KPIs, predicciones, analytics)
- Docker Compose completo
- Datos dummy con fallback

---

## Fase 2: Multi-Modelo IA (Planificado - Q3 2026)

### Objetivo
Permitir integrar múltiples modelos de IA (OpenAI, Claude, Gemini, DeepSeek, etc.) sin cambiar lógica de negocio.

### Tareas
- [ ] Implementar patrón **Adapter** para integración IA
  ```
  src/infrastructure/ai/
  ├── adapters/
  │   ├── opencode_adapter.py
  │   ├── openai_adapter.py
  │   ├── claude_adapter.py
  │   └── gemini_adapter.py
  ├── ports/
  │   └── prediction_port.py  # Interfaz común
  └── factory.py              # Selección de adapter
  ```

- [ ] Nodo n8n "AI Adapter Selector":
  - Configuración de qué modelo usar
  - Fallback entre modelos si uno falla
  - Comparación de resultados entre modelos

- [ ] Ensemble de modelos:
  - Múltiples predicciones por partido (uno por modelo)
  - Votación ponderada o promedio de confianzas
  - Métricas de accuracy por modelo

- [ ] Dashboard actualizado:
  - Comparación de accuracy entre modelos
  - Selector de modelo activo
  - Historial de predicciones por modelo

### Tiempo Estimado: 3-4 semanas

---

## Fase 3: Sistema de Bankroll y Gestión (Planificado - Q4 2026)

### Objetivo
Añadir análisis financiero y gestión de riesgo para apuestas.

### Tareas
- [ ] **Bankroll management**:
  - Tracking de bankroll inicial
  - Historial de transacciones
  - Límites de apuesta por día/semana

- [ ] **Kelly Criterion**:
  - Cálculo de stake óptimo basado en confianza y odds
  - Fracción de Kelly (1/2, 1/4, full)
  - Integración con predicciones existentes

- [ ] **Simulación Monte Carlo**:
  - Simular 1000+ escenarios con bankroll inicial
  - Probabilidad de bancarrota (ruin)
  - Curva de equity esperada
  - Análisis de drawdown máximo

- [ ] **Dashboard financiero**:
  - KPIs: ROI, Yield, Profit/Loss
  - Curva de bankroll histórica
  - Gráficos de Monte Carlo
  - Tabla de stakes sugeridos

### Tiempo Estimado: 4-6 semanas

---

## Fase 4: Mobile y Notificaciones (Planificado - Q1 2027)

### Objetivo
Extender la plataforma a móviles y canales de mensajería.

### Tareas
- [ ] **Flutter mobile app**:
  - Replicar dashboard en móvil
  - Notificaciones push
  - Favoritos y alertas
  - Compartir predicciones

- [ ] **Telegram Bot interactivo**:
  - Comandos: `/matches`, `/predictions`, `/stats`
  - Suscripción a alertas por equipo/jugador
  - Consultar predicciones en tiempo real
  - Notificaciones de resultados

- [ ] **WhatsApp Business**:
  - Integración con WhatsApp Business API
  - Notificaciones de predicciones del día
  - Resumen de resultados

- [ ] **API pública** (opcional):
  - API key para desarrolladores
  - Rate limiting
  - Documentación Swagger

### Tiempo Estimado: 6-8 semanas

---

## Mejoras Continuas (Backlog)

### Testing y Calidad
- [ ] Tests unitarios backend (pytest, 80% coverage)
- [ ] Tests unitarios frontend (vitest)
- [ ] Tests de integración (n8n + backend + frontend)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Linting y formateo (ruff, black, prettier)

### Observabilidad
- [ ] Logs estructurados con rotación de archivos
- [ ] Métricas Prometheus (FastAPI)
- [ ] Dashboard Grafana (infra + negocio)
- [ ] Alertas (CPU, memoria, errores)

### Scraping Mejorado
- [ ] Implementar anti-detection (headers, proxies, delays)
- [ ] Rotación de user agents
- [ ] Manejo de captchas (si aparecen)
- [ ] Fallback entre fuentes (Flashscore → Sofascore → Fotmob)
- [ ] Caché de respuestas para reducir requests

### Datos Avanzados
- [ ] Estadísticas históricas de jugadores/equipos
- [ ] Análisis de tendencias (forma a largo plazo)
- [ ] Factores climáticos (fútbol al aire libre)
- [ ] Lesiones y bajas ( scraping de noticias)

### UX/UI
- [ ] Modo oscuro
- [ ] Gráficos interactivos (D3.js o Chart.js)
- [ ] Filtros avanzados en tablas
- [ ] Exportar datos a CSV/Excel
- [ ] Responsive design mejorado

### Seguridad
- [ ] Autenticación JWT (si se añade multi-usuario)
- [ ] Rate limiting en API
- [ ] HTTPS en producción
- [ ] CORS restringido
- [ ] Validación de inputs más estricta

---

## Migración de Infraestructura (Planificación a largo plazo)

### PostgreSQL (si se necesita)
**Criterios para migrar**:
- 100,000+ predicciones históricas
- 1,000+ usuarios concurrentes
- 1+ año de histórico

**Estrategia**:
- Adapter pattern para persistencia (FileSystemAdapter → PostgreSQLAdapter)
- Migración sin downtime (dual write → read from PG → remove files)
- TimescaleDB para series temporales (métricas)

### Kubernetes (si se necesita)
- Helm charts para despliegue
- HPA (Horizontal Pod Autoscaler)
- Ingress con Nginx
- Secrets management

---

## Métricas de Éxito

### Fase 1 (PoC)
- ✅ Stack funcional end-to-end
- ✅ < 500ms API response
- ✅ < 2s Dashboard load
- ✅ Docker Compose funcional

### Fase 2 (Multi-modelo)
- [ ] 2+ modelos de IA integrados
- [ ] Accuracy por modelo > 65%
- [ ] Ensemble accuracy > 70%
- [ ] Adapter funcional con tests

### Fase 3 (Bankroll)
- [ ] ROI simulado > 5% en Monte Carlo
- [ ] Kelly Criterion implementado
- [ ] Dashboard financiero funcional
- [ ] 0% bancarrota en simulación

### Fase 4 (Mobile)
- [ ] App en stores (Android/iOS)
- [ ] 100+ usuarios activos
- [ ] 50% engagement con Telegram bot
- [ ] 95% uptime

---

## Notas

- Todas las fases respetan la separación de capas definida en Fase 1
- La migración a PostgreSQL no requiere cambios en n8n ni frontend
- El patrón Adapter permite cambiar de modelo IA sin tocar lógica de negocio
- El sistema está diseñado para escalabilidad horizontal desde el inicio
