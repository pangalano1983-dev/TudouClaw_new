import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import type { UserInfo } from '@/types'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const response = await authApi.login({ username, password })
      token.value = response.access_token
      localStorage.setItem('access_token', response.access_token)
      await fetchMe()
      router.push('/')
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function loginByToken(tokenValue: string) {
    loading.value = true
    try {
      const response = await authApi.login({ token: tokenValue })
      token.value = response.access_token
      localStorage.setItem('access_token', response.access_token)
      await fetchMe()
      router.push('/')
    } catch (error) {
      console.error('Token login failed:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    try {
      const userInfo = await authApi.me()
      user.value = userInfo
    } catch (error) {
      console.error('Failed to fetch user info:', error)
      throw error
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('access_token')
    router.push('/login')
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    login,
    loginByToken,
    fetchMe,
    logout,
  }
})
