# Анализ неиспользуемого кода

Дата анализа: 10 октября 2025

## 📊 Общая статистика

### ✅ Backend (Python) - api-service/
- **Всего функций:** 24
- **Неиспользуемых функций:** 1
- **Неиспользуемых переменных:** 1
- **Неиспользуемых импортов:** 0

### ✅ Frontend (React/TypeScript) - ui-react-service/
- **Неиспользуемых компонентов:** 0
- **Неиспользуемых полей интерфейсов:** 2
- **Неиспользуемых импортов:** 0

---

## 🔴 Найденные проблемы

### 1. Backend (api-service/analysis_api_hybrid.py)

#### ❌ Неиспользуемая функция `load_tu_prompts()` и переменная `TU_PROMPTS`

**Строки:** 96-116, 162

```python
def load_tu_prompts() -> Dict[str, str]:
    """Загружает предзагруженные ТУ для стадий ФЭ и ЭП."""
    # ... код загрузки файлов tu_fe.txt и tu_ep.txt
    
TU_PROMPTS = load_tu_prompts()  # Строка 162 - загружается, но нигде не используется
```

**Проблема:**
- Функция загружает файлы `prompts/tu_fe.txt` и `prompts/tu_ep.txt`
- Переменная `TU_PROMPTS` инициализируется, но НИКОГДА не используется в коде
- Файлы существуют и содержат типовые технические требования для стадий ФЭ и ЭП

**Рекомендация:**
- **Вариант 1 (удалить):** Если ТУ не нужны - удалить функцию, переменную и файлы `tu_fe.txt`, `tu_ep.txt`
- **Вариант 2 (использовать):** Интегрировать ТУ в процесс анализа (например, добавить их к требованиям из ТЗ)

---

### 2. Frontend (ui-react-service/src/)

#### ⚠️ Неиспользуемые поля интерфейсов

##### a) Поле `recommendations` в типе `Requirement`

**Файл:** `ui-react-service/src/types.ts:10`

```typescript
export interface Requirement {
    // ... другие поля
    recommendations: string;  // ❌ Никогда не используется во frontend
    // ...
}
```

**Проблема:**
- Поле определено в типе
- Backend возвращает это поле (заполняет при ошибках)
- Frontend НЕ отображает `recommendations` нигде в UI
- В компоненте `RequirementList.tsx` используются только: `status`, `confidence`, `solution_description`, `reference`, `discrepancies`

**Использование в backend:**
```python
# api-service/analysis_api_hybrid.py
recommendations="Проверьте вручную"        # строка 939
recommendations="Повторите анализ"         # строка 1004, 1070
recommendations="Переформулируйте..."     # строка 955
```

**Рекомендация:**
- **Вариант 1:** Отобразить `recommendations` в UI (например, в секции "Рекомендации")
- **Вариант 2:** Удалить поле из типа, если рекомендации не нужны пользователю

---

##### b) Поле `trace_id` в типах `Requirement` и `EditableRequirement`

**Файлы:** 
- `ui-react-service/src/types.ts:12`
- `ui-react-service/src/components/RequirementEditor.tsx:8`

```typescript
export interface Requirement {
    // ...
    trace_id?: string;  // ❌ Никогда не используется
}

export interface EditableRequirement {
    // ...
    trace_id?: string;  // ❌ Никогда не используется
}
```

**Проблема:**
- Поле определено, но нигде не используется в UI
- Backend передает это поле, но frontend его игнорирует
- Вероятно, использовалось для трассировки/отладки

**Рекомендация:**
- **Вариант 1:** Использовать для отладки (отображать в dev mode)
- **Вариант 2:** Удалить, если не нужно

---

## ✅ Проверенные элементы (используются корректно)

### Backend
- ✅ Все импорты используются:
  - `asyncio` → `asyncio.to_thread()` (4 вызова)
  - `HTTPException` → обработка ошибок (14 использований)
  - `RateLimitError` → обработка rate limit от OpenAI
  - `warnings` → отключение deprecation warnings

- ✅ Все функции используются:
  - `extract_selected_pdf_pages_as_images()` → используется в analyze_documentation
  - `_extract_page_texts_quick()` → текстовый префильтр
  - `_simple_candidate_pages()` → выбор кандидатов страниц
  - `find_contradictions()` → Stage 4 (опционально, управляется `STAGE4_ENABLED`)
  - `normalize_status_confidence()` → валидация данных от LLM

### Frontend
- ✅ Все компоненты используются:
  - `Header` → в App.tsx
  - `RequirementList` → в App.tsx
  - `PdfViewer` → в App.tsx
  - `RequirementEditor` → в App.tsx

- ✅ `reportWebVitals()` → вызывается в index.tsx

---

## 📋 Рекомендации по приоритетности

### Высокий приоритет (удалить/использовать)
1. ❌ **`TU_PROMPTS` + `load_tu_prompts()`** - точно неиспользуется, занимает память

### Средний приоритет (решить, нужно ли)
2. ⚠️ **`recommendations`** - backend генерирует, frontend игнорирует (можно показывать пользователю)

### Низкий приоритет (техдолг)
3. ⚠️ **`trace_id`** - может пригодиться для отладки

---

## 🛠️ Действия для очистки

### Если решено удалить неиспользуемое:

```bash
# 1. Удалить TU_PROMPTS
# В api-service/analysis_api_hybrid.py:
# - Удалить строки 96-116 (функция load_tu_prompts)
# - Удалить строку 162 (TU_PROMPTS = ...)

# 2. Удалить файлы ТУ
rm prompts/tu_fe.txt
rm prompts/tu_ep.txt

# 3. Удалить неиспользуемые поля (опционально)
# В ui-react-service/src/types.ts - удалить:
# - recommendations: string
# - trace_id?: string
```

---

## 📈 Итоговая оценка качества кода

- **Общая чистота кода:** ⭐⭐⭐⭐☆ (4/5)
- **Связность:** Отличная (все функции связаны, минимум мертвого кода)
- **Типизация:** Хорошая (TypeScript интерфейсы полные, но есть лишние поля)
- **Оптимизация:** Есть потенциал (TU_PROMPTS загружается зря)

**Вывод:** Код в целом чистый и хорошо организованный. Найдено минимальное количество неиспользуемых элементов, что говорит о качественном рефакторинге.
