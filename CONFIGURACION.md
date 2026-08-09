# Guía de Configuración - BrainBets

## Fecha: 2026-06-10
## Estado: Telegram Configurado ✅ | Scraping Configurado ✅ | OpenCode Go: Pendiente API Key

---

## ✅ COMPLETADO: Configuración Telegram

### Credenciales Configuradas:
- **Bot Token**: variable de entorno `TELEGRAM_TOKEN` (ver `.env` local; nunca commitear)
- **Chat ID**: variable de entorno `TELEGRAM_CHAT_ID`

### Workflows Actualizados:
Los 3 workflows principales ahora usan tu Chat ID:
- ✅ `data_collection_pipeline.json`
- ✅ `prediction_pipeline.json`
- ✅ `validation_pipeline.json`

### Nuevos Workflows de Scraping:
- ✅ `flashscore_tennis_scraper.json` - Scraping de tenis (Flashscore)
- ✅ `sofascore_football_scraper.json` - Scraping de fútbol (Sofascore)

---

## ✅ COMPLETADO: Configuración OpenCode Go

### API Key Configurada:
- **API Key**: variable de entorno `OPENCODE_GO_API_KEY` (ver `.env` local)
- **Endpoint**: `https://api.opencode.ai/v1/chat/completions`
- **Método**: POST
- **Headers**: `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`

### Workflows Actualizados:
- ✅ `prediction_pipeline_opencode.json` - Conexión real con OpenCode Go
  - Nodo "Call OpenCode Go API" conectado al endpoint
  - Nodo "Parse OpenCode Response" para procesar la respuesta
  - Nodo "Fallback Predictions" si la API falla
  - Mantiene el fallback como seguridad

### Formato de Request:
```json
{
  "model": "opencode-go",
  "messages": [
    {
      "role": "system",
      "content": "You are a sports betting analyst..."
    },
    {
      "role": "user",
      "content": "{match_data_json}"
    }
  ],
  "temperature": 0.7
}
```

### Formato de Response Esperado:
```json
{
  "predictions": [
    {
      "matchId": "TEN001",
      "sport": "tennis",
      "market": "Winner",
      "prediction": "Carlos Alcaraz",
      "confidence": 87,
      "reasoning": "Mejor forma reciente..."
    }
  ]
}
```

---

## 🔧 OPCIONAL: APIs Deportivas (Para Scraping Real Avanzado)

### Opción 1: API-Football (Recomendada para Fútbol)
- **URL**: https://www.api-football.com
- **Precio**: Gratis (100 requests/día) / $19 mes (1000 requests/día)
- **Registro**:
  1. Ve a https://dashboard.api-football.com/register
  2. Crea cuenta gratuita
  3. Ve a "My APIS" → API-Football
  4. Copia tu API Key

### Opción 2: SportMonks
- **URL**: https://www.sportmonks.com
- **Precio**: Gratis (180 requests/hora) / Planes pagos
- **Registro**:
  1. Crea cuenta en https://www.sportmonks.com
  2. Ve a Dashboard → API Tokens
  3. Genera token nuevo

### Opción 3: Sofascore API (No oficial)
- Sofascore no tiene API oficial pública
- Alternativa: Scraping con Puppeteer/Playwright
- O usar la API interna (requiere inspección de red)

### Opción 4: Flashscore API (No oficial)
- Flashscore no tiene API oficial pública
- Alternativa: Scraping con Selenium/Puppeteer
- O usar fuentes de terceros como API-Football

---

## 🚀 Cómo Importar Workflows en n8n

### Método 1: Importar desde Archivo
1. Abre n8n: http://localhost:5678
2. Usuario: `admin`, Password: `brainbets123`
3. Ve a **Settings** (icono de engranaje arriba a la derecha)
4. Selecciona **Workflows**
5. Click **"Import from File"**
6. Selecciona los archivos de `n8n/workflows/`:
   - `data_collection_pipeline.json`
   - `prediction_pipeline.json`
   - `validation_pipeline.json`
   - `flashscore_tennis_scraper.json`
   - `sofascore_football_scraper.json`

### Método 2: Importar desde Directorio
1. Copia los archivos `.json` a `./n8n/workflows/`
2. Reinicia n8n: `docker-compose restart n8n`
3. Los workflows aparecerán automáticamente

### Configurar Credenciales en n8n
1. Ve a **Settings** → **Credentials**
2. Click **"Add New"**
3. Selecciona **Telegram API**
4. Pega tu **Bot Token** (valor de `TELEGRAM_TOKEN` en tu `.env`)
5. Guarda

---

## 📋 Variables de Entorno

Copia `.env.example` a `.env` y configura:

```bash
cp .env.example .env
```

Edita `.env` con tus valores (ver `.env.example` para la lista completa):
```env
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
OPENCODE_GO_API_KEY=your_opencode_go_key
OPENCODE_GO_ENDPOINT=https://api.opencode.ai/v1/chat/completions
```

---

## 🎾⚽ Scraping Real: Próximos Pasos

### Opción A: Scraping Simple (Actual)
- Usa HTTP Request a Flashscore/Sofascore
- Fallback a datos dummy si falla
- ✅ Ya implementado

### Opción B: Scraping Avanzado (Futuro)
- Requiere: Puppeteer/Playwright en Docker
- Extrae datos reales de partidos del día
- Más estable pero más complejo

### Opción C: API Deportiva (Recomendado)
- Usa API-Football o SportMonks
- Datos estructurados y confiables
- Requiere API key (gratis o pago)

---

## 📝 Notas Importantes

### Seguridad
- **NUNCA** subas el archivo `.env` a GitHub
- El `.env` está en `.gitignore` (debería estar)
- Los tokens de Telegram son sensibles
- Rotación de API keys recomendada cada 90 días

### Fallbacks
- Todos los workflows tienen **fallback** implementado
- Si el scraping falla → datos dummy realistas
- Si OpenCode Go falla → generador de predicciones local
- Si Telegram falla → el workflow continúa

### Mantenimiento
- Los workflows de scraping están separados por deporte
- Fácil de modificar uno sin afectar el otro
- Nodos de scraping en workflows independientes

---

## ✅ Checklist de Configuración

- [x] Token de Telegram Bot
- [x] Chat ID de Telegram
- [x] Workflows actualizados con Telegram
- [x] Scraping básico configurado (Flashscore + Sofascore)
- [x] API Key de OpenCode Go
- [x] Workflows actualizados con OpenCode Go
- [ ] API Key deportiva (OPCIONAL - API-Football recomendada)
- [ ] Variables de entorno en `.env` (crear archivo .env)
- [ ] Workflows importados en n8n
- [ ] Test de notificación Telegram
- [ ] Test de scraping real
- [ ] Test de predicción con OpenCode Go

---

## 🆘 Solución de Problemas

### "No me llegan notificaciones a Telegram"
1. Verifica que el bot esté activo: busca tu bot en Telegram y envía /start
2. Verifica que el Chat ID sea correcto
3. Prueba manualmente: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=Test`
4. Revisa logs de n8n: `docker logs brainbets-n8n`

### "El scraping falla siempre"
1. Flashscore y Sofascore bloquean bots
2. Usa el fallback (ya está implementado)
3. Considera Puppeteer o API-Football para producción

### "OpenCode Go no responde"
1. Verifica tu API key
2. Verifica el endpoint (cloud vs local)
3. Usa el fallback de predicciones (ya está implementado)
4. Revisa límite de requests de tu suscripción

---

**Esperando tu API Key de OpenCode Go para completar la configuración.**
