# 📊 Анализ Status Bar системы

## 🔍 Как работает система прогресс-бара

### Архитектура

```
Frontend (Header.tsx)  →  Polling каждые 2 сек  →  Backend API
                                                     ├─ /extraction_status
                                                     └─ /status
```

---

## Frontend (Header.tsx)

### 1. **Состояния**
```typescript
const [loading, setLoading] = useState(false);
const [analysisProgress, setAnalysisProgress] = useState(0);
const [currentStage, setCurrentStage] = useState('');
const [realTimeStatus, setRealTimeStatus] = useState<any>(null);
const statusPollingRef = useRef<NodeJS.Timeout | null>(null);
```

### 2. **Логика Polling**

```typescript
useEffect(() => {
  if (loading) {
    const endpoint = currentStep === 1 ? 'extraction_status' : 'status';
    statusPollingRef.current = setInterval(() => fetchStatus(endpoint), 2000);
  } else {
    clearInterval(statusPollingRef.current);
    setRealTimeStatus(null);
    setAnalysisProgress(0);
    setCurrentStage('');
  }
}, [loading, currentStep]);
```

**Как работает:**
- ✅ При `loading = true` → запускается интервал каждые 2 сек
- ✅ Определяет endpoint по `currentStep`:
  - Шаг 1 (извлечение требований) → `/extraction_status`
  - Шаг 2 (анализ проекта) → `/status`
- ✅ При `loading = false` → останавливает polling, сбрасывает состояния
- ✅ Cleanup при unmount

### 3. **Функция fetchStatus**

```typescript
const fetchStatus = async (endpoint: string) => {
  try {
    const response = await axios.get(`${API_URL}/${endpoint}`);
    const data = response.data;
    
    setRealTimeStatus(data);
    setAnalysisProgress(data.progress || 0);
    setCurrentStage(data.stage_name || '');
  } catch (err) {
    console.error('Status fetch error:', err);
  }
};
```

**Проблема 1:** ❌ Ошибки игнорируются (только console.error)
**Проблема 2:** ❌ Нет обработки 404 (если endpoint не найден)

### 4. **UI отображение**

```jsx
{loading && (
  <div className="progress-container">
    <div className="progress-header">
      <span className="progress-title">🔄 Анализ в процессе</span>
      <span className="progress-percentage">{analysisProgress}%</span>
    </div>
    
    <div className="progress-bar">
      <div className="progress-fill" style={{ width: `${analysisProgress}%` }}>
        {/* Градиент меняется в зависимости от прогресса */}
      </div>
    </div>

    {/* Показываем статус если доступен */}
    {realTimeStatus && (
      <div className="progress-stage">
        <span className="stage-icon">{STAGE_ICONS[...]}</span>
        <span className="stage-text">
          Этап {realTimeStatus.current_stage}/{realTimeStatus.total_stages}: 
          {realTimeStatus.stage_name}
        </span>
      </div>
    )}
    
    {/* Дублирование! */}
    {currentStage && (
      <div className="progress-stage">
        <span className="stage-icon">📊</span>
        <span className="stage-text">{currentStage}</span>
      </div>
    )}
  </div>
)}
```

**Проблема 3:** ❌ Дублируется отображение статуса (realTimeStatus и currentStage одновременно)

---

## Backend (analysis_api_hybrid.py)

### 1. **Глобальные переменные статуса**

```python
# Для анализа проекта (/analyze)
analysis_status = {
    "current_stage": None,
    "progress": 0,
    "stage_name": "",
    "total_stages": 3,
    "start_time": None,
    "is_running": False
}

# Для извлечения требований (/extract_requirements)
extraction_status = {
    "current_stage": None,
    "progress": 0,
    "stage_name": "",
    "total_stages": 2,
    "start_time": None,
    "is_running": False
}
```

### 2. **Функции обновления**

```python
def update_analysis_status(stage_num: int, stage_name: str, progress: int):
    """Обновляет глобальный статус анализа"""
    analysis_status.update({
        "current_stage": stage_num,
        "progress": progress,
        "stage_name": stage_name,
    })
    logger.info(f"📊 Analysis status updated: Stage {stage_num}/3 - {stage_name} - {progress}%")

def update_extraction_status(stage_num: int, stage_name: str, progress: int):
    """Обновляет статус извлечения требований"""
    extraction_status.update({
        "current_stage": stage_num,
        "progress": progress,
        "stage_name": stage_name,
        "is_running": True
    })
    logger.info(f"📊 Extraction status updated: Stage {stage_num}/2 - {stage_name} - {progress}%")
```

### 3. **API Endpoints**

```python
@app.get("/status")
async def get_analysis_status():
    """Получить текущий статус анализа"""
    return analysis_status

@app.get("/extraction_status")
async def get_extraction_status():
    return extraction_status
```

---

## 🔴 КРИТИЧЕСКИЕ ОШИБКИ

### ❌ **Ошибка #1: НЕ ОБНОВЛЯЕТСЯ STATUS для извлечения требований**

**Код в `/extract_requirements`:**
```python
@app.post("/extract_requirements")
async def extract_requirements_endpoint(...):
    # ... извлечение требований ...
    # ❌ НИ РАЗУ НЕ ВЫЗЫВАЕТСЯ update_extraction_status()!
    
    logger.info("📄 Extracting text from TZ document...")
    tz_text = await extract_text_from_any(tz_content, tz_document.filename)
    
    logger.info("✂️ Segmenting requirements...")
    requirements = await segment_requirements(tz_text)
    
    return {"success": True, "requirements": requirements}
```

**Результат:**
- Frontend polling запрашивает `/extraction_status` каждые 2 сек
- Backend НИКОГДА не обновляет `extraction_status`
- Пользователь видит: **0% и пустой статус всё время** ❌

---

### ⚠️ **Ошибка #2: Прогресс в Stage 3 НЕ обновляется динамически**

**Код в `/analyze` (Stage 3):**
```python
# ЭТАП 6 [STAGE 3]: Группировка и анализ
update_analysis_status(3, "Детальный анализ требований", 70)  # ← Один раз 70%
analyzed_reqs = []

# Группируем требования по общим страницам
page_to_reqs = defaultdict(list)
# ... группировка ...

# Анализируем каждую группу
for group_idx, (pages_key, reqs_group) in enumerate(page_to_reqs.items(), 1):
    logger.info(f"📦 [STAGE 3] [{group_idx}/{len(page_to_reqs)}]...")
    
    # ❌ НЕТ update_analysis_status с динамическим прогрессом!
    
    batch_results = await analyze_batch_with_high_detail(...)
    analyzed_reqs.extend(batch_results)

# После ВСЕХ требований:
update_analysis_status(3, "Генерация отчета", 95)  # ← Скачок с 70% до 95%
```

**Результат:**
- Прогресс застревает на 70% надолго (самый долгий этап!)
- Пользователь не видит реальный прогресс анализа требований
- Внезапный скачок 70% → 95%

---

### ⚠️ **Ошибка #3: Дублирование отображения статуса**

**Frontend код:**
```jsx
{realTimeStatus && (
  <div className="progress-stage">
    Этап {realTimeStatus.current_stage}/{realTimeStatus.total_stages}: 
    {realTimeStatus.stage_name}
  </div>
)}

{currentStage && (  // ← Дублирование!
  <div className="progress-stage">
    {currentStage}
  </div>
)}
```

**Результат:**
- Показываются ДВА блока статуса одновременно
- `realTimeStatus.stage_name` и `currentStage` - это одно и то же
- Визуальный мусор

---

### ⚠️ **Ошибка #4: Нет обработки ошибок polling**

**Код:**
```typescript
const fetchStatus = async (endpoint: string) => {
  try {
    const response = await axios.get(`${API_URL}/${endpoint}`);
    // ...
  } catch (err) {
    console.error('Status fetch error:', err);  // ← Только лог!
  }
};
```

**Проблемы:**
- Если backend недоступен → пользователь не знает
- Если endpoint не существует → тихая ошибка
- Если timeout → тихая ошибка
- Polling продолжается бесконечно даже при ошибках

---

### ⚠️ **Ошибка #5: Некорректный total_stages**

**Backend:**
```python
analysis_status = {
    "total_stages": 3,  # ← Stage 1, 2, 3
    # ...
}
```

**Реальность:**
```python
# Stage 1: Извлечение метаданных (33%)
update_analysis_status(1, "Извлечение метаданных", 33)

# Stage 2: Оценка релевантности (40-66%)
update_analysis_status(2, "Оценка релевантности страниц", 40)
update_analysis_status(2, "Оценка релевантности страниц", 50)
update_analysis_status(2, "Оценка релевантности страниц", 60)
update_analysis_status(2, "Оценка релевантности страниц", 66)

# Stage 3: Детальный анализ (70-100%)
update_analysis_status(3, "Детальный анализ требований", 70)
update_analysis_status(3, "Генерация отчета", 95)
update_analysis_status(3, "Анализ завершен", 100)
```

**Проблема:** Stage 2 обновляется 4 раза подряд с разными процентами

---

## 📊 Распределение прогресса

### Текущее (проблемное):

| Stage | Progress Range | Description | Problem |
|-------|----------------|-------------|---------|
| 1 | 5% → 33% | Подготовка + Метаданные | ✅ OK |
| 2 | 40% → 66% | Оценка релевантности | ⚠️ 4 обновления подряд |
| 3 | 70% → 95% → 100% | Анализ требований | ❌ Долгий застой на 70% |

### Извлечение требований (НЕ работает):

| Stage | Progress | Description | Status |
|-------|----------|-------------|--------|
| 1 | ??? | Извлечение текста | ❌ Нет обновлений |
| 2 | ??? | Сегментация | ❌ Нет обновлений |

---

## 🎯 Таблица проблем

| # | Проблема | Критичность | Где |
|---|----------|-------------|-----|
| 1 | **НЕ обновляется extraction_status** | 🔴 КРИТИЧНО | Backend: /extract_requirements |
| 2 | **Прогресс застревает на 70%** | 🔴 КРИТИЧНО | Backend: Stage 3 loop |
| 3 | Дублирование UI статуса | 🟡 Средняя | Frontend: Header.tsx |
| 4 | Нет обработки ошибок polling | 🟡 Средняя | Frontend: fetchStatus |
| 5 | Некорректный total_stages | 🟢 Низкая | Backend: logic |
| 6 | Нет индикации connection loss | 🟡 Средняя | Frontend + Backend |

---

## 💡 Рекомендации по исправлению

### 1. **Добавить обновления в /extract_requirements**

```python
@app.post("/extract_requirements")
async def extract_requirements_endpoint(...):
    reset_extraction_status()
    update_extraction_status(1, "Извлечение текста из документа", 10)
    
    tz_text = await extract_text_from_any(tz_content, tz_document.filename)
    update_extraction_status(1, "Извлечение текста завершено", 50)
    
    update_extraction_status(2, "Сегментация требований", 60)
    requirements = await segment_requirements(tz_text)
    update_extraction_status(2, "Сегментация завершена", 100)
    
    return {"success": True, "requirements": requirements}
```

### 2. **Динамический прогресс в Stage 3**

```python
# В цикле анализа групп:
for group_idx, (pages_key, reqs_group) in enumerate(page_to_reqs.items(), 1):
    # Вычисляем прогресс: 70% + (0-25% в зависимости от группы)
    progress = 70 + int((group_idx / len(page_to_reqs)) * 25)
    update_analysis_status(
        3, 
        f"Анализ требований ({group_idx}/{len(page_to_reqs)} групп)", 
        progress
    )
    
    batch_results = await analyze_batch_with_high_detail(...)
    analyzed_reqs.extend(batch_results)
```

### 3. **Убрать дублирование UI**

```jsx
{realTimeStatus && (
  <div className="progress-stage">
    <span className="stage-icon">
      {STAGE_ICONS[realTimeStatus.current_stage] || '📊'}
    </span>
    <span className="stage-text">
      Этап {realTimeStatus.current_stage}/{realTimeStatus.total_stages}: 
      {realTimeStatus.stage_name}
    </span>
  </div>
)}

{/* Удалить этот блок ↓ */}
{/* {currentStage && <div>...</div>} */}
```

### 4. **Обработка ошибок polling**

```typescript
const [pollingErrors, setPollingErrors] = useState(0);

const fetchStatus = async (endpoint: string) => {
  try {
    const response = await axios.get(`${API_URL}/${endpoint}`);
    const data = response.data;
    
    setRealTimeStatus(data);
    setAnalysisProgress(data.progress || 0);
    setCurrentStage(data.stage_name || '');
    setPollingErrors(0); // Сброс счетчика
  } catch (err) {
    console.error('Status fetch error:', err);
    setPollingErrors(prev => prev + 1);
    
    // Останавливаем polling после 5 неудачных попыток
    if (pollingErrors >= 5) {
      if (statusPollingRef.current) {
        clearInterval(statusPollingRef.current);
      }
      setError('Потеряно соединение с сервером');
    }
  }
};
```

### 5. **Улучшить Stage 2 (меньше обновлений)**

```python
# Вместо 4 обновлений подряд:
update_analysis_status(2, "Оценка релевантности страниц", 40)
# ... extraction ...
update_analysis_status(2, "Оценка релевантности страниц", 60)
# ... assessment ...
update_analysis_status(2, "Оценка релевантности завершена", 66)
```

---

## 📈 Итоговая схема исправленного прогресса

```
/extract_requirements:
├─ 10%: Извлечение текста
├─ 50%: Извлечение завершено
├─ 60%: Сегментация
└─ 100%: Готово

/analyze:
├─ 5%: Подготовка данных
├─ 33%: Метаданные извлечены
├─ 40%: Оценка релевантности (начало)
├─ 60%: Оценка релевантности (конец)
├─ 70%: Stage 3 начало
├─ 70-95%: Stage 3 (динамически по группам)
├─ 95%: Генерация отчета
└─ 100%: Завершено
```

---

Дата анализа: 2025-10-13

