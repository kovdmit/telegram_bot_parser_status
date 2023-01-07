import requests
from pprint import pprint


url = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
headers = {'Authorization': 'OAuth y0_AgAAAABTR6wVAAYckQAAAADY6BsylSb_GswRTW-NTfEJ94858Q2vZIk'}
payload = {'from_date': 1673010053}

# Делаем GET-запрос к эндпоинту url с заголовком headers и параметрами params
homework_statuses = requests.get(url, headers=headers, params=payload).json()

# Печатаем ответ API в формате JSON
pprint(homework_statuses)
