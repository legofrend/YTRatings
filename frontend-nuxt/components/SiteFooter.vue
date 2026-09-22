<template>
  <footer
    class="mx-auto max-w-screen-lg px-2 mt-8 mb-4 pt-4 border-t border-white/15 text-sm text-white/55"
  >
    <div
      class="flex flex-col items-center gap-2 sm:flex-row sm:justify-between sm:items-center sm:gap-4"
    >
      <div
        class="inline-flex items-center gap-2 text-white/80 shrink-0"
        title="o2t4 — one · two · three · four"
      >
        <img
          src="/img/o2t4-logo.png"
          alt="o2t4"
          class="h-7 w-7 object-contain"
          width="28"
          height="28"
        />
        <span class="font-medium tracking-wide">o2t4</span>
      </div>

      <p class="shrink-0 text-center">
        Связь:
        <a
          class="text-white/80 hover:text-white underline underline-offset-2"
          href="mailto:o2t4.ru@mail.ru"
        >o2t4.ru@mail.ru</a>
      </p>

      <p class="text-xs text-white/40 text-center sm:text-right shrink-0">
        © {{ year }} o2t4. Все права защищены.
      </p>
    </div>
  </footer>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()
</script>
