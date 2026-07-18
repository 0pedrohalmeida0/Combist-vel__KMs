# Fuel Consumption

Calculadora de consumo de combustível para veículos leves (carros e
motos), que roda **100% no navegador** — sem servidor, sem API
externa, sem build step.

> **Stack**: JavaScript ES2020 (vanilla) · HTML5 · CSS3 · Chart.js via CDN
>
> Cálculo: 9 presets de veículos · 13+ fatores de correção · integração por segmento de 100 m · stop-and-go

A interface é uma página estática servida de qualquer host
(Netlify, GitHub Pages, S3, `python3 -m http.server` no seu
notebook). O motor de cálculo vive em `frontend/engine/` e foi
portado de um back-end Python/FastAPI para JS puro, com a mesma
física e os mesmos resultados bit-a-bit (validado contra 15
cenários, diff < 0.05%).

---

## Demo

Acesse a versão hospedada: [fuel-comb.netlify.app](https://fuel-comb.netlify.app)

---

## Como rodar local

Qualquer servidor estático serve. O mais simples:

```bash
cd frontend
python3 -m http.server 8080
# Abra: http://localhost:8080/
```

> Não funciona abrir `index.html` direto pelo `file://` — o
> `<script type="module">` é bloqueado pelo protocolo `file://`.

---

## Como usar

1. Escolha um **preset de veículo** (5 carros + 4 motos) ou abra
   *Especificações customizadas* pra sobrescrever campos.
2. Preencha os parâmetros da viagem (**distância é o único
   obrigatório**).
3. Clique em **Calcular**.

O resultado mostra:

- **Total de combustível** (L) e **custo em BRL** (se você informar
  o preço por litro)
- **Consumo médio** (km/L e L/100 km)
- **Energia consumida** (MJ) e **CO₂ emitido** (kg)
- **Gráfico de fatores** que mostra como cada variável (altitude,
  temperatura, vento, estilo, etc.) contribuiu pro resultado
- **Breakdown por segmento** de 100 m com inclinação, velocidade,
  potência trativa e combustível gasto
- **Avisos** operacionais (pneu murcho, tanque pequeno, AC no frio…)

---

## Como hospedar

### Netlify (recomendado)

1. Conecte o repo no GitHub em <https://app.netlify.com/start>
2. Config:
   - **Build command**: (vazio)
   - **Publish directory**: `frontend`
3. Push na `main` faz redeploy automático.

O `netlify.toml` já tá configurado — cache de assets, headers de
segurança, etc.

### Outras opções

- **GitHub Pages**: settings → Pages → source: `main`, folder: `/frontend`
- **Vercel/Cloudflare Pages**: importar repo, publish = `frontend`
- **S3 / nginx / qualquer host estático**: copie o conteúdo de `frontend/`

---

## Stack

| Camada | Tecnologia |
|---|---|
| UI | HTML5 + CSS3 (variáveis, dark/light auto) + JS vanilla |
| Gráfico | [Chart.js 4.4](https://www.chartjs.org/) via CDN |
| Cálculo | ES modules em `frontend/engine/` |
| Build | nenhum — `python3 -m http.server` resolve |

---

## Estrutura

```
Fuel-Consumption-API/
├── frontend/
│   ├── index.html           # página única
│   ├── styles.css           # tema dark/light
│   ├── app.js               # controller (form, eventos, render)
│   ├── engine/
│   │   ├── physics.js       # arrasto, rolamento, subida, potência, vazão
│   │   ├── corrections.js   # 13+ fatores multiplicativos
│   │   ├── presets.js       # 9 veículos (5 carros + 4 motos)
│   │   ├── calculator.js    # orquestração + integração 100m + stop-and-go
│   │   └── index.js         # barrel
│   ├── _headers             # Netlify: headers de segurança
│   ├── _redirects           # Netlify: regras de redirect
│   └── README.md
├── netlify.toml
└── README.md                # este arquivo
```

---

## Modelo físico

Para cada **segmento de 100 m** da viagem, computa-se:

- **Densidade do ar** ρ com pressão barométrica (modelo ISA) +
  vapor d'água (Tetens), função de altitude, temperatura e umidade
- **Força de arrasto**: `F_d = 0.5 · ρ · Cd · A · (v + headwind)²`
- **Resistência de rolamento**: `F_r = Crr · m · g · cos(θ)`
- **Força de aclive**: `F_c = m · g · sin(θ)`
- **Potência de tração**: `P_t = (F_d + F_r + F_c) · v`
- **Potência total** inclui auxiliares (1500 W base + AC + extras)
- **Vazão mássica**: `ṁ = P / (η_eng · η_drv · LHV)`
- **Vazão volumétrica**: `L/s = ṁ / ρ_fuel`
- **Combustível do segmento**: `L/s · dx/v`

Stop-and-go (perfis `urban` / `suburban` / `mixed` / `highway`)
adiciona energia cinética + marcha lenta a cada parada modelada
(rolagem determinística por índice de segmento, pra ser
reproduzível entre chamadas).

A inclinação é interpolada linearmente a partir de
`elevation_profile` ou zero (plano) quando não fornecida.

---

## Fatores de correção

A cada cálculo, os seguintes fatores multiplicativos são combinados:

| Fator | Efeito |
|---|---|
| **altitude** | +4% por 1000 m acima de 1500 m (cap em +25%) |
| **temperature** | Motor frio: +1.0 a +2.0 (decai com a distância via `exp(-d/5)`) |
| **humidity** | ±0.2% (ar úmido é menos denso) |
| **road_condition** | dry 1.00 · wet 1.05 · snow 1.20 · ice 1.35 |
| **driving_style** | eco 0.92 · normal 1.00 · aggressive 1.18 |
| **fuel_quality** | regular 1.00 · premium 0.97 |
| **vehicle_age** | +0.5%/ano, cap em +20% |
| **transmission** | manual 1.00 · automatic 1.05 · cvt 1.03 |
| **tire_pressure** | +0.2% por kPa abaixo do nominal (220 kPa) |
| **load** | +0.5% por 100 kg acima de 200 kg, cap em +5% |
| **ac** | +1.5 a +3 kW no aux; cresce com T > 22 °C e decai em T < 10 °C |
| **ethanol_blend** | flex+premium ≈ 1.30× volume, 0.65× CO₂ (etanol puro) |
| **towing** | +0.15 m² de área frontal por tonelada rebocada |

Vento de proa é incorporado **diretamente no cálculo de arrasto**
(soma vetorial com a velocidade de cruzeiro), não como fator posterior.

---

## Presets incluídos

Cinco carros e quatro motos, com especificações realistas do mercado
brasileiro:

| `preset_id` | Tipo | Combustível | Referência de mercado |
|---|---|---|---|
| `car-compact-popular` | car | gasoline | Chevrolet Onix 1.0 |
| `car-sedan-medium` | car | flex | Toyota Corolla 2.0 |
| `car-suv-compact` | car | gasoline | Jeep Compass 1.3T |
| `car-pickup` | car | diesel | Toyota Hilux 2.8 |
| `car-sport` | car | gasoline | Honda Civic Si 1.5T |
| `moto-scooter-125` | motorcycle | gasoline | Honda Biz 125 |
| `moto-naked-300` | motorcycle | gasoline | Honda CB300F |
| `moto-sport-600` | motorcycle | gasoline | Honda CBR600RR |
| `moto-touring-1300` | motorcycle | gasoline | Honda Gold Wing 1800 |

---

## Validação

Suite de 15 cenários cobrindo casos base, extremos e regressões,
comparada bit-a-bit contra o back-end Python original. Diferença
típica < 0.05% (limitada apenas por arredondamento de ponto
flutuante).

Casos cobertos:

- Carro base 100 km / 80 km/h (referência)
- Cenário adverso: frio −5 °C + altitude 1200 m + vento 30 km/h + AC + agressivo
- Moto scooter 30 km / 40 km/h
- Estilos: eco, normal, aggressive
- Vento de proa 50 km/h
- Altitude 3000 m
- Pneu murcho (120 kPa) vs cheio (320 kPa)
- Veículo de 1990 (idade)
- Moto touring 500 km / 90 km/h
- Moto sport 200 km / 150 km/h
- Urbano 50 km / 30 km/h
- Veículo custom (caminhão 2.0T diesel)
- Subida de 4% interpolada por pontos de elevação

Para rodar a suite (precisa de Node 18+):

```bash
node /tmp/compare.mjs   # ou copie o script de validação
```

---

## Limitações conhecidas

- **Modelo simplificado**: atrito interno do motor, perdas por
  transmissão, arrasto de rodagem, etc. são agrupados em
  `drivetrain_efficiency` e `engine_thermal_efficiency`.
- **Sem mapa de elevação global**: só perfis por trecho
  (`elevation_profile`).
- **Vento só longitudinal**: vento lateral não está modelado.
- **Inércia rotacional** aproximada via `engine_thermal_efficiency`
  na fase de aceleração.
- **Sem histórico** de cálculos nesta versão.
- **Preço de combustível** só BRL por litro (sem impostos separados).

---

## Licença

MIT
