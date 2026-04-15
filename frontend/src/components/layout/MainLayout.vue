<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  DashboardOutlined,
  RobotOutlined,
  ProjectOutlined,
  ApartmentOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  ClockCircleOutlined,
  BulbOutlined,
  SettingOutlined,
  AuditOutlined,
  LogoutOutlined,
  DownOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const collapsed = ref(false)

const menuItems = [
  { label: 'Dashboard', key: 'Dashboard', icon: DashboardOutlined },
  { label: 'Agents', key: 'Agents', icon: RobotOutlined },
  { label: 'Projects', key: 'Projects', icon: ProjectOutlined },
  { label: 'Workflows', key: 'Workflows', icon: ApartmentOutlined },
  { label: 'Skills', key: 'Skills', icon: ThunderboltOutlined },
  { label: 'MCP', key: 'MCP', icon: ApiOutlined },
  { label: 'Providers', key: 'Providers', icon: CloudServerOutlined },
  { label: 'Nodes', key: 'Nodes', icon: ClusterOutlined },
  { label: 'Scheduler', key: 'Scheduler', icon: ClockCircleOutlined },
  { label: 'Experience', key: 'Experience', icon: BulbOutlined },
  { label: 'Config', key: 'Config', icon: SettingOutlined },
  { label: 'Audit', key: 'Audit', icon: AuditOutlined },
]

const currentRoute = computed(() => router.currentRoute.value.name as string)

function handleMenuClick(key: string) {
  router.push({ name: key })
}

function handleLogout() {
  authStore.logout()
}
</script>

<template>
  <a-layout style="min-height: 100vh">
    <!-- Sidebar -->
    <a-layout-sider
      v-model:collapsed="collapsed"
      theme="dark"
      :width="200"
      collapsible
      :collapsed-width="80"
    >
      <div style="padding: 16px; text-align: center; border-bottom: 1px solid #1e293b">
        <div style="font-size: 24px">🥔</div>
        <div v-if="!collapsed" style="color: #a78bfa; margin-top: 8px; font-weight: bold">
          TudouClaw
        </div>
      </div>
      <a-menu
        :selected-keys="[currentRoute]"
        theme="dark"
        mode="inline"
        @click="(e) => handleMenuClick(e.key as string)"
      >
        <a-menu-item v-for="item in menuItems" :key="item.key">
          <template #icon>
            <component :is="item.icon" />
          </template>
          {{ item.label }}
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <!-- Header -->
      <a-layout-header
        style="
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0 24px;
        "
      >
        <h2 style="margin: 0; color: #e2e8f0">{{ currentRoute }}</h2>
        <a-dropdown placement="bottomRight">
          <template #overlay>
            <a-menu>
              <a-menu-item key="logout" @click="handleLogout">
                <template #icon>
                  <LogoutOutlined />
                </template>
                Logout
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="text" style="color: #e2e8f0">
            {{ authStore.user?.user_id }}
            <DownOutlined />
          </a-button>
        </a-dropdown>
      </a-layout-header>

      <!-- Content -->
      <a-layout-content>
        <RouterView />
      </a-layout-content>

      <!-- Footer -->
      <a-layout-footer style="text-align: center; padding: 16px">
        TudouClaw Multi-Agent AI Coordination Hub © 2024
      </a-layout-footer>
    </a-layout>
  </a-layout>
</template>
