// A per-turn, immutable MCP payload reader. No model-selected paths or actions.
import { readFileSync, statSync } from 'node:fs';
import readline from 'node:readline';

const path = process.argv[2];
if (!path || statSync(path).size > 36 * 1024 * 1024) process.exit(1);
const content = JSON.parse(readFileSync(path, 'utf8'));
if (!Array.isArray(content) || content.some(item => !['text', 'image', 'resource'].includes(item.type)
    || item.type === 'resource' && (item.resource?.mimeType !== 'application/pdf'
      || !item.resource?.uri?.startsWith('smarti-attachment:///') || typeof item.resource?.blob !== 'string'))) process.exit(1);
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
for await (const line of input) {
  if (line.length > 65536) break;
  let request;
  try { request = JSON.parse(line); } catch { continue; }
  if (request.id === undefined) continue;
  let result;
  if (request.method === 'initialize') result = { protocolVersion: '2024-11-05',
    capabilities: { tools: {} }, serverInfo: { name: 'smarti_media', version: '1.0' } };
  else if (request.method === 'ping') result = {};
  else if (request.method === 'tools/list') result = { tools: [{ name: 'attachments',
    description: 'Load the images and PDF documents already supplied in this Smarti conversation, in message order. No file access or actions.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false } }] };
  else if (request.method === 'tools/call' && request.params?.name === 'attachments'
      && Object.keys(request.params.arguments || {}).length === 0) result = { content };
  else { emit({ jsonrpc: '2.0', id: request.id, error: { code: -32601, message: 'Unsupported media operation' } }); continue; }
  emit({ jsonrpc: '2.0', id: request.id, result });
}
