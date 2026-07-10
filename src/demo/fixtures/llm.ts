/** Demo LLM profile fixtures */
import type { LlmProfiles } from '../../api/types';

export const DEMO_LLM_PROFILES: LlmProfiles = {
  base_url: 'https://api.camel-hub.demo/v1',
  items: [
    { role: 'pllm', model: 'claude-3-5-sonnet-20241022', temperature: 0.1, max_tokens: 1600, timeout_s: 90 },
    { role: 'qllm', model: 'Qwen/Qwen2.5-7B-Instruct', temperature: 0.1, max_tokens: 900, timeout_s: 90 },
  ],
};

export const DEMO_LLM_MODELS: string[] = [
  'claude-3-5-sonnet-20241022',
  'claude-3-haiku-20240307',
  'Qwen/Qwen2.5-7B-Instruct',
  'Qwen/Qwen2.5-14B-Instruct',
  'gpt-4o',
];
