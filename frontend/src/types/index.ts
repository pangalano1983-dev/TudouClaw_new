// ── Agent ────────────────────────────────────────────────────────────────
export interface Agent {
  id: string
  name: string
  role: string
  status: 'idle' | 'busy' | 'error' | 'offline'
  phase: string
  model: string
  provider: string
  robot_avatar: string
  node_id: string
  parent_id?: string
  task_count: number
  token_usage: number
  created_at: string
}

// ── Chat ─────────────────────────────────────────────────────────────────
export interface ChatEvent {
  type: 'text_delta' | 'text' | 'tool_call' | 'tool_result' | 'error' | 'done' | 'status' | 'thinking' | 'approval_request' | 'plan_update' | 'artifact_refs'
  content?: string
  name?: string
  timestamp?: number
  status?: string
  progress?: number
  phase?: string
  [key: string]: any
}

export interface ChatTask {
  task_id: string
  status: string
  progress: number
  phase: string
  result: string
}

// ── AgentEvent (history) ─────────────────────────────────────────────────
export interface AgentEvent {
  timestamp: number
  kind: string
  data: {
    role?: string
    content?: string
    [key: string]: any
  }
}

// ── Project ──────────────────────────────────────────────────────────────
export interface Project {
  id: string
  name: string
  status: string
  description: string
  members: string[]
  created_at: string
  tasks: ProjectTask[]
}

export interface ProjectTask {
  id: string
  title: string
  status: string
  assignee: string
  priority: string
}

// ── Workflow ──────────────────────────────────────────────────────────────
export interface Workflow {
  id: string
  name: string
  status: string
  template_id: string
  steps: WorkflowStep[]
}

export interface WorkflowStep {
  id: string
  name: string
  status: string
  assignee: string
  depends_on: string[]
}

export interface WorkflowTemplate {
  id: string
  name: string
  description: string
  category: string
  steps: { name: string; role: string }[]
}

// ── Skill ────────────────────────────────────────────────────────────────
export interface SkillPackage {
  id: string
  name: string
  description: string
  version: string
  trust_tier: string
  status: string
}

// ── MCP ──────────────────────────────────────────────────────────────────
export interface MCPServer {
  id: string
  name: string
  transport: string
  scope: string
  enabled: boolean
  status: string
}

// ── Provider ─────────────────────────────────────────────────────────────
export interface Provider {
  id: string
  name: string
  type: string
  base_url: string
  models: string[]
  status: string
}

// ── Node ─────────────────────────────────────────────────────────────────
export interface ClusterNode {
  id: string
  name: string
  status: string
  agent_count: number
  address: string
}

// ── Auth ─────────────────────────────────────────────────────────────────
export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user_id: string
  role: string
}

export interface UserInfo {
  user_id: string
  role: string
  is_super_admin: boolean
}
