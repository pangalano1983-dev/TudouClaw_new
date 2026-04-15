<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { message } from 'ant-design-vue'

const authStore = useAuthStore()
const activeTab = ref<'admin' | 'token'>('admin')
const username = ref('')
const password = ref('')
const token = ref('')
const loading = ref(false)
const errorMsg = ref('')
const showHelp = ref(false)

function switchTab(tab: 'admin' | 'token') {
  activeTab.value = tab
  errorMsg.value = ''
}

async function handleAdminLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.login(username.value, password.value)
    message.success('登录成功')
  } catch (error: any) {
    errorMsg.value = error.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function handleTokenLogin() {
  if (!token.value) {
    errorMsg.value = '请输入 Token'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.loginByToken(token.value)
    message.success('登录成功')
  } catch (error: any) {
    errorMsg.value = error.message || 'Token 登录失败'
  } finally {
    loading.value = false
  }
}

async function resetToken() {
  try {
    const res = await fetch('/api/auth/reset-token', { method: 'POST' })
    const data = await res.json()
    if (data.ok) {
      message.success('Token 已重置，请查看终端输出')
      showHelp.value = false
    } else {
      message.error('重置失败')
    }
  } catch {
    message.error('重置请求失败')
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1>🥔 Tudou Claws</h1>
        <p>Multi-Agent AI Coordination Hub</p>
      </div>

      <!-- Error message -->
      <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

      <!-- Tab switcher -->
      <div class="tab-bar">
        <button
          :class="['tab-btn', { active: activeTab === 'admin' }]"
          @click="switchTab('admin')"
        >管理员登录</button>
        <button
          :class="['tab-btn', { active: activeTab === 'token' }]"
          @click="switchTab('token')"
        >Token 登录</button>
      </div>

      <!-- Admin login form -->
      <div v-show="activeTab === 'admin'" class="login-form">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="输入管理员用户名"
            autocomplete="username"
            :disabled="loading"
            @keydown.enter="$event.target === $el ? null : (password ? handleAdminLogin() : ($refs.pwdInput as HTMLInputElement)?.focus())"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            ref="pwdInput"
            v-model="password"
            type="password"
            placeholder="输入密码"
            autocomplete="current-password"
            :disabled="loading"
            @keydown.enter="handleAdminLogin"
          />
        </div>
        <div class="login-actions">
          <button
            class="btn btn-primary"
            :class="{ loading: loading }"
            :disabled="loading"
            @click="handleAdminLogin"
          >登录</button>
        </div>
      </div>

      <!-- Token login form -->
      <div v-show="activeTab === 'token'" class="login-form">
        <div class="form-group">
          <label>API Token</label>
          <input
            v-model="token"
            type="password"
            placeholder="输入你的 API Token"
            :disabled="loading"
            @keydown.enter="handleTokenLogin"
          />
        </div>
        <div class="login-actions">
          <button
            class="btn btn-primary"
            :class="{ loading: loading }"
            :disabled="loading"
            @click="handleTokenLogin"
          >登录</button>
        </div>
        <div class="help-link">
          <button @click="showHelp = true">忘记 Token？</button>
        </div>
      </div>

      <div class="login-footer">
        首次启动时会在控制台打印生成的管理员密码
      </div>
    </div>

    <!-- Token help modal -->
    <div v-if="showHelp" class="modal-overlay" @click.self="showHelp = false">
      <div class="modal-content">
        <h3>如何找到 Admin Token</h3>
        <div class="help-body">
          <p><strong>方法 1:</strong> 查看终端启动日志，找到 <code>⚠ Admin Token</code> 行</p>
          <p><strong>方法 2:</strong> 查看文件<br/><code>cat ~/.tudou_claw/.admin_token</code></p>
          <p><strong>方法 3:</strong> 重启时指定 token<br/><code>TUDOU_ADMIN_SECRET=YOUR_TOKEN uvicorn app.api.main:app</code></p>
          <p><strong>方法 4:</strong> 点击下方按钮直接重置</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-primary" @click="resetToken">重置 Token</button>
          <button class="btn btn-secondary" @click="showHelp = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg, #0e141b);
}

.login-container {
  background: var(--surface, #161c23);
  border: 1px solid var(--border, #474651);
  border-radius: 12px;
  padding: 48px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.login-header h1 {
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--text, #dde3ed);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.login-header p {
  font-size: 14px;
  color: var(--text3, #6e7681);
}

/* Tabs */
.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border, #474651);
}

.tab-btn {
  flex: 1;
  padding: 10px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text3, #6e7681);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.2s;
}

.tab-btn.active {
  border-bottom-color: var(--primary, #cbc9ff);
  color: var(--primary, #cbc9ff);
}

.tab-btn:hover:not(.active) {
  color: var(--text2, #8b949e);
}

/* Form */
.form-group {
  margin-bottom: 24px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: var(--text2, #8b949e);
  margin-bottom: 8px;
  font-weight: 500;
  letter-spacing: 0.3px;
}

.form-group input {
  width: 100%;
  padding: 12px 14px;
  background: var(--bg, #0e141b);
  border: 1px solid var(--border, #474651);
  border-radius: 8px;
  color: var(--text, #dde3ed);
  font-family: inherit;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
}

.form-group input::placeholder {
  color: var(--text3, #6e7681);
}

.form-group input:focus {
  border-color: var(--primary, #cbc9ff);
  background: var(--surface2, #242a32);
  box-shadow: 0 0 0 3px rgba(203, 201, 255, 0.1);
}

.form-group input:disabled {
  opacity: 0.6;
}

/* Buttons */
.login-actions {
  display: flex;
  gap: 12px;
}

.btn {
  flex: 1;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  font-family: inherit;
  font-weight: 600;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #cbc9ff, #acaaff);
  color: #0e141b;
  box-shadow: 0 4px 12px rgba(203, 201, 255, 0.3);
}

.btn-primary:hover {
  box-shadow: 0 6px 20px rgba(203, 201, 255, 0.4);
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: translateY(0);
}

.btn-secondary {
  padding: 8px 20px;
  background: var(--surface2, #242a32);
  color: var(--text, #dde3ed);
  border: 1px solid var(--border, #474651);
}

.btn.loading {
  opacity: 0.6;
  pointer-events: none;
}

/* Error */
.error-msg {
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.3);
  color: #f85149;
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 20px;
}

/* Help link */
.help-link {
  text-align: center;
  margin-top: 20px;
}

.help-link button {
  background: none;
  border: none;
  color: var(--text3, #6e7681);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}

/* Footer */
.login-footer {
  text-align: center;
  margin-top: 20px;
  font-size: 11px;
  color: var(--text3, #6e7681);
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  background: var(--surface, #161c23);
  border: 1px solid var(--border, #474651);
  border-radius: 12px;
  padding: 32px;
  max-width: 480px;
  width: 90%;
}

.modal-content h3 {
  font-family: 'Plus Jakarta Sans', sans-serif;
  margin-bottom: 16px;
  color: var(--text, #dde3ed);
}

.help-body {
  font-size: 13px;
  color: var(--text2, #8b949e);
  line-height: 1.8;
}

.help-body p {
  margin-bottom: 12px;
}

.help-body code {
  background: var(--bg, #0e141b);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 16px;
}

.modal-actions .btn {
  flex: unset;
}
</style>
