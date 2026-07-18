# Fuel Consumption — Front-end

Interface web estática (HTML + CSS + JavaScript vanilla) que roda
**100% no navegador**. O motor de cálculo vive em `engine/` (ES
modules) — não há API externa, não há back-end, não há build step.

> Stack: HTML5 · CSS3 (variáveis, dark/light auto) · JS ES2020 · Chart.js 4.4 via CDN

## Como rodar local

Qualquer servidor estático serve. O mais simples:

```bash
cd frontend
python3 -m http.server 8080
# Abra: http://localhost:8080/
```

> Não funciona abrir `index.html` direto pelo `file://` — o
> `<script type="module">` é bloqueado por esse protocolo.

## Como usar

1. Escolha um **preset de veículo** (5 carros + 4 motos) ou abra
   *Especificações customizadas* pra sobrescrever campos.
2. Preencha os parâmetros da viagem (**distância é o único
   obrigatório**).
3. Clique em **Calcular**.

A página mostra:

- **Total de combustível** (L) e **custo em BRL** (se você
  informar `fuel_price_brl_per_l`)
- **Consumo médio** em km/L e L/100 km
- **Energia consumida** (MJ) e **CO₂ emitido** (kg)
- **Gráfico de fatores** (Chart.js): quanto cada variável
  contribuiu pro resultado
- **Breakdown por segmento** de 100 m (inclinação, velocidade,
  potência trativa, combustível)
- **Avisos** operacionais (pneu murcho, tanque pequeno, AC no frio…)

A última entrada válida é salva em `localStorage` (chave
`fuel:form-cache:v1`). Se o DOM for limpo por algum motivo
(extensão, autofill, bug de navegador), o app restaura do cache
e segue com o cálculo.

## Como hospedar

### Netlify (mais fácil)

O `netlify.toml` na raiz já está configurado (`publish = "frontend"`).

1. Conecte o repo no GitHub em <https://app.netlify.com/start>
2. Build command: (vazio) · Publish directory: `frontend`
3. Push na `main` → redeploy automático

### Outras opções

- **GitHub Pages**: settings → Pages → source: `main`, folder: `/frontend`
- **Vercel / Cloudflare Pages**: importar repo, publish = `frontend`
- **S3 / nginx / qualquer host estático**: copie o conteúdo de `frontend/`

## Estrutura

```
frontend/
├── index.html           # página única
├── styles.css           # tema dark/light
├── app.js               # controller: form, eventos, render
├── engine/
│   ├── physics.js       # arrasto, rolamento, subida, potência, vazão
│   ├── corrections.js   # 13+ fatores multiplicativos
│   ├── presets.js       # 9 veículos (5 carros + 4 motos)
│   ├── calculator.js    # orquestração + integração 100m + stop-and-go
│   └── index.js         # barrel re-exportando a API pública
├── _headers             # Netlify: headers de segurança
├── _redirects           # Netlify: regras de redirect
└── README.md            # este arquivo
```

## Stack

- HTML5 puro
- CSS puro com custom properties (suporta dark/light automático
  via `prefers-color-scheme`)
- JavaScript ES2020, sem build
- [Chart.js 4.4](https://www.chartjs.org/) via CDN
- ES modules nativos (`<script type="module">`)

## Limitações conhecidas

- O breakdown por segmento mostra os primeiros 50 (~5 km). Viagens
  maiores mostram `+N segmentos` no fim da tabela.
- Sem histórico de cálculos nesta versão.
- Sem autenticação (a página é pública).
- Cache do form (`localStorage`) só guarda a última entrada válida.
