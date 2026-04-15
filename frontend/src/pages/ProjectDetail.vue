<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { projectApi } from '@/api'
import { message } from 'ant-design-vue'

const route = useRoute()
const id = route.params.id as string
const loading = ref(false)
const activeTab = ref('overview')

const project = ref<any>(null)
const tasks = ref<any[]>([])
const milestones = ref<any[]>([])
const goals = ref<any[]>([])
const deliverables = ref<any[]>([])
const issues = ref<any[]>([])

onMounted(async () => {
  await fetchProjectData()
})

async function fetchProjectData() {
  loading.value = true
  try {
    const [projectData, tasksData, milestonesData, goalsData, deliverablesData, issuesData] =
      await Promise.all([
        projectApi.get(id),
        projectApi.getTasks(id),
        projectApi.getMilestones(id),
        projectApi.getGoals(id),
        projectApi.getDeliverables(id),
        projectApi.getIssues(id),
      ])

    project.value = projectData
    tasks.value = tasksData
    milestones.value = milestonesData
    goals.value = goalsData
    deliverables.value = deliverablesData
    issues.value = issuesData
  } catch (error) {
    message.error('Failed to load project')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-spin :spinning="loading">
    <a-tabs v-model:activeKey="activeTab">
      <!-- Overview Tab -->
      <a-tab-pane key="overview" tab="Overview">
        <a-card v-if="project" :bordered="false">
          <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px">
            <div>
              <div style="color: #94a3b8; font-size: 12px">Name</div>
              <div style="font-size: 18px; font-weight: bold">{{ project.name }}</div>
            </div>
            <div>
              <div style="color: #94a3b8; font-size: 12px">Status</div>
              <a-tag :color="project.status === 'active' ? 'success' : 'default'">
                {{ project.status }}
              </a-tag>
            </div>
            <div style="grid-column: 1 / -1">
              <div style="color: #94a3b8; font-size: 12px">Description</div>
              <div>{{ project.description }}</div>
            </div>
            <div>
              <div style="color: #94a3b8; font-size: 12px">Members</div>
              <div>{{ project.members?.length || 0 }}</div>
            </div>
            <div>
              <div style="color: #94a3b8; font-size: 12px">Created</div>
              <div>{{ project.created_at }}</div>
            </div>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tasks Tab -->
      <a-tab-pane key="tasks" tab="Tasks">
        <a-table :columns="[
          { title: 'Title', dataIndex: 'title', key: 'title' },
          { title: 'Status', dataIndex: 'status', key: 'status' },
          { title: 'Assignee', dataIndex: 'assignee', key: 'assignee' },
          { title: 'Priority', dataIndex: 'priority', key: 'priority' },
        ]"
        :data-source="tasks"
        :pagination="{ pageSize: 10 }"
        />
      </a-tab-pane>

      <!-- Milestones Tab -->
      <a-tab-pane key="milestones" tab="Milestones">
        <a-table :columns="[
          { title: 'Name', dataIndex: 'name', key: 'name' },
          { title: 'Status', dataIndex: 'status', key: 'status' },
          { title: 'Due Date', dataIndex: 'due_date', key: 'due_date' },
        ]"
        :data-source="milestones"
        :pagination="{ pageSize: 10 }"
        />
      </a-tab-pane>

      <!-- Goals Tab -->
      <a-tab-pane key="goals" tab="Goals">
        <a-table :columns="[
          { title: 'Goal', dataIndex: 'name', key: 'name' },
          { title: 'Status', dataIndex: 'status', key: 'status' },
          { title: 'Progress', dataIndex: 'progress', key: 'progress' },
        ]"
        :data-source="goals"
        :pagination="{ pageSize: 10 }"
        />
      </a-tab-pane>

      <!-- Deliverables Tab -->
      <a-tab-pane key="deliverables" tab="Deliverables">
        <a-table :columns="[
          { title: 'Name', dataIndex: 'name', key: 'name' },
          { title: 'Status', dataIndex: 'status', key: 'status' },
          { title: 'Due Date', dataIndex: 'due_date', key: 'due_date' },
        ]"
        :data-source="deliverables"
        :pagination="{ pageSize: 10 }"
        />
      </a-tab-pane>

      <!-- Issues Tab -->
      <a-tab-pane key="issues" tab="Issues">
        <a-table :columns="[
          { title: 'Issue', dataIndex: 'title', key: 'title' },
          { title: 'Severity', dataIndex: 'severity', key: 'severity' },
          { title: 'Status', dataIndex: 'status', key: 'status' },
        ]"
        :data-source="issues"
        :pagination="{ pageSize: 10 }"
        />
      </a-tab-pane>
    </a-tabs>
  </a-spin>
</template>
