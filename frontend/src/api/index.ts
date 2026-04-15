/**
 * TudouClaw API client — typed wrappers around all backend endpoints.
 */
import http from './http'
import type { Agent, LoginResponse, ChatTask, Project, Workflow, WorkflowTemplate, SkillPackage, MCPServer, Provider, ClusterNode, UserInfo } from '@/types'

// ── Auth ─────────────────────────────────────────────────────────────────
export const authApi = {
  login: (data: { username?: string; password?: string; token?: string }) =>
    http.post<LoginResponse>('/api/auth/login', data),
  logout: () => http.post('/api/auth/logout'),
  me: () => http.get<UserInfo>('/api/auth/me'),
  listTokens: () => http.get('/api/auth/tokens'),
  createToken: (name: string, role: string) =>
    http.post('/api/auth/tokens', { name, role }),
  revokeToken: (id: string) => http.delete(`/api/auth/tokens/${id}`),
  resetToken: () => http.post('/api/auth/reset-token'),
}

// ── Agents ───────────────────────────────────────────────────────────────
export const agentApi = {
  list: (includeSubagents = false) =>
    http.get<{ agents: Agent[] }>('/api/portal/agents', { params: { include_subagents: includeSubagents } }),
  getEvents: (id: string) =>
    http.get(`/api/portal/agent/${id}/events`),
  getTasks: (id: string) =>
    http.get(`/api/portal/agent/${id}/tasks`),
  getRuntimeStats: (id: string) =>
    http.get(`/api/portal/agent/${id}/runtime-stats`),
  getCost: (id: string) =>
    http.get(`/api/portal/agent/${id}/cost`),
  getGrowth: (id: string) =>
    http.get(`/api/portal/agent/${id}/growth`),
  getSoul: (id: string) =>
    http.get(`/api/portal/agent/${id}/soul`),
  updateSoul: (id: string, soul: string) =>
    http.post(`/api/portal/agent/${id}/soul`, { soul }),
  updateModel: (id: string, provider: string, model: string) =>
    http.post(`/api/portal/agent/${id}/model`, { provider, model }),
  updateProfile: (id: string, data: Record<string, any>) =>
    http.post(`/api/portal/agent/${id}/profile`, data),
  chat: (id: string, message: string) =>
    http.post<{ task_id: string; status: string }>(`/api/portal/agent/${id}/chat`, { message }),
  wake: (id: string) => http.post(`/api/portal/agent/${id}/wake`),
  clear: (id: string) => http.post(`/api/portal/agent/${id}/clear`),
  getThinking: (id: string) =>
    http.get(`/api/portal/agent/${id}/thinking`),
  enableThinking: (id: string) =>
    http.post(`/api/portal/agent/${id}/thinking/enable`),
  disableThinking: (id: string) =>
    http.post(`/api/portal/agent/${id}/thinking/disable`),
  manageEnhancement: (id: string, action: string, data: Record<string, any> = {}) =>
    http.post(`/api/portal/agent/${id}/enhancement`, { action, ...data }),
}

// ── Chat streaming ───────────────────────────────────────────────────────
export const chatApi = {
  getStatus: (taskId: string) =>
    http.get<ChatTask>(`/api/portal/chat-task/${taskId}/status`),
  abort: (taskId: string) =>
    http.post(`/api/portal/chat-task/${taskId}/abort`),
  /** Returns an EventSource URL for SSE streaming. */
  streamUrl: (taskId: string, cursor = 0) =>
    `/api/portal/chat-task/${taskId}/stream?cursor=${cursor}`,
}

// ── Projects ─────────────────────────────────────────────────────────────
export const projectApi = {
  list: () => http.get<{ projects: Project[] }>('/api/portal/projects'),
  get: (id: string) => http.get<Project>(`/api/portal/projects/${id}`),
  create: (data: Record<string, any>) =>
    http.post('/api/portal/projects', { action: 'create', ...data }),
  update: (id: string, data: Record<string, any>) =>
    http.post('/api/portal/projects', { action: 'update', project_id: id, ...data }),
  delete: (id: string) =>
    http.post('/api/portal/projects', { action: 'delete', project_id: id }),
  getTasks: (id: string) =>
    http.get(`/api/portal/projects/${id}/tasks`),
  getMilestones: (id: string) =>
    http.get(`/api/portal/projects/${id}/milestones`),
  getGoals: (id: string) =>
    http.get(`/api/portal/projects/${id}/goals`),
  getDeliverables: (id: string) =>
    http.get(`/api/portal/projects/${id}/deliverables`),
  getIssues: (id: string) =>
    http.get(`/api/portal/projects/${id}/issues`),
  getOverview: (id: string) =>
    http.get(`/api/portal/projects/${id}/overview`),
}

// ── Workflows ────────────────────────────────────────────────────────────
export const workflowApi = {
  list: () => http.get<{ workflows: Workflow[] }>('/api/portal/workflows'),
  getTemplates: () => http.get<{ templates: WorkflowTemplate[] }>('/api/portal/workflow-templates'),
  getCatalog: () => http.get('/api/portal/workflow-catalog'),
  get: (id: string) => http.get<Workflow>(`/api/portal/workflows/${id}`),
  create: (data: Record<string, any>) =>
    http.post('/api/portal/workflows', { action: 'create', ...data }),
  start: (id: string) => http.post(`/api/portal/workflows/${id}/start`),
  abort: (id: string) => http.post(`/api/portal/workflows/${id}/abort`),
}

// ── Skills ───────────────────────────────────────────────────────────────
export const skillApi = {
  list: () => http.get<{ skills: SkillPackage[] }>('/api/portal/skill-pkgs'),
  get: (id: string) => http.get<SkillPackage>(`/api/portal/skill-pkgs/${id}`),
  install: (data: Record<string, any>) =>
    http.post('/api/portal/skill-pkgs/install', data),
  grant: (id: string, agentIds: string[]) =>
    http.post(`/api/portal/skill-pkgs/${id}/grant`, { agent_ids: agentIds }),
  revoke: (id: string, agentIds: string[]) =>
    http.post(`/api/portal/skill-pkgs/${id}/revoke`, { agent_ids: agentIds }),
  getStore: () => http.get('/api/portal/skill-store'),
}

// ── MCP ──────────────────────────────────────────────────────────────────
export const mcpApi = {
  getCatalog: () => http.get('/api/portal/mcp/catalog'),
  getNodes: () => http.get('/api/portal/mcp/nodes'),
  getGlobal: () => http.get('/api/portal/mcp/global'),
  getNodeConfig: (nodeId: string) =>
    http.get(`/api/portal/mcp/node/${nodeId}`),
  getAgentEffective: (nodeId: string, agentId: string) =>
    http.get(`/api/portal/mcp/node/${nodeId}/agent/${agentId}`),
  getRecommend: (role: string) =>
    http.get(`/api/portal/mcp/recommend/${role}`),
  manage: (data: Record<string, any>) =>
    http.post('/api/portal/mcp/manage', data),
}

// ── Providers ────────────────────────────────────────────────────────────
export const providerApi = {
  list: () => http.get<{ providers: Provider[] }>('/api/portal/providers'),
  getModels: (id: string) =>
    http.get(`/api/portal/providers/${id}/models`),
  register: (data: Record<string, any>) =>
    http.post('/api/portal/providers', data),
  update: (id: string, data: Record<string, any>) =>
    http.post(`/api/portal/providers/${id}/update`, data),
  detectModels: (id: string) =>
    http.post(`/api/portal/providers/${id}/detect`),
  detectAll: () => http.post('/api/portal/providers/detect-all'),
}

// ── Config ───────────────────────────────────────────────────────────────
export const configApi = {
  get: () => http.get('/api/portal/config'),
  update: (data: Record<string, any>) =>
    http.post('/api/portal/config', data),
  getPolicy: () => http.get('/api/portal/policy'),
  updatePolicy: (data: Record<string, any>) =>
    http.post('/api/portal/policy', data),
  approve: (data: Record<string, any>) =>
    http.post('/api/portal/approve', data),
  getRoles: () => http.get('/api/portal/roles'),
  getAudit: () => http.get('/api/portal/audit'),
  getCosts: () => http.get('/api/portal/costs'),
  getSystemInfo: () => http.get('/api/portal/system-info'),
}

// ── Nodes ────────────────────────────────────────────────────────────────
export const nodeApi = {
  list: () => http.get<{ nodes: ClusterNode[] }>('/api/portal/nodes'),
  getConfigs: () => http.get('/api/portal/node-configs'),
  getConfig: (nodeId: string) =>
    http.get(`/api/portal/node/${nodeId}/config`),
  updateConfig: (nodeId: string, data: Record<string, any>) =>
    http.post(`/api/portal/node/${nodeId}/config`, data),
  syncConfig: (nodeId: string) =>
    http.post(`/api/portal/node/${nodeId}/config/sync`),
}

// ── Scheduler ────────────────────────────────────────────────────────────
export const schedulerApi = {
  listJobs: () => http.get('/api/portal/scheduler/jobs'),
  getJob: (id: string) => http.get(`/api/portal/scheduler/jobs/${id}`),
  getHistory: (id: string) =>
    http.get(`/api/portal/scheduler/jobs/${id}/history`),
  manageJob: (data: Record<string, any>) =>
    http.post('/api/portal/scheduler/jobs', data),
}

// ── Experience ───────────────────────────────────────────────────────────
export const experienceApi = {
  getStats: () => http.get('/api/portal/experience/stats'),
  list: (role?: string) =>
    http.get('/api/portal/experience/list', { params: { role } }),
  getHistory: () => http.get('/api/portal/experience/history'),
  triggerRetrospective: (agentId: string) =>
    http.post('/api/portal/experience/retrospective', { agent_id: agentId }),
  triggerLearning: (agentId: string, topic: string) =>
    http.post('/api/portal/experience/learning', { agent_id: agentId, topic }),
}

// ── Health ───────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => http.get('/api/health'),
}
