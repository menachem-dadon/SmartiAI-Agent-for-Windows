export interface Conversation {
  id: string; title: string; preview?: string; updated_at?: string; message_count?: number;
  unread_count?: number; needs_input?: boolean; is_busy?: boolean; runtime_status?: string; active_run_count?: number; pinned?: boolean;
}
export interface AttachmentMeta { handle?: string; name: string; kind?: string; mime_type?: string; size?: number; path?: string; }
export interface ChatMessage { role: "user" | "assistant" | "system"; content: string; created_at?: string; attachments?: AttachmentMeta[]; metadata?: Record<string, unknown>; }
export interface MessagePage { session_id: string; messages: ChatMessage[]; total_count: number; has_older: boolean; older_count: number; next_before_ordinal: number | null; }
export interface RunRecord { id: string; session_id: string; status: string; user_text: string; response_text?: string; error_text?: string; updated_at?: string; }
export interface RunEvent { event_id: number; sequence: number; event_type: string; session_id: string; run_id: string; payload: Record<string, unknown>; created_at: string; }
export interface Approval { id: string; run_id: string; session_id: string; title: string; prompt: string; risk_level: string; created_at: string; }
export interface ReasoningOption { value: string; label: string; }
export interface ChatModels { providers: string[]; provider: string; model: string; reasoning_effort?: string; reasoning_options?: ReasoningOption[]; }
export interface SafeSettings { values?: Record<string, unknown>; }
export interface Bootstrap { conversations: Conversation[]; pending_approvals: Approval[]; unread_count: number; chat_models: ChatModels; display_name?: string; settings?: SafeSettings; }
export interface PendingAttachment extends AttachmentMeta { path: string; previewUrl?: string; registering?: boolean; error?: string; }
