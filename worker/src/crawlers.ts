// Robôs de IA conhecidos. Cada padrão é procurado no User-Agent, sem diferenciar maiúsculas.
// Google-Extended e Applebot-Extended NÃO aparecem no User-Agent: são só nomes usados no
// robots.txt (o Google e a Apple rastreiam com Googlebot/Applebot). Para eles, use o robots.txt.

export interface KnownCrawler {
  name: string;
  company: string;
  userAgentPatterns: string[];
  robotsTxtOnly?: boolean;
}

export const KNOWN_AI_CRAWLERS: KnownCrawler[] = [
  { name: 'GPTBot', company: 'OpenAI', userAgentPatterns: ['GPTBot'] },
  { name: 'ChatGPT-User', company: 'OpenAI', userAgentPatterns: ['ChatGPT-User'] },
  { name: 'OAI-SearchBot', company: 'OpenAI', userAgentPatterns: ['OAI-SearchBot'] },
  { name: 'ClaudeBot', company: 'Anthropic', userAgentPatterns: ['ClaudeBot', 'Claude-Web', 'anthropic-ai'] },
  { name: 'Claude-User', company: 'Anthropic', userAgentPatterns: ['Claude-User'] },
  { name: 'Claude-SearchBot', company: 'Anthropic', userAgentPatterns: ['Claude-SearchBot'] },
  { name: 'Google-Extended', company: 'Google', userAgentPatterns: ['Google-Extended'], robotsTxtOnly: true },
  { name: 'GoogleOther', company: 'Google', userAgentPatterns: ['GoogleOther'] },
  { name: 'FacebookBot', company: 'Meta', userAgentPatterns: ['FacebookBot'] },
  { name: 'Meta-ExternalAgent', company: 'Meta', userAgentPatterns: ['meta-externalagent'] },
  { name: 'Meta-ExternalFetcher', company: 'Meta', userAgentPatterns: ['meta-externalfetcher'] },
  { name: 'Applebot-Extended', company: 'Apple', userAgentPatterns: ['Applebot-Extended'], robotsTxtOnly: true },
  { name: 'Amazonbot', company: 'Amazon', userAgentPatterns: ['Amazonbot'] },
  { name: 'PerplexityBot', company: 'Perplexity', userAgentPatterns: ['PerplexityBot'] },
  { name: 'Perplexity-User', company: 'Perplexity', userAgentPatterns: ['Perplexity-User'] },
  { name: 'MistralAI-User', company: 'Mistral AI', userAgentPatterns: ['MistralAI-User'] },
  { name: 'YouBot', company: 'You.com', userAgentPatterns: ['YouBot'] },
  { name: 'DuckAssistBot', company: 'DuckDuckGo', userAgentPatterns: ['DuckAssistBot'] },
  { name: 'cohere-ai', company: 'Cohere', userAgentPatterns: ['cohere-ai', 'cohere-training-data-crawler'] },
  { name: 'Bytespider', company: 'ByteDance', userAgentPatterns: ['Bytespider'] },
  { name: 'CCBot', company: 'Common Crawl', userAgentPatterns: ['CCBot'] },
  { name: 'AI2Bot', company: 'Allen Institute', userAgentPatterns: ['AI2Bot'] },
  { name: 'Diffbot', company: 'Diffbot', userAgentPatterns: ['Diffbot'] },
];

const LOWERED = KNOWN_AI_CRAWLERS.map(c => ({ name: c.name, patterns: c.userAgentPatterns.map(p => p.toLowerCase()) }));

export function getCrawlerName(userAgent: string): string | null {
  if (!userAgent) return null;
  const ua = userAgent.toLowerCase();
  for (const c of LOWERED) {
    if (c.patterns.some(p => ua.includes(p))) return c.name;
  }
  return null;
}
