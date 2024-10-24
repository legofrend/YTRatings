import "./assets/main.css";

import { createApp } from "vue";
import { autoAnimatePlugin } from "@formkit/auto-animate/vue";
import App from "./App.vue";

createApp(App).use(autoAnimatePlugin).mount("#app");
