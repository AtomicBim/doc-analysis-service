/**
 * Утилиты для работы со ссылками на страницы в требованиях.
 * Выносит сложную логику парсинга из компонентов.
 */

export interface PageReference {
  page: number;  // PDF page number (порядковый номер для навигации)
  sheetNumber: string;  // Sheet number (реальный номер листа для отображения)
  description: string;
}

/**
 * Преобразует номер листа в номер PDF страницы используя mapping
 */
export function resolveSheetToPdfPage(
  sheetRef: string,
  sheetToPdfMapping: Record<string, number>
): number | null {
  // Ищем точное совпадение
  if (sheetToPdfMapping[sheetRef]) {
    return sheetToPdfMapping[sheetRef];
  }

  // Fallback: если это число, используем как есть
  const numericPage = parseInt(sheetRef, 10);
  if (!isNaN(numericPage) && numericPage > 0 && numericPage < 500) {
    return numericPage;
  }

  return null;
}

/**
 * Извлекает ссылки на страницы из поля reference (точные ссылки от API)
 * Для каждого листа ищет конкретный текст из решения
 */
export function extractReferencesFromField(
  referenceField: string,
  solution: string,
  sheetToPdfMapping: Record<string, number>
): PageReference[] {
  const references: PageReference[] = [];

  if (!referenceField || !referenceField.trim() || referenceField === '-') {
    return references;
  }

  // Парсим обозначения листов: "АР-01", "5", "КР-03.1" и т.д.
  const sheetRefs = referenceField.match(/[\w\d]+(?:[-–—.]\w*)*/g) || [];

  sheetRefs.forEach(sheetRef => {
    const pdfPageNum = resolveSheetToPdfPage(sheetRef, sheetToPdfMapping);

    if (pdfPageNum && !references.some(r => r.page === pdfPageNum)) {
      // Ищем конкретный текст для этого листа в решении
      const sheetSpecificText = extractSheetSpecificDescription(sheetRef, solution);

      references.push({
        page: pdfPageNum,
        sheetNumber: sheetRef,
        description: sheetSpecificText || `Упоминание листа ${sheetRef} в проектной документации`
      });
    }
  });

  return references;
}

/**
 * Извлекает описание, специфичное для конкретного листа
 * УЛУЧШЕНО: извлекает КОНКРЕТНЫЙ текст, который нужно искать на чертеже
 */
function extractSheetSpecificDescription(sheetRef: string, solution: string): string {
  // Нормализуем номер листа для поиска (убираем пробелы, приводим к нижнему регистру)
  const sheetRefNormalized = sheetRef.trim().replace(/\s+/g, '\\s*');

  // Паттерны для поиска текста после упоминания листа
  const patterns = [
    // 1. "на Листе АР-03: <текст>" или "Лист АР-03 - <текст>"
    new RegExp(`(?:на\\s+)?(?:лист[еа]?)\\s+${sheetRefNormalized}\\s*[:–—-]\\s*([^.;]{10,150})`, 'gi'),

    // 2. "Лист АР-03, где показано <текст>"
    new RegExp(`(?:лист[еа]?)\\s+${sheetRefNormalized}[,\\s]+(?:где|на котором|который показывает|содержащий|с указанием)\\s+([^.;]{10,150})`, 'gi'),

    // 3. "<текст> (Лист АР-03)"
    new RegExp(`([^.;(]{15,150})\\s*\\((?:лист[еа]?)\\s+${sheetRefNormalized}\\)`, 'gi'),

    // 4. "Лист АР-03 <текст до точки>"
    new RegExp(`(?:лист[еа]?)\\s+${sheetRefNormalized}[,\\s]+([^.;]{15,150})[.;]`, 'gi'),

    // 5. Текст ДО упоминания листа (для случаев типа "План 1 этажа Лист 5")
    new RegExp(`([А-ЯЁа-яё][А-ЯЁа-яё\\s\\d-]{10,100})\\s+(?:на\\s+)?(?:лист[еа]?)\\s+${sheetRefNormalized}`, 'gi')
  ];

  for (const pattern of patterns) {
    const matches = Array.from(solution.matchAll(pattern));
    if (matches.length > 0) {
      for (const match of matches) {
        let description = match[1]?.trim();
        if (!description) continue;

        // Очищаем от лишних символов в начале и конце
        description = description.replace(/^[-–—:,;\s()]+/, '').replace(/[-–—:,;\s()]+$/, '').trim();

        // Пропускаем слишком короткие или слишком общие описания
        if (description.length < 10) continue;
        if (/^(см\.|см|см\s+лист|лист|страница|стр)/i.test(description)) continue;

        // Извлекаем КЛЮЧЕВЫЕ СЛОВА для поиска (первые 3-5 значимых слов)
        const words = description.split(/\s+/);
        const significantWords = words.filter(w =>
          w.length > 3 &&
          !/^(и|в|на|с|по|для|или|также|а|но|от|до|из|при)$/i.test(w)
        );

        // Формируем компактное описание из ключевых слов
        let searchText = significantWords.slice(0, 5).join(' ');

        // Если searchText слишком длинный - обрезаем
        if (searchText.length > 80) {
          searchText = searchText.substring(0, 77) + '...';
        }

        // Если нашли хорошее описание - возвращаем
        if (searchText.length >= 10) {
          console.log(`✅ Извлечен текст для листа ${sheetRef}: "${searchText}"`);
          return searchText;
        }
      }
    }
  }

  // Fallback: если не нашли специфичный текст, ищем общий контекст
  const contextPattern = new RegExp(`.{0,30}${sheetRefNormalized}.{0,80}`, 'gi');
  const contextMatch = solution.match(contextPattern);
  if (contextMatch && contextMatch.length > 0) {
    let context = contextMatch[0].trim();

    // Убираем упоминание самого листа
    context = context.replace(new RegExp(`(?:на\\s+)?(?:лист[еа]?)\\s+${sheetRefNormalized}`, 'gi'), '').trim();
    context = context.replace(/^[-–—:,;\s()]+/, '').replace(/[-–—:,;\s()]+$/, '').trim();

    // Извлекаем значимые слова
    const words = context.split(/\s+/).filter(w =>
      w.length > 3 &&
      !/^(и|в|на|с|по|для|или|также|а|но|от|до|из|при)$/i.test(w)
    );

    if (words.length >= 2) {
      const searchText = words.slice(0, 5).join(' ');
      console.log(`⚠️ Fallback: извлечен контекст для листа ${sheetRef}: "${searchText}"`);
      return searchText.length > 80 ? searchText.substring(0, 77) + '...' : searchText;
    }
  }

  console.warn(`❌ Не удалось извлечь текст для поиска на листе ${sheetRef}`);
  return '';
}

/**
 * Извлекает ссылки на страницы из текста решения (дополнительные ссылки)
 */
export function extractReferencesFromSolution(
  solution: string,
  sheetToPdfMapping: Record<string, number>
): PageReference[] {
  const references: PageReference[] = [];

  // Regex для поиска упоминаний листов:
  // Захватывает: "лист 5", "Лист АР-03", "странице 26", "лист КР-05.1" и т.д.
  const pageRegex = /(?:на\s+)?(?:лист[е]?|страниц[ае])\s+([\w\d]+(?:[-–—.]\w*)*)\s*[-–—]?\s*([^.;]*(?:[.;][^;.]*?(?=(?:лист[е]?|страниц[ае]|[\w\d]+\s*[-–—]|$)))?)/gi;

  let match;
  while ((match = pageRegex.exec(solution)) !== null) {
    const sheetRef = match[1].trim();  // Может быть "5", "АР-03", "26" и т.д.
    let description = match[2] ? match[2].trim() : '';

    // Очищаем описание от лишних символов
    description = description.replace(/^[-–—:,;\s]+/, '').replace(/[;.,]+$/, '').trim();

    // Если описание пустое или слишком короткое, берем контекст после упоминания листа
    if (!description || description.length < 10) {
      const startIndex = match.index + match[0].length;
      const contextLength = 100;
      const endIndex = Math.min(startIndex + contextLength, solution.length);
      description = solution.substring(startIndex, endIndex).trim();

      // Обрезаем до конца предложения
      const sentenceEnd = description.search(/[.;]/);
      if (sentenceEnd !== -1) {
        description = description.substring(0, sentenceEnd).trim();
      }
    }

    // Если описание все еще слишком длинное, обрезаем
    if (description.length > 150) {
      description = description.substring(0, 147) + '...';
    }

    const pdfPageNum = resolveSheetToPdfPage(sheetRef, sheetToPdfMapping);

    if (pdfPageNum && !references.some(r => r.page === pdfPageNum)) {
      // Улучшаем description - извлекаем ключевые слова из контекста
      let betterDescription = description;
      if (!description || description.length < 20) {
        // Ищем существительные и технические термины рядом с упоминанием листа
        const context = solution.substring(Math.max(0, match.index - 50), match.index + 150);
        const keywords = context.match(/[А-ЯЁ][а-яё]+(?:\s+[а-яё]+){0,3}/g);
        if (keywords && keywords.length > 0) {
          betterDescription = keywords.slice(0, 3).join(', ');
        }
      }

      references.push({
        page: pdfPageNum,  // PDF page number для навигации
        sheetNumber: sheetRef,  // Реальный номер листа для отображения
        description: betterDescription || solution.substring(0, 80).trim()
      });
    }
  }

  return references;
}

/**
 * Основная функция для извлечения всех ссылок на страницы из требования
 */
export function extractPageReferences(
  solution: string,
  referenceField: string | undefined,
  sheetToPdfMapping: Record<string, number>
): PageReference[] {
  const references: PageReference[] = [];

  // СНАЧАЛА парсим поле reference - там точные ссылки от API
  references.push(...extractReferencesFromField(referenceField || '', solution, sheetToPdfMapping));

  // ПОТОМ парсим текст решения для дополнительных ссылок
  references.push(...extractReferencesFromSolution(solution, sheetToPdfMapping));

  // Если ничего не найдено - попробуем простой поиск числовых ссылок
  if (references.length === 0 && referenceField && referenceField !== '-') {
    console.log('⚠️ Regex не нашел ссылок, пробуем простой поиск в reference field');
    const simpleNumbers = referenceField.match(/\b\d{1,3}\b/g);
    if (simpleNumbers) {
      simpleNumbers.forEach(numStr => {
        const pageNum = parseInt(numStr, 10);
        if (pageNum > 0 && pageNum < 500 && !references.some(r => r.page === pageNum)) {
          references.push({
            page: pageNum,
            sheetNumber: numStr,
            description: solution.substring(0, 100).trim() + '...'
          });
        }
      });
    }
  }

  // Удаляем дубликаты по номеру страницы
  const uniqueRefs = references.filter((ref, index, self) =>
    index === self.findIndex(r => r.page === ref.page)
  );

  return uniqueRefs.sort((a, b) => a.page - b.page);
}
