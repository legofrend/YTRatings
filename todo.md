1. ~~сохарнить локально лого каналов на впс~~
   ~~проверить размер лого, почему не квадратные~~
2. ~~добавить в стационарную страницу канала еще и топ 5 видео по топ 10 каналов, чтобы быстрее работало~~
   (API /channels?videos_limit=5&videos_for=10 → SSG payload)
3. ~~добавить новую категорию топ каналов по миру~~
4. распарсить данные по топ каналов категорий с сайтов
   [https://whatstat.ru/youtube/channels?sort=views](https://whatstat.ru/youtube/channels?sort=views)
   [https://livedune.com/ru/ratings/youtube/russia/category/news_politics/?sort=vr](https://livedune.com/ru/ratings/youtube/russia/category/news_politics/?sort=vr)
5. ~~добавить в сео ключевые слова поисковых запросов яндекса~~ (сделано: title/desc/H1/keywords + «в мире»)
6. ~~как активировать прохождение робота по сайту, чтобы взял новую инфу~~
7. ~~редактирование каналов, сделать UX только для админа~~
8. ~~как все выглядит на мобильном телефоне~~
9. ~~учёт квоты YT~~
10. ~~топ видео категории~~ (`/videos?category_id=&period=` + UI над графиком)
11. ~~расчет приоритетов~~
12. ~~замена ювикорн на проде~~ (не надо при текущей нагрузке; uvicorn ок)
