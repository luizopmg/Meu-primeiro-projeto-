export interface Env {
  DEFAULT_PRICE?: string;
  CRAWLER_RULES?: string;
  LOG_LEVEL?: string;
  /** Opcional: endereço do site original (ex.: https://meusite.com). Sem ele, o Worker repassa o pedido para a própria rota. */
  ORIGIN_URL?: string;
}

export type CrawlerAction = 'allow' | 'charge' | 'block';

export interface CrawlerRule {
  name: string;
  action: CrawlerAction;
  price?: number;
}

export interface CrawlerConfig {
  default?: CrawlerAction;
  defaultPrice?: number;
  crawlers?: CrawlerRule[];
}
