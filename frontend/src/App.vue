<script setup lang="ts">
import { RouterView } from 'vue-router'
import { ConfigProvider, theme } from 'ant-design-vue'
</script>

<template>
  <ConfigProvider :theme="{ algorithm: theme.darkAlgorithm }">
    <RouterView />
  </ConfigProvider>
</template>
