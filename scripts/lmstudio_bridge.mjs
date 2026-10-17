// One structured prediction through the official LM Studio SDK. No act(), MCP,
// server-side tools, conversation storage, settings mutation or model loading.
import { LMStudioClient, Chat } from '@lmstudio/sdk';
import { createInterface } from 'node:readline';

const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
const lines = createInterface({ input: process.stdin });
const abort = new AbortController();
let started = false;
lines.on('close', () => abort.abort());
lines.on('line', async line => {
  if (started) { abort.abort(); return; }
  started = true;
  try {
    const input = JSON.parse(line);
    const client = new LMStudioClient({ baseUrl: input.root.replace(/^http/, 'ws'),
      logger: { debug() {}, info() {}, warn() {}, error() {} } });
    const version = await client.system.getLMStudioVersion();
    // Budgets entered the official SDK with LSEP-era 0.4.x runtimes. Do not
    // quietly send the new KV field to an older server which may ignore it.
    const [major, minor, patch] = version.version.split('.').map(Number);
    if (major === 0 && (minor < 4 || minor === 4 && patch < 19)) throw new Error('תקציב חשיבה קשיח דורש LM Studio 0.4.19 ומעלה ומנוע GGUF תומך.');
    const model = client.llm.createDynamicHandle(input.identifier || input.model);
    if (!await model.getModelInfo()) throw new Error('המודל המקומי אינו טעון ב-LM Studio.');
    const chat = Chat.empty();
    chat.append('system', input.system);
    for (const message of input.messages) {
      const images = [], text = [];
      if (Array.isArray(message.content)) for (const part of message.content) {
        if (part.type === 'text') text.push(part.text || '');
        if (part.type === 'image_url') {
          const match = /^data:image\/([^;]+);base64,(.*)$/s.exec(part.image_url?.url || '');
          if (!match) throw new Error('תקציב חשיבה ב-LM Studio דורש צירוף תמונה מקומי.');
          images.push(await client.files.prepareImageBase64('attachment.' + match[1], match[2]));
        }
      }
      const role = message.role === 'system' ? 'system' : message.role === 'assistant' ? 'assistant' : 'user';
      chat.append(role, Array.isArray(message.content) ? text.join('\n') : String(message.content || ''), { images });
    }
    const opts = { reasoningBudget: input.budget < 0 ? false : input.budget,
      enableThinking: input.budget !== 0, signal: abort.signal,
      onPromptProcessingProgress: progress => emit({ type: 'prefill', percent: progress * 100 }) };
    if (input.maxTokens) opts.maxTokens = input.maxTokens;
    const prediction = model.respond(chat, opts);
    for await (const fragment of prediction) {
      if (fragment.reasoningType && fragment.reasoningType !== 'none') emit({ type: 'thinking' });
      else if (fragment.content) emit({ type: 'text', content: fragment.content });
    }
    const result = await prediction;
    emit({ type: 'done', stats: result.stats });
    process.exit(0);
  } catch (error) {
    emit({ type: 'error', message: String(error?.message || error) });
    process.exit(1);
  }
});
