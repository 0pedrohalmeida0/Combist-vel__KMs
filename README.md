# Fuel Consumption API

API REST em **FastAPI** que estima o consumo de combustível de veículos
leves (carros e motos) para uma viagem, considerando aerodinâmica,
resistência de rolamento, aclive, perfil de paradas, vento, altitude,
temperatura, umidade, carga, estilo de direção, qualidade do
combustível, idade do veículo e tipo de transmissão.

> **Stack**: Python 3.11 · FastAPI · Pydantic v2 · Uvicorn · pytest + httpx

Acompanha uma **interface web estática** em [`frontend/`](frontend/) — HTML + CSS + JavaScript vanilla, sem build step, pronta pra servir com qualquer servidor estático. Veja [`frontend/README.md`](frontend/README.md).

---

## Visão geral

A API recebe um JSON descrevendo o veículo e a viagem e devolve:

- **Total de combustível** (L)
- **Consumo médio** (km/L e L/100 km)
- **Energia consumida** (MJ)
- **CO₂ emitido** (kg)
- **Duração** da viagem (h)
- **Custo** em BRL (se `fuel_price_brl_per_l` for informado)
- **Breakdown por segmento** (100 m cada) + **fatores de correção
  aplicados** + **avisos** (pneu murcho, tanque pequeno, AC no frio…)

O cálculo integra a viagem em segmentos de 100 m, somando
instantaneamente a vazão de combustível em cada segmento. As
correções finais (estilo, altitude, qualidade, etc.) são aplicadas
como fatores multiplicativos.

---

## Como rodar

### 1. Setup

```bash
cd fuel-consumption-api
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # opcional — edite conforme necessário
```

### 2. Servidor de desenvolvimento

```bash
uvicorn app.main:app --reload --port 8000
```

Documentação interativa: <http://localhost:8000/docs>

### 3. Testes

```bash
python -m pytest -q
```

83 testes cobrindo física, correções, serviço de cálculo e rotas HTTP.

---

## Variáveis de ambiente

Todas opcionais. Carregadas de `.env` se existir (veja `.env.example`).

| Variável              | Padrão                       | Descrição                                  |
|-----------------------|------------------------------|--------------------------------------------|
| `APP_NAME`            | `fuel-consumption-api`        | Identificador da aplicação                 |
| `VERSION`             | `0.1.0`                      | Versão exposta em `/health`                 |
| `ENVIRONMENT`         | `dev`                        | `dev` \| `staging` \| `prod`               |
| `LOG_LEVEL`           | `INFO`                       | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`\|`CRITICAL` |
| `CORS_ORIGINS`        | `*`                          | CSV de origens permitidas (CORS)           |
| `BATCH_SIZE_LIMIT`    | `100`                        | Limite de itens em `/calculate/batch`      |
| `SEGMENT_LENGTH_M`    | `100`                        | Tamanho do segmento de integração (m)      |

> ⚠️ Em **produção** configure `CORS_ORIGINS` explicitamente (ex.:
> `https://app.example.com`) e nunca use `*` com credenciais.

---

## Endpoints

Todos sob `/api/v1/fuel` (exceto `/health` e `/ready`).

| Método | Rota                                | Descrição                                |
|--------|-------------------------------------|------------------------------------------|
| GET    | `/health`                           | Liveness probe                           |
| GET    | `/ready`                            | Readiness probe (executa cálculo de sanidade) |
| GET    | `/api/v1/fuel/presets`              | Lista os 9 presets de veículos           |
| GET    | `/api/v1/fuel/presets/{id}`         | Detalhe de um preset                     |
| POST   | `/api/v1/fuel/calculate`            | Calcula o consumo de uma viagem          |
| POST   | `/api/v1/fuel/calculate/batch`      | Calcula N viagens (máx. `BATCH_SIZE_LIMIT`) |

### Request body — `POST /api/v1/fuel/calculate`

Apenas `vehicle.type` e `trip.distance_km` são obrigatórios. O
`vehicle` aceita um formato **parcial**: o resto dos campos é
preenchido a partir do `preset_id` (quando informado) e o resultado
é revalidado antes do cálculo. Se mesmo após o merge faltar algum
campo obrigatório, a resposta será 422.

**Forma mais curta** (apenas type + preset):
```jsonc
{
  "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
  "trip":    {"distance_km": 100, "average_speed_kmh": 80}
}
```

**Forma completa** (com overrides do preset):
```jsonc
{
  "vehicle": {
    "type": "car",                       // "car" | "motorcycle"
    "preset_id": "car-compact-popular",  // opcional — preenche o resto
    "category": "hatch",                 // ou "custom"
    "empty_weight_kg": 1100.0,
    "engine_displacement_l": 1.0,
    "engine_power_kw": 75.0,
    "transmission": "manual",            // "manual" | "automatic" | "cvt"
    "cylinders": 3,
    "drag_coefficient_cd": 0.33,         // 0.15 a 0.6
    "frontal_area_m2": 2.10,             // 0.3 a 4
    "rolling_resistance_coeff": 0.010,   // 0.005 a 0.025
    "tire_pressure_kpa": 220.0,
    "fuel_tank_capacity_l": 44.0,
    "fuel_type": "gasoline",             // "gasoline" | "ethanol" | "diesel" | "flex"
    "year": 2024
  },
  "trip": {
    "distance_km": 100.0,                // OBRIGATÓRIO
    "average_speed_kmh": 80.0,
    "speed_profile": "constant",         // "constant" | "urban" | "suburban" | "highway" | "mixed"
    "idle_time_min": 0.0,
    "stops_per_km": 0.0,                 // se 0, usa o default do profile
    "elevation_profile": null            // ou [{distance_km, elevation_m}, …] estritamente crescente
  },
  "environment": {
    "temperature_c": 20.0,
    "altitude_m": 0.0,
    "humidity_pct": 60.0,
    "wind_speed_kmh": 0.0,
    "wind_direction_deg": 0.0,           // 0 = headwind puro
    "road_condition": "dry"              // "dry" | "wet" | "snow" | "ice"
  },
  "load": {
    "passenger_count": 1,
    "passenger_avg_weight_kg": 75.0,
    "cargo_weight_kg": 0.0,
    "towing_kg": 0.0
  },
  "driver": {
    "driving_style": "normal",           // "eco" | "normal" | "aggressive"
    "use_ac": false,
    "fuel_quality": "regular",           // "regular" | "premium"
    "fuel_price_brl_per_l": 6.0          // opcional
  }
}
```

**Regras de merge**:
- Se `preset_id` for informado, o serviço usa os campos do preset e
  sobrescreve com os campos que o cliente efetivamente enviou.
- Se o cliente enviar campos extras (ex.: `drag_coefficient_cd`),
  eles sobrescrevem o valor do preset.
- Se um campo obrigatório do resolved `VehicleSpec` continuar
  faltando (ex.: custom sem `engine_power_kw`), a resposta será
  422 com `code: VALIDATION_ERROR`.

### Exemplo de chamada `curl`

```bash
# Health check
curl http://localhost:8000/health
# {"status":"ok"}

# Calcular uma viagem
curl -X POST http://localhost:8000/api/v1/fuel/calculate \
  -H 'content-type: application/json' \
  -d @sample.json
```

### Exemplo de resposta

```json
{
  "vehicle_label": "car-compact-popular",
  "fuel_type": "gasoline",
  "distance_km": 100.0,
  "trip_duration_h": 1.25,
  "average_speed_kmh": 80.0,
  "total_fuel_l": 5.94,
  "fuel_per_km_l_per_100km": 5.94,
  "km_per_l": 16.83,
  "energy_mj": 32.70,
  "co2_kg": 14.04,
  "fuel_cost_brl": 35.66,
  "factors": [
    {"name": "altitude", "factor": 1.0, "note": null},
    {"name": "temperature", "factor": 1.0, "note": null},
    {"name": "humidity", "factor": 1.0, "note": null},
    {"name": "road_condition", "factor": 1.0, "note": null},
    {"name": "driving_style", "factor": 1.0, "note": null},
    {"name": "fuel_quality", "factor": 1.0, "note": null},
    {"name": "vehicle_age", "factor": 1.0, "note": null},
    {"name": "transmission", "factor": 1.0, "note": null},
    {"name": "tire_pressure", "factor": 1.0, "note": null},
    {"name": "load", "factor": 1.0, "note": null},
    {"name": "ethanol_blend_volume", "factor": 1.0, "note": null},
    {"name": "ethanol_blend_co2", "factor": 1.0, "note": null}
  ],
  "segments": [
    {"index": 0, "start_km": 0.0, "end_km": 0.1, "grade_pct": 0.0,
     "speed_kmh": 80.0, "tractive_power_w": 7218.6, "fuel_l": 0.0059},
    "..."
  ],
  "warnings": [],
  "total_mass_kg": 1175.0,
  "air_density_kg_per_m3": 1.2186,
  "effective_headwind_kmh": 0.0,
  "aux_power_effective_w": 1500.0
}
```

### Códigos de erro

Todas as respostas de erro seguem o formato:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Payload inválido",
    "request_id": "abc123…",
    "details": [/* opcional */]
  }
}
```

| Status | Code                 | Quando                                            |
|--------|----------------------|---------------------------------------------------|
| 404    | `NOT_FOUND`          | `preset_id` desconhecido                          |
| 413    | `PAYLOAD_TOO_LARGE`  | Batch > `BATCH_SIZE_LIMIT` itens                  |
| 422    | `VALIDATION_ERROR`   | Payload inválido (campos fora de faixa, etc.)     |
| 500    | `INTERNAL_ERROR`     | Erro inesperado — verifique os logs               |

---

## Presets incluídos

Cinco carros e quatro motos, com especificações realistas do mercado
brasileiro. Use `GET /api/v1/fuel/presets` para a lista completa.

| `preset_id`             | Tipo  | Combustível | Referência de mercado            |
|-------------------------|-------|-------------|----------------------------------|
| `car-compact-popular`   | car   | gasoline    | Chevrolet Onix 1.0               |
| `car-sedan-medium`      | car   | flex        | Toyota Corolla 2.0               |
| `car-suv-compact`       | car   | gasoline    | Jeep Compass 1.3T                |
| `car-pickup`            | car   | diesel      | Toyota Hilux 2.8                 |
| `car-sport`             | car   | gasoline    | Honda Civic Si 1.5T              |
| `moto-scooter-125`      | moto  | gasoline    | Honda Biz 125                    |
| `moto-naked-300`        | moto  | gasoline    | Honda CB300F                     |
| `moto-sport-600`        | moto  | gasoline    | Honda CBR600RR                   |
| `moto-touring-1300`     | moto  | gasoline    | Honda Gold Wing 1800             |

Para usar um preset, basta informar `vehicle.preset_id` e os demais
campos faltantes serão preenchidos (sobreponíveis pelo usuário).

---

## Correções aplicadas

A cada cálculo, os seguintes fatores multiplicativos são combinados:

| Fator                  | Efeito                                                                  |
|------------------------|-------------------------------------------------------------------------|
| **altitude**           | +4% por 1000 m acima de 1500 m (cap em +25%)                           |
| **temperature**        | Motor frio: +1.0 a +2.0 (decai com a distância via `exp(-d/5)`)        |
| **humidity**           | ±0.2% (ar úmido é menos denso)                                         |
| **road_condition**     | dry 1.00 · wet 1.05 · snow 1.20 · ice 1.35                            |
| **driving_style**      | eco 0.92 · normal 1.00 · aggressive 1.18                               |
| **fuel_quality**       | regular 1.00 · premium 0.97                                            |
| **vehicle_age**        | +0.5%/ano, cap em +20%                                                 |
| **transmission**       | manual 1.00 · automatic 1.05 · cvt 1.03                                |
| **tire_pressure**      | +0.2% por kPa abaixo do nominal (220 kPa)                              |
| **load**               | +0.5% por 100 kg acima de 200 kg, cap em +5%                           |
| **ac**                 | +1.5 a +3 kW no aux; cresce com T > 22 °C e decai em T < 10 °C         |
| **ethanol_blend**      | flex+premium ≈ 1.30× volume, 0.65× CO₂ (etanol puro)                   |

Vento de proa é incorporado **diretamente no cálculo de arrasto**
(soma vetorial com a velocidade de cruzeiro), não como fator posterior.

---

## Arquitetura

```
fuel-consumption-api/
├── app/
│   ├── main.py                 # FastAPI app, middleware, handlers, lifespan
│   ├── config.py               # Settings (Pydantic)
│   ├── errors.py               # AppError hierarchy + global payload
│   ├── middleware/
│   │   ├── request_id.py       # Gera/propaga X-Request-ID
│   │   └── logging_mw.py       # Log JSON por requisição
│   ├── fuel/
│   │   ├── routes.py           # /api/v1/fuel/* (controller)
│   │   ├── service.py          # Orquestra physics + corrections
│   │   ├── repository.py       # Carrega presets
│   │   ├── presets.py          # 9 veículos pré-definidos
│   │   ├── schemas.py          # Pydantic v2 DTOs
│   │   ├── physics.py          # Forças, energia, combustível
│   │   └── corrections.py      # Fatores multiplicativos
│   └── shared/
│       └── logger.py           # JSON formatter
├── tests/
│   ├── test_physics.py
│   ├── test_corrections.py
│   ├── test_service.py
│   └── test_routes.py
├── requirements.txt
├── .env.example
├── pytest.ini
└── README.md
```

### Modelo físico

Para cada segmento de 100 m, computa-se:

- **Densidade do ar** com pressão barométrica + vapor d'água (Tetens)
- **Força de arrasto**: F_d = 0.5 · ρ · Cd · A · (v + headwind)²
- **Resistência de rolamento**: F_r = Crr · m · g · cos(θ)
- **Força de aclive**: F_c = m · g · sin(θ)
- **Potência de tração**: P_t = (F_d + F_r + F_c) · v
- **Potência total** inclui auxiliares (1500 W base + AC)
- **Vazão mássica**: ṁ = P / (η_eng · η_drv · LHV)
- **Vazão volumétrica**: L/s = ṁ / ρ_fuel
- **Combustível do segmento**: L/s · dx/v

Stop-and-go (perfis `urban`/`suburban`/`mixed`/`highway`) adiciona
energia cinética + marcha lenta a cada parada modelada.

---

## Limitações conhecidas

- **Modelo simplificado**: atrito interno do motor, perdas por
  transmissão (engrenagens), arrasto de rodagem, etc. são agrupados
  em `drivetrain_efficiency` e `engine_thermal_efficiency`.
- **Sem mapa de elevação global**: só é possível passar perfis de
  elevação por trecho (`elevation_profile`). Topografia detalhada
  exigiria integração com um serviço externo.
- **Vento é tratado apenas como componente longitudinal** (headwind /
  tailwind). Vento lateral afeta levemente o coeficiente de arrasto
  efetivo, mas isso não está modelado.
- **Inércia rotacional** (rodas, virabrequim) é aproximada via
  `engine_thermal_efficiency` na fase de aceleração.
- **Perfil de paradas** é estatístico-estável por índice de segmento
  (não estritamente aleatório), o que torna o cálculo reproduzível
  entre chamadas.
- **Preço de combustível** é apenas BRL por litro (sem impostos
  separados, sem cálculo de consumo por estado).

---

## Testes

```bash
# Suite completa
python -m pytest -q

# Apenas um módulo
python -m pytest tests/test_physics.py -v
python -m pytest tests/test_routes.py -v
```

**Referência de sanidade**: 100 km plana, 80 km/h, sem vento, 20 °C,
gasolina, com `car-compact-popular` → **~5.94 L** (intervalo
esperado 5.6 – 6.2 L). O valor de mão é:

```
F_drag  = 0.5 · 1.225 · 0.33 · 2.10 · 22.22² ≈ 209.6 N
F_roll  = 0.010 · 1175 · 9.80665 · cos(0) ≈ 115.2 N
P_tract = 324.8 N · 22.22 m/s ≈ 7218.6 W
P_total = 7218.6 + 1500 = 8718.6 W
ṁ       = 8718.6 / (0.25 · 0.85 · 42e6) ≈ 0.000977 kg/s
v̇      = 0.000977 / 0.745 ≈ 0.00131 L/s
T(100km) = 1.25 h
fuel    ≈ 0.00131 · 3600 · 1.25 ≈ 5.90 L
```

---

## Licença

MIT
