import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/pages/Dashboard.vue'),
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/pages/Agents.vue'),
      },
      {
        path: 'agent/:id',
        name: 'AgentChat',
        component: () => import('@/pages/AgentChat.vue'),
        props: true,
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/pages/Projects.vue'),
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/pages/ProjectDetail.vue'),
        props: true,
      },
      {
        path: 'workflows',
        name: 'Workflows',
        component: () => import('@/pages/Workflows.vue'),
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('@/pages/Skills.vue'),
      },
      {
        path: 'mcp',
        name: 'MCP',
        component: () => import('@/pages/MCP.vue'),
      },
      {
        path: 'providers',
        name: 'Providers',
        component: () => import('@/pages/Providers.vue'),
      },
      {
        path: 'nodes',
        name: 'Nodes',
        component: () => import('@/pages/Nodes.vue'),
      },
      {
        path: 'scheduler',
        name: 'Scheduler',
        component: () => import('@/pages/Scheduler.vue'),
      },
      {
        path: 'experience',
        name: 'Experience',
        component: () => import('@/pages/Experience.vue'),
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('@/pages/Config.vue'),
      },
      {
        path: 'audit',
        name: 'Audit',
        component: () => import('@/pages/Audit.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard: redirect to login if not authenticated
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  if (!to.meta.public && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
