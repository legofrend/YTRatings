<script setup>
import { ref, onMounted, watch } from 'vue';
import axios from 'axios';
import Data from './assets/data.json';
import Chart from './components/Chart.vue';
import InfoBlock from './components/InfoBlock.vue';
import FeedbackForm from './components/FeedbackForm.vue';


const data = ref([]);
const loading = ref(true);
const error = ref(null);
const currentPeriod = ref(0);
const currentCategory = ref(1);
const categories = ref([]);

async function fetchData(category_id) {
  console.log('fetchData: category_id is ', category_id)

  const d = Data.filter(item => item.category_id == category_id);
  // sorted [...this.Data].sort((tomb1, tomb2) => tomb1[this.selectedSort]?.localeCompare(tomb2[this.selectedSort]))
  data.value = d;
  currentPeriod.value = data.value.length - 1
  return

  try {
    const response = await axios.get('reports?category_id=' + category_id);
    data.value = response.data;
    currentPeriod.value = data.value.length - 1
    console.log('Current period', currentPeriod.value)
    console.log('Current display', data.value[currentPeriod.value].display_period)
  } catch (err) {
    error.value = err.message;
  } finally {
  }
}


async function fetchCategories() {
  try {
    const response = await axios.get('categories');
    categories.value = response.data;
  } catch (err) {
    error.value = err.message;
  } finally {
  }
}


function changeCategory(value) {
  console.log('changeCategory: value is ', value)
  currentCategory.value = value
  fetchData(currentCategory.value);
}

watch(
  currentCategory,
  () => {
    localStorage.setItem('currentCategory', currentCategory.value)
  },
  // { deep: true }
)


onMounted(() => {

  axios.defaults.baseURL = 'https://47b996947b39655e.mokky.dev/';
  loading.value = true;
  fetchCategories();
  const localCurrentCategory = localStorage.getItem('currentCategory');
  console.log(localCurrentCategory);
  currentCategory.value = localCurrentCategory ? localCurrentCategory : 1;

  fetchData(currentCategory.value);
  loading.value = false;

})
</script>

<template>
  <div class=" mx-5 ">
    <h1 class="flex items-center justify-center gap-3 text-4xl m-3 ">Рейтинг <img class="h-8"
        src="/img/youtube_logo.svg" alt="">
      каналов</h1>
    <info-block header="Методика" class="text-xs">Рейтинг на основе суммы просмотров на канале по видео и клипам двух
      последних месяцев.
      Клипы (shorts) учитываются с коэффициентом 1/10</info-block>
    <p v-if="loading">Loading...</p>
    <p v-else-if="error">{{ error }}</p>
    <div v-else>
      <h2 class="text-center text-3xl m-3">{{ data[currentPeriod].category.title }}</h2>
      <info-block header="Критерии" class="text-xs">{{ data[currentPeriod].category.criteria }}</info-block>
      <div class="flex justify-center">
        <select v-model="currentCategory" @change="changeCategory($event.target.value)" name="category"
          class="text-center text-xl m-3 cursor-pointer">
          <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
        </select>

        <div class="flex justify-center items-center">
          <span class="text-2xl mx-2 cursor-pointer" @click="currentPeriod == 0 ? False : currentPeriod--">⮜</span>
          <!-- <img :src="ArrowLeft" class="h-6 mx-3 cursor-pointer" @click="currentPeriod == 0 ? False : currentPeriod--" /> -->

          <h3 class="text-center text-xl m-3">{{ data[currentPeriod].display_period }}</h3>
          <!-- <img :src="ArrowRight" class="h-6 mx-3 cursor-pointer"
            @click="currentPeriod == data.length - 1 ? False : currentPeriod++" /> -->
          <span class="text-2xl mx-2 cursor-pointer"
            @click="currentPeriod == data.length - 1 ? False : currentPeriod++">⮞</span>
        </div>
      </div>
      <Chart :data="data[currentPeriod]" />
    </div>
    <info-block header="Предложить свой канал или тему" class="text-lg my-10"><feedback-form /></info-block>

  </div>
</template>

<!-- {/* <template>
  <div>
    <p v-if="loading">Loading...</p>
    <p v-else-if="error">{{ error }}</p>
    <ul v-else>
      <li v-for="(obj, index) in data" :key="index">{{ obj.id }}</li>
    </ul>
  </div>
</template> */} -->
