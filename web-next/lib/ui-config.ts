/**
 * Konfiguracja stałych UI - timing, interwały, opóźnienia
 *
 * Wszystkie wartości czasowe w milisekundach.
 */

/**
 * Timing efektów wizualnych
 */
export const TYPING_EFFECT = {
  /** Opóźnienie między krokami efektu pisania (ms) */
  INTERVAL_MS: 20,
  /** Maksymalna liczba kroków dla efektu pisania */
  MAX_STEPS: 120,
} as const;

/**
 * Interwały pollingu i synchronizacji
 */
export const POLLING = {
  /** Interwał pollingu zadań (ms) */
  TASK_INTERVAL_MS: 2000,
  /** Interwał synchronizacji boot ID (ms) */
  BOOT_SYNC_INTERVAL_MS: 30000,
} as const;

/**
 * Timeouty powiadomień i komunikatów
 */
export const NOTIFICATIONS = {
  /** Czas wyświetlania komunikatu kopiowania (ms) */
  COPY_MESSAGE_TIMEOUT_MS: 2000,
  /** Czas wyświetlania toasta (ms) */
  TOAST_TIMEOUT_MS: 2500,
  /** Czas wyświetlania komunikatu kopiowania commita (ms) */
  COMMIT_COPY_TIMEOUT_MS: 1500,
  /** Czas wyświetlania komunikatu strategii (ms) */
  STRATEGY_TOAST_TIMEOUT_MS: 4000,
} as const;
