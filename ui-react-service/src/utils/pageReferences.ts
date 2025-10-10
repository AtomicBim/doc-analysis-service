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
 */
function extractSheetSpecificDescription(sheetRef: string, solution: string): string {
  // Ищем упоминания конкретного листа в тексте решения
  const patterns = [
    // Прямые упоминания типа "на Листе 10", "Лист 10", "лист 10"
    new RegExp(`(?:на\\s+)?(?:лист[е]?|страниц[ае])\\s+${sheetRef}\\s*([^.;]*(?:[.;][^;.]*?(?=(?:лист[е]?|страниц[ае]|$)))?)`, 'gi'),
    // Упоминания в скобках типа "(Лист 10)"
    new RegExp(`\\(Лист\\s+${sheetRef}[^)]*\\)`, 'gi'),
    // Упоминания с ссылками типа "Лист 10 и Лист 11"
    new RegExp(`Лист\\s+${sheetRef}(?:\\s+и\\s+Лист\\s+\\d+)?\\s*([^.;]*(?:[.;][^;.]*?(?=(?:лист[е]?|страниц[ае]|$)))?)`, 'gi')
  ];

  for (const pattern of patterns) {
    const matches = solution.match(pattern);
    if (matches && matches.length > 0) {
      // Берем первое найденное совпадение и очищаем его
      let description = matches[0].trim();

      // Убираем префикс с номером листа, оставляем только описание
      description = description.replace(new RegExp(`^(?:на\\s+)?(?:лист[е]?|страниц[ае])\\s+${sheetRef}\\s*[-–—]?\\s*`, 'i'), '');
      description = description.replace(/^\(Лист\s+\d+[^)]*\)/, '');
      description = description.replace(/^Лист\s+\d+(?:\s+и\s+Лист\s+\d+)?\s*/, '');

      // Очищаем от лишних символов
      description = description.replace(/^[-–—:,;\s]+/, '').replace(/[;.,]+$/, '').trim();

      if (description && description.length > 10) {
        // Обрезаем если слишком длинное
        if (description.length > 150) {
          description = description.substring(0, 147) + '...';
        }
        return description;
      }
    }
  }

  // Если не нашли специфичный текст, ищем ближайший контекст вокруг упоминания листа
  const contextPattern = new RegExp(`.{0,50}${sheetRef}.{0,100}`, 'gi');
  const contextMatch = solution.match(contextPattern);
  if (contextMatch && contextMatch.length > 0) {
    let context = contextMatch[0].trim();
    // Убираем упоминание самого листа и берем текст после него
    const sheetIndex = context.toLowerCase().indexOf(sheetRef.toLowerCase());
    if (sheetIndex !== -1) {
      context = context.substring(sheetIndex + sheetRef.length).trim();
      context = context.replace(/^[-–—:,;\s]+/, '').replace(/[;.,]+$/, '').trim();

      if (context && context.length > 10) {
        return context.length > 150 ? context.substring(0, 147) + '...' : context;
      }
    }
  }

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
