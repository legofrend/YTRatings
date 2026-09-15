<script setup lang="ts">
const { categories } = useYtrApi()

const { data, error } = await useAsyncData('home-redirect', async () => {
  const cats = await categories()
  const cat =
    cats.find((c) => c.sys_name === 'news_politics') ||
    cats.find((c) => c.id !== 0 && c.sys_name) ||
    cats.find((c) => c.id !== 0)
  if (!cat?.sys_name) throw new Error('Нет категорий с sys_name')
  return { sysName: cat.sys_name }
})

if (error.value) {
  throw createError({ statusCode: 500, statusMessage: error.value.message })
}

await navigateTo(`/${data.value!.sysName}`, {
  redirectCode: 302,
  replace: true,
})
</script>

<template>
  <p class="p-4 text-center">Перенаправление…</p>
</template>
