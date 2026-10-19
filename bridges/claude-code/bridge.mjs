// Only Anthropic's published SDK/binary owns credentials and network inference.
import { query } from '@anthropic-ai/claude-agent-sdk';
import readline from 'node:readline';

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const line = await new Promise(resolve => input.once('line', resolve));
input.close();
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
let session;
try {
  const request = JSON.parse(line);
  const options = {
    cwd: request.cwd,
    env: { ...process.env, CLAUDE_AGENT_SDK_CLIENT_APP: 'smarti',
      CLAUDE_CODE_DISABLE_AUTO_MEMORY: '1', ENABLE_CLAUDEAI_MCP_SERVERS: 'false' },
    tools: [], mcpServers: {}, strictMcpConfig: true, settingSources: [],
    agents: {}, skills: [], plugins: [], permissionMode: 'default',
    settings: { disableAllHooks: true, autoMemoryEnabled: false,
      disableClaudeAiConnectors: true },
    persistSession: false, includePartialMessages: true, maxTurns: 3,
    canUseTool: async (name, toolInput) => name === 'StructuredOutput'
      ? { behavior: 'allow', updatedInput: toolInput }
      : { behavior: 'deny', message: 'Smarti Core owns all tool execution.' },
    extraArgs: { 'disable-slash-commands': null },
  };
  if (request.executable) options.pathToClaudeCodeExecutable = request.executable;
  if (request.prompt_path) options.extraArgs['system-prompt-file'] = request.prompt_path;
  if (request.model) options.model = request.model;
  if (request.effort) options.effort = request.effort;
  if (request.schema) options.outputFormat = { type: 'json_schema', schema: request.schema };
  async function* prompt() {
    if (request.method === 'metadata') await new Promise(() => {});
    else yield { type: 'user', session_id: '', parent_tool_use_id: null,
      message: { role: 'user', content: request.content } };
  }
  session = query({ prompt: prompt(), options });
  if (request.method === 'metadata') {
    const models = await session.supportedModels();
    let account = {};
    try { account = await session.accountInfo(); } catch { /* Inference-only tokens may lack account metadata. */ }
    emit({ type: 'metadata', models, account });
  } else {
    const blocks = new Map();
    for await (const message of session) {
      if (message.type === 'system' && message.subtype === 'init') {
        if ((message.tools || []).some(name => name !== 'StructuredOutput') || (message.mcp_servers || []).length) {
          throw new Error('provider_contract_violation');
        }
        emit({ type: 'init', model: message.model });
      } else if (message.type === 'stream_event') {
        const event = message.event;
        if (event.type === 'content_block_start')
          blocks.set(event.index, event.content_block?.name || event.content_block?.type);
        if (event.type === 'content_block_delta' && event.delta?.type === 'input_json_delta'
            && blocks.get(event.index) === 'StructuredOutput')
          emit({ type: 'text', text: event.delta.partial_json });
        else if (!request.schema && event.type === 'content_block_delta' && event.delta?.type === 'text_delta')
          emit({ type: 'text', text: event.delta.text });
        else if (event.type === 'content_block_delta' && event.delta?.type === 'thinking_delta')
          emit({ type: 'thinking' });
      } else if (message.type === 'assistant') {
        for (const block of message.message?.content || []) {
          if (block.type === 'tool_use' && block.name !== 'StructuredOutput')
            throw new Error('provider_contract_violation');
        }
      } else if (message.type === 'result') {
        emit({ type: 'result', ok: !message.is_error && message.subtype === 'success',
          output: message.structured_output, text: message.result,
          usage: message.usage, modelUsage: message.modelUsage,
          errors: message.errors, subtype: message.subtype });
      }
    }
  }
} catch (error) {
  // No raw SDK diagnostics: they may include credentials or request content.
  emit({ type: 'failure', reason: error?.message === 'provider_contract_violation'
    ? 'provider_contract_violation' : 'provider_failed' });
  process.exitCode = 1;
} finally {
  session?.close();
}
