// Generated from smarti/control_plane_contract.py. Do not edit by hand.
export const SMARTI_DESKTOP_CONTRACT_VERSION = "2.0.0" as const;
export interface ApiEnvelope<T> { request_id: string; data: T }
export interface ApiError { request_id: string; error: string; detail?: string; fields?: string[] }
export interface DesktopEvent { event_id: number; sequence: number; event_type: string; request_id: string; session_id: string; run_id: string; payload: Record<string, unknown>; created_at: string }
export interface CreateWorkspaceRequest {
  title?: string;
  root_path?: string;
  metadata?: Record<string, unknown>;
}
export interface PatchWorkspaceRequest {
  title?: string;
  root_path?: string;
  metadata?: Record<string, unknown>;
}
export interface CreateConversationRequest {
  title?: string;
  workspace_id?: string;
}
export interface PatchConversationRequest {
  title?: string;
  workspace_id?: string;
  pinned?: boolean;
}
export interface SubmitRunRequest {
  text?: string;
  attachment_handles?: Array<string>;
  workspace_id?: string;
  source?: string;
  provider_mode?: string;
  model_name?: string;
}
export interface MarkReadRequest {
  actor_id?: string;
  attention_ids?: Array<string>;
}
export interface ResolveApprovalRequest {
  approved: boolean;
}
export interface PatchSettingsRequest {
  values: Record<string, unknown>;
}
export interface SetSecretRequest {
  value: string;
}
export interface LegalAcceptanceRequest {
  accepted: boolean;
  version: string;
}
export interface SettingsActionRequest {
  action: "reset" | "codex_status" | "codex_check" | "codex_login" | "codex_logout" | "email_test" | "ssl_test" | "ssl_import_ca" | "log_clear";
  ssl_trust_mode?: "system" | "custom_ca" | "legacy_insecure";
  ssl_custom_ca_path?: string;
  source_path?: string;
  confirmation?: string;
}
export interface ValidateProviderRequest {
  secret?: string;
  local_url?: string;
}
export interface SetModelReasoningRequest {
  model: string;
  effort: string;
}
export interface RegisterAttachmentRequest {
  path: string;
  session_id?: string;
  ttl_seconds?: number;
}
export interface StartTtsRequest {
  text: string;
}
export interface ProvideRunApiKeyRequest {
  secret_key: string;
  value: string;
}
export interface TaskActionRequest {
  action: "create" | "edit" | "cancel" | "retry" | "resume" | "delete";
  id?: string;
  prompt?: string;
  delay_minutes?: number;
  repeat?: "once" | "interval" | "weekly";
  interval_minutes?: number;
  days_of_week?: Array<number>;
  conversation_mode?: "current" | "new" | "dedicated";
}
export interface MemoryActionRequest {
  action: "details" | "reveal" | "edit" | "pin" | "archive" | "restore" | "delete";
  subject?: string;
  content?: string;
  category?: string;
  sensitivity?: string;
  tags?: Array<string>;
  importance?: number;
  pinned?: boolean;
  memory_type?: string;
  ttl_hours?: number;
}
export interface MemoryCollectionActionRequest {
  action: "create" | "bulk_archive" | "bulk_restore" | "bulk_delete" | "import" | "export" | "clear";
  ids?: Array<string>;
  subject?: string;
  content?: string;
  category?: string;
  memory_type?: string;
  tags?: Array<string>;
  importance?: number;
  ttl_hours?: number;
  pinned?: boolean;
  path?: string;
  confirmation?: string;
}
export interface ToolActionRequest {
  action: "set_trust" | "set_enabled" | "refresh" | "install_skill" | "install_custom" | "install_mcp" | "delete";
  kind?: "builtin" | "custom" | "mcp" | "skill";
  name?: string;
  trusted?: boolean;
  enabled?: boolean;
  path?: string;
  package?: string;
}
export interface DiagnosticActionRequest {
  action?: "scan" | "repair" | "cancel";
  include_network?: boolean;
  repair_id?: string;
}
export interface SetWorkspaceRootRequest {
  path: string;
}
export interface OpenWorkspaceFileRequest {
  path: string;
}
export interface TerminalActionRequest {
  action: "write" | "restart";
  text?: string;
}
export interface CanvasActionRequest {
  action: "layout" | "close" | "reopen";
  button_positions?: Array<Record<string, unknown>>;
}
export interface BrowserImportRequest {
  source_id: string;
  history?: boolean;
  bookmarks?: boolean;
  cookies?: boolean;
}
export interface LegacyBrowserMigrationRequest {
  action: "applied";
}
