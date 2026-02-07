# Ozon Ads Local — подробная документация по API

Документ описывает API, которые использует текущий UI, а также форматы ответов и правила интерпретации полей.

## Базовые параметры

- База: `https://api-performance.ozon.ru`
- Аутентификация: `Bearer` токен, полученный через `POST /api/client/token`
- Переменные окружения (см. `.env`):
  - `PERF_CLIENT_ID`
  - `PERF_CLIENT_SECRET`

## 1) Получение токена

### Запрос
```http
POST /api/client/token
Content-Type: application/x-www-form-urlencoded

client_id=...&client_secret=...&grant_type=client_credentials
```

### Ответ
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

## 2) Список кампаний

### Запрос
```http
GET /api/client/campaign?advObjectType=SKU
Authorization: Bearer <token>
Accept: application/json
```

### Пример ответа (по campaign_id = 19295547)
```json
[
  {
    "id": "19295547",
    "title": "Поиск 200 Эрл",
    "state": "CAMPAIGN_STATE_RUNNING",
    "advObjectType": "SKU",
    "fromDate": "2025-12-02",
    "toDate": "",
    "dailyBudget": "0",
    "placement": [
      "PLACEMENT_TOP_PROMOTION"
    ],
    "budget": "0",
    "createdAt": "2025-12-02T05:22:29.140958Z",
    "updatedAt": "2025-12-12T05:57:21.865680Z",
    "productCampaignMode": "PRODUCT_CAMPAIGN_MODE_AUTO",
    "productAutopilotStrategy": "TARGET_BIDS",
    "autopilot": null,
    "PaymentType": "CPC",
    "expenseStrategy": "DAILY_BUDGET",
    "weeklyBudget": "2000000000",
    "budgetType": "PRODUCT_CAMPAIGN_BUDGET_TYPE_WEEKLY",
    "startWeekDay": "TUESDAY",
    "endWeekDay": "MONDAY",
    "autoIncrease": {
      "autoIncreasePercent": null,
      "isAutoIncreased": false,
      "autoIncreasedBudget": null,
      "recommendedAutoIncreasePercent": null
    },
    "ProductAdvPlacements": [],
    "isAutocreated": false,
    "autostopStatus": "AUTOSTOP_STATUS_NONE"
  }
]
```

### Поля (ключевые)
| Поле | Тип | Значение |
|---|---|---|
| `id` | string | ID кампании |
| `title` | string | Название |
| `state` | string | Статус (пример: `CAMPAIGN_STATE_RUNNING`) |
| `advObjectType` | string | Тип объекта (`SKU`) |
| `fromDate` / `toDate` | string | Период кампании (ISO дата) |
| `dailyBudget` / `budget` / `weeklyBudget` | string | Бюджеты (единицы зависят от типа бюджета) |
| `productCampaignMode` | string | Режим кампании (авто/ручной) |
| `productAutopilotStrategy` | string | Стратегия (пример: `TARGET_BIDS`) |
| `PaymentType` | string | Тип оплаты (`CPC`) |
| `expenseStrategy` | string | Стратегия трат |

> Примечание: часть значений приходит строками, даже если по смыслу это числа.

## 3) Товары кампании (ставки)

### Запрос
```http
GET /api/client/campaign/{campaign_id}/v2/products?page=1&pageSize=100
Authorization: Bearer <token>
Accept: application/json
```

### Пример ответа
```json
{
  "products": [
    {
      "sku": "2878122582",
      "bid": "10000000",
      "title": "Чай черный листовой Эрл Грей с бергамотом, 200г"
    }
  ]
}
```

### Поля
| Поле | Тип | Значение |
|---|---|---|
| `sku` | string | SKU товара |
| `bid` | string | Ставка в микро-рублях |
| `title` | string | Название товара |

### Важно про `bid`
`bid` приходит в микро-рублях.  
Пример: `10000000` = `10` руб.

## 4) Обновление ставок

### Запрос
```http
PUT /api/client/campaign/{campaign_id}/products
Authorization: Bearer <token>
Accept: application/json

{
  "bids": [
    { "sku": "2878122582", "bid": "10000000" }
  ]
}
```

### Ответ
В зависимости от API может возвращаться либо JSON-объект, либо пустой ответ.

## 5) Статистика кампаний (period / day range)

### Запрос
```http
GET /api/client/statistics/campaign/product/json?dateFrom=2026-01-20&dateTo=2026-01-27&campaignIds=19295547
Authorization: Bearer <token>
Accept: application/json
```

### Пример ответа
```json
{
  "rows": [
    {
      "id": "19295547",
      "title": "Поиск 200 Эрл",
      "objectType": "SKU",
      "status": "running",
      "placement": "top-promotion",
      "weeklyBudget": "2000,00",
      "budget": "0,00",
      "moneySpent": "2251,53",
      "views": "7412",
      "clicks": "241",
      "ctr": "0,03",
      "clickPrice": "9,34",
      "orders": "17",
      "ordersMoney": "11050,00",
      "drr": "20,4",
      "toCart": "45",
      "strategy": "TARGET_BIDS"
    }
  ]
}
```

### Поля (ключевые)
| Поле | Тип | Значение |
|---|---|---|
| `moneySpent` | string | Расход (строка с запятой как разделителем) |
| `views` | string | Показы |
| `clicks` | string | Клики |
| `clickPrice` | string | CPC из API |
| `ordersMoney` | string | GMV по заказам |
| `orders` | string | Кол-во заказов |
| `toCart` | string | Добавления в корзину |
| `ctr` | string | CTR (в API) |

> Примечание: числовые поля часто приходят строками и с запятой как десятичным разделителем.

## Как считаются метрики в UI

### click_price
- если кликов > 0: `money_spent / clicks`
- иначе: берем `clickPrice` из статистики

## Логи изменений ставок (локально)

Файл: `bid_changes.csv`  
Столбцы:
- `ts_iso`, `date`, `campaign_id`, `sku`, `old_bid_micro`, `new_bid_micro`, `reason`

Используется для отображения “Изменение bid” в деталке.
