<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import axios from 'axios';
import Data from './assets/data.json';
import Chart from './components/Chart.vue';
import InfoBlock from './components/InfoBlock.vue';
import FeedbackForm from './components/FeedbackForm.vue';


const metaData = ref([]);
const data = ref([]);
const selectedSort = ref(Object);
const loading = ref(true);
const error = ref(null);
const currentCategory = ref(Object);
const currentPeriodIndex = ref(0)

const sortTypes = [
  { id: 'rank', name: 'Место' },
  { id: 'subscriber_count', name: 'Подписчики' },
]
selectedSort.value = 'rank'
// selectedSort.value = 'subscriber_count'


const currentPeriod = computed(() => {
  return currentCategory.value.periods[currentPeriodIndex.value]
})

const currentCategoryId = computed(() => {
  return currentCategory.value.id
})

const periodDisplay = computed(() => {
  return formattedDate(currentPeriod.value)
})



function formattedDate(dateStr) {
  const dateObject = new Date(dateStr);
  // console.log('dateStr', typeof dateStr, dateStr)
  // console.log('dateObject', typeof dateObject, dateObject)
  const months = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
  const month = months[dateObject.getMonth()];
  const year = dateObject.getFullYear();
  return `${month} ${year}`;
}

async function fetchData(category_id, period) {
  console.log('fetchData: category_id=', category_id, ', period=', period)

  try {
    const response = await axios.get('report', {
      params: {
        category_id: category_id,
        period: period
      }
    });
    data.value = response.data;
    // currentPeriod.value = period
    // currentCategory.value = category_id
    // console.log('Current period', currentPeriod.value)
    // console.log('Current display', data.value[currentPeriod.value].display_period)
  } catch (err) {
    error.value = err.message;
    return
  } finally {
  }
}


async function fetchMetaData() {
  // console.log('fetchMetaData')
  try {
    const response = await axios.get('metadata');
    console.log('response', response)
    metaData.value = response.data;
    // console.log('metaData', metaData.value)
  } catch (err) {
    error.value = err.message;
  } finally {
  }



}

function changePeriod(change) {
  const newIndex = currentPeriodIndex.value + change
  if (newIndex < 0 || newIndex >= currentCategory.value.periods.length) {
    return False
  }
  currentPeriodIndex.value = newIndex
  fetchData(currentCategoryId.value, currentPeriod.value);
}


function changeCategory(categoryId) {
  // console.log('changeCategory: categoryId=', categoryId, typeof categoryId)

  const category = metaData.value.find(cat => cat.id === Number(categoryId));

  if (!category) {
    throw new Error('Категория не найдена');
    // return False
  }

  // Проверяем существует ли period в категориях
  if (!category.periods.includes(currentPeriod.value)) {
    currentPeriodIndex.value = category.periods.length - 1
  }
  else {
    currentPeriodIndex.value = category.periods.indexOf(currentPeriod.value)
  }

  currentCategory.value = category

  fetchData(categoryId, currentPeriod.value);
}

watch(
  currentCategoryId,
  () => {
    localStorage.setItem('currentCategoryId', currentCategoryId.value)
  },
  // { deep: true }
)

function parseUrl() {
  const url = window.location.href; // Получаем полный URL
  const regex = /\/(\d+)\/([\d]{4}-[\d]{2}-[\d]{2})$/; // Регулярное выражение для парсинга

  const matches = url.match(regex);
  if (matches) {
    this.categoryId = parseInt(matches[1], 10); // Присваиваем categoryId
    this.period = matches[2]; // Присваиваем period
  }
}

async function initialize() {
  loading.value = true;

  // Взять параметры из адресной строки
  const urlParams = new URLSearchParams(window.location.search);
  const paramValue = urlParams.get('category_id');
  // console.log('url param category_id=', paramValue);

  const localCurrentCategoryId = localStorage.getItem('currentCategoryId');
  const categoryId = paramValue ? Number(paramValue) : (localCurrentCategoryId ? Number(localCurrentCategoryId) : 1);

  await fetchMetaData();
  console.log('metaData', metaData.value);
  // console.log('currentCategory', currentCategory.value);

  currentCategory.value = metaData.value.find(cat => cat.id === categoryId);
  console.log('Category', currentCategory.value);
  if (currentCategory.value) {
    currentPeriodIndex.value = currentCategory.value.periods.length - 1
    // const period = category.periods[currentPeriodIndex.value];
    await fetchData(categoryId, currentPeriod.value);
  } else {
    error.value = 'Категория не найдена';
  }

  loading.value = false;

  return true

}

onMounted(() => {
  axios.defaults.baseURL = window.location.origin;
  if (window.location.origin.endsWith(':5173')) {
    axios.defaults.baseURL = window.location.origin.replace(':5173', ':5000');
  }
  // else {
  //   axios.defaults.baseURL = 'https://ytr.o2t4.ru';
  // }
  axios.defaults.baseURL += '/api/ytr/'
  console.log('baseURL', axios.defaults.baseURL)

  // Установка withCredentials в true для передачи куки
  axios.defaults.withCredentials = true;

  initialize();

})
</script>

<template>
  <div class="mx-auto px-2 max-w-screen-lg">
    <h1 class="flex flex-wrap items-center justify-center gap-2 text-xl md:text-4xl my-3 ">Рейтинг
      <img class="h-6 md:h-8" src="/img/youtube_logo_black.svg" alt="">
      каналов
    </h1>
    <p v-if="loading">Loading...</p>
    <p v-else-if="error">{{ error }}</p>
    <div v-else>

      <!-- Navigation -->
      <!-- Category -->
      <div class="flex flex-col md:flex-row justify-center items-center shadow select-none gap-1 md:gap-5">
        <select v-model="currentCategoryId" @change="changeCategory($event.target.value)" name="category"
          class="pl-1   text-black text-base  cursor-pointer rounded">
          <option class=" text-left" v-for="category in metaData" :key="category.id" :value="category.id">{{
            category.name }}
          </option>
        </select>

        <!-- Period -->
        <div class="flex justify-center items-center select-none gap-1">
          <img src="/img/arrowLeftWhite.svg" class="h-4 mx-1 cursor-pointer" @click="changePeriod(-1)" />
          <h3 class="text-center text-base">{{ periodDisplay }}</h3>
          <img src="/img/arrowLeftWhite.svg" class="h-4 mx-1 cursor-pointer rotate-180" @click="changePeriod(1)" />
        </div>

        <!-- Sort order -->
        <div class="flex flex-row items-center gap-1">
          <div class="bg-white rounded-lg h-5 w-7 items-center flex justify-center">
            <img src="/img/sortBtn.svg" class="h-4" />
          </div>
          <div>
            <select v-model="selectedSort" @change="selectedSort = $event.target.value" name="sort"
              class=" text-black  cursor-pointer rounded">
              <option class=" text-left" v-for="sort in sortTypes" :key="sort.id" :value="sort.id">{{
                sort.name }}
              </option>
            </select>

          </div>
        </div>
      </div>

      <!-- Category title -->
      <h2 class="text-center text-xl md:text-3xl my-3">{{ data.category.title }}</h2>

      <!-- Chart -->
      <Chart :data="data" :selected-sort="selectedSort" />

      <info-block header="Методика" class="text-xs  mt-10">Рейтинг на основе суммы просмотров на канале по видео и
        клипам двух последних месяцев. Клипы (shorts) учитываются с коэффициентом 1/10. <p>Критерии выбора каналов: {{
          data.category.description }}</p>

      </info-block>
    </div>
    <info-block header="Предложить свой канал или тему" class="text-lg mt-3"><feedback-form /></info-block>

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
