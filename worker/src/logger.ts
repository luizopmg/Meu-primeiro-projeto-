type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
let currentLevel: LogLevel = 'info';

export function setLogLevel(level: LogLevel) { currentLevel = level; }

export function log(level: LogLevel, message: string, data?: Record<string, unknown>) {
  if (LEVELS[level] < LEVELS[currentLevel]) return;
  const entry = { timestamp: new Date().toISOString(), level: level.toUpperCase(), message, ...(data ? { data } : {}) };
  const formatted = `[PayPerCrawl] ${JSON.stringify(entry)}`;
  switch (level) {
    case 'error': console.error(formatted); break;
    case 'warn': console.warn(formatted); break;
    default: console.log(formatted);
  }
}
