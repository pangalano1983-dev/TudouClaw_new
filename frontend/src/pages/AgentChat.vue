<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAgentStore } from '@/stores/agents'
import { agentApi, chatApi } from '@/api'
import { message } from 'ant-design-vue'
import type { ChatEvent } from '@/types'

const route = useRoute()
const agentStore = useAgentStore()
const id = route.params.id as string

const messages = ref<{ role: string; content: string; timestamp: number }[]>([])
const inputMessage = ref('')
const loading = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const streaming = ref(false)
const currentStreamingMessage = ref('')

const agent = computed(() => {
  return agentStore.agents.find((a) => a.id === id)
})

onMounted(async () => {
  if (!agentStore.agents.length) {
    await agentStore.fetchAgents()
  }
  agentStore.selectAgent(id)
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function simpleMarkdown(text: string): string {
  // Simple markdown rendering
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="color: #a78bfa;">$1</code>')
    .replace(/\n/g, '<br/>')
}

async function handleSendMessage() {
  if (!inputMessage.value.trim()) {
    return
  }

  const userMessage = inputMessage.value
  inputMessage.value = ''

  // Add user message
  messages.value.push({
    role: 'user',
    content: userMessage,
    timestamp: Date.now(),
  })
  scrollToBottom()

  loading.value = true
  streaming.value = true
  currentStreamingMessage.value = ''

  try {
    // Get task ID from chat endpoint
    const { task_id } = await agentApi.chat(id, userMessage)

    // Add placeholder for assistant message
    const assistantMessageIndex = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    })

    // Open SSE connection
    const streamUrl = chatApi.streamUrl(task_id, 0)
    const eventSource = new EventSource(streamUrl)

    eventSource.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data) as ChatEvent

        if (data.type === 'text_delta' && data.content) {
          currentStreamingMessage.value += data.content
          messages.value[assistantMessageIndex].content = currentStreamingMessage.value
          scrollToBottom()
        } else if (data.type === 'text' && data.content) {
          currentStreamingMessage.value = data.content
          messages.value[assistantMessageIndex].content = currentStreamingMessage.value
          scrollToBottom()
        } else if (data.type === 'done') {
          eventSource.close()
          streaming.value = false
        }
      } catch (err) {
        console.error('Error parsing SSE message:', err)
      }
    })

    eventSource.onerror = (error) => {
      console.error('SSE error:', error)
      eventSource.close()
      streaming.value = false
      if (messages.value[assistantMessageIndex].content) {
        // Message was partially received, keep it
      } else {
        message.error('Failed to get response from agent')
      }
    }
  } catch (error: any) {
    message.error(error.message || 'Failed to send message')
    // Remove the placeholder message if chat failed
    messages.value.pop()
  } finally {
    loading.value = false
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Enter' && event.ctrlKey) {
    handleSendMessage()
  }
}
</script>

<template>
  <div style="display: flex; gap: 16px; height: 100%; min-height: calc(100vh - 200px)">
    <!-- Left: Chat Area -->
    <div style="flex: 1; display: flex; flex-direction: column">
      <!-- Messages -->
      <div
        ref="messagesContainer"
        style="
          flex: 1;
          overflow-y: auto;
          margin-bottom: 16px;
          padding: 16px;
          background: #151d27;
          border-radius: 4px;
        "
      >
        <div v-if="!messages.length" style="text-align: center; color: #64748b; padding: 32px">
          No messages yet. Start a conversation!
        </div>
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          style="
            margin-bottom: 12px;
            display: flex;
            justify-content: msg.role === 'user' ? 'flex-end' : 'flex-start';
          "
        >
          <div
            v-if="msg.role === 'assistant'"
            style="
              display: flex;
              gap: 8px;
              max-width: 80%;
              align-items: flex-start;
            "
          >
            <div style="font-size: 20px; flex-shrink: 0">🤖</div>
            <div
              style="
                background: #1a2332;
                padding: 12px 16px;
                border-radius: 8px;
                border-left: 3px solid #a78bfa;
              "
            >
              <div v-html="simpleMarkdown(msg.content)" />
              <div
                v-if="idx === messages.length - 1 && streaming"
                style="color: #94a3b8; font-size: 12px; margin-top: 8px"
              >
                <a-spin size="small" />
              </div>
            </div>
          </div>
          <div
            v-else
            style="
              background: #a78bfa;
              color: #0e141b;
              padding: 12px 16px;
              border-radius: 8px;
              max-width: 80%;
            "
          >
            {{ msg.content }}
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div style="display: flex; gap: 8px">
        <a-input
          v-model:value="inputMessage"
          placeholder="Type your message (Ctrl+Enter to send)"
          :disabled="loading || streaming"
          @keydown="handleKeyDown"
        />
        <a-button
          type="primary"
          :loading="loading || streaming"
          @click="handleSendMessage"
        >
          Send
        </a-button>
      </div>
    </div>

    <!-- Right: Agent Info -->
    <div style="width: 280px">
      <a-card :bordered="false" v-if="agent">
        <template #title>
          <div style="font-size: 20px">{{ agent.robot_avatar }}</div>
        </template>
        <div style="display: flex; flex-direction: column; gap: 12px">
          <div>
            <div style="color: #94a3b8; font-size: 12px">Name</div>
            <div>{{ agent.name }}</div>
          </div>
          <div>
            <div style="color: #94a3b8; font-size: 12px">Role</div>
            <div>{{ agent.role }}</div>
          </div>
          <div>
            <div style="color: #94a3b8; font-size: 12px">Model</div>
            <div>{{ agent.model }}</div>
          </div>
          <div>
            <div style="color: #94a3b8; font-size: 12px">Status</div>
            <a-tag
              :color="
                agent.status === 'idle'
                  ? 'success'
                  : agent.status === 'busy'
                    ? 'processing'
                    : 'error'
              "
            >
              {{ agent.status }}
            </a-tag>
          </div>
          <div>
            <div style="color: #94a3b8; font-size: 12px">Tasks</div>
            <div>{{ agent.task_count }}</div>
          </div>
        </div>
      </a-card>
      <a-empty v-else description="Agent not found" />
    </div>
  </div>
</template>
